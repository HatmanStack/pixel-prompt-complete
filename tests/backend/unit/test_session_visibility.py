"""Paid generations are private; everything else feeds the public gallery.

The privacy boundary is structural rather than a filter applied on read: a
private image lands under a prefix that the CloudFront origin policy does not
grant, so it has no unsigned URL at all. Forgetting a check on some future
read path cannot expose it, because there is no URL to leak.

That only holds if every path that can *reach* a private session authorizes it
first, so the enumeration below is the point of this file. Each endpoint that
returns an image URL, a prompt, or a source image gets a test.
"""

from __future__ import annotations

import os
import uuid
from unittest.mock import MagicMock, patch

import pytest

os.environ.setdefault("S3_BUCKET", "test-bucket")
os.environ.setdefault("CLOUDFRONT_DOMAIN", "test.cloudfront.net")

from users.tier import TierContext


def _ctx(tier="paid", uid="u1", authed=True):
    return TierContext(
        tier=tier,
        user_id=uid,
        email=None,
        is_authenticated=authed,
        guest_token_id=None,
        issue_guest_cookie=False,
    )


# --- which tiers get privacy -------------------------------------------------


@pytest.mark.parametrize(
    "tier,expected",
    [
        ("paid", "private"),
        ("free", "public"),
        ("guest", "public"),
        ("anon", "public"),
        (None, "public"),
    ],
)
def test_visibility_follows_tier(tier, expected):
    import lambda_function as lf

    assert lf._visibility_for_tier(tier) == expected


# --- the key encodes the boundary -------------------------------------------


def test_private_images_land_outside_the_cdn_prefix(mock_s3):
    """The bucket policy grants CloudFront sessions/* only, so private/ has no URL."""
    from utils.storage import ImageStorage

    s3, bucket = mock_s3
    st = ImageStorage(s3, bucket, "cdn.example.com")
    key = st.upload_image(
        "aGk=", "2026-07-25-12-00-00", "gemini", 0, "sess-1", "private"
    )

    assert key.startswith("private/")
    assert not key.startswith("sessions/")
    assert st.is_private_key(key)


def test_public_images_stay_in_the_gallery_prefix(mock_s3):
    from utils.storage import ImageStorage

    s3, bucket = mock_s3
    st = ImageStorage(s3, bucket, "cdn.example.com")
    key = st.upload_image(
        "aGk=", "2026-07-25-12-00-00", "gemini", 0, "sess-1", "public"
    )

    assert key.startswith("sessions/")
    assert not st.is_private_key(key)


def test_private_upload_without_a_session_id_is_refused(mock_s3):
    """The session id is the whole key namespace for a private image."""
    from utils.storage import ImageStorage

    s3, bucket = mock_s3
    st = ImageStorage(s3, bucket, "cdn.example.com")
    with pytest.raises(ValueError, match="session_id"):
        st.upload_image("aGk=", "t", "gemini", 0, None, "private")


def test_private_images_are_never_listed_in_the_gallery(mock_s3):
    """Structural, not filtered: list_galleries only ever looks under sessions/."""
    from utils.storage import ImageStorage

    s3, bucket = mock_s3
    st = ImageStorage(s3, bucket, "cdn.example.com")
    pub = str(uuid.uuid4())
    priv = str(uuid.uuid4())
    st.upload_image("aGk=", "2026-07-25-12-00-00", "gemini", 0, pub, "public")
    st.upload_image("aGk=", "2026-07-25-12-00-00", "nova", 0, priv, "private")

    galleries = st.list_galleries()
    assert galleries == [f"2026-07-25-12-00-00-{pub[:8]}"]


def test_session_state_folders_are_not_listed_as_galleries(mock_s3):
    """Session state lives at sessions/{uuid}/ and is not gallery content."""
    from utils.storage import ImageStorage

    s3, bucket = mock_s3
    st = ImageStorage(s3, bucket, "cdn.example.com")
    s3.put_object(Bucket=bucket, Key=f"sessions/{uuid.uuid4()}/status.json", Body=b"{}")

    assert st.list_galleries() == []


# --- the collision that predates all of this --------------------------------


def test_two_sessions_in_the_same_second_do_not_share_a_key(mock_s3):
    """The regression this fixes: at 500 generates/day it was 76% likely daily.

    The folder used to be a bare second-granularity timestamp and the filename
    a second-granularity timestamp plus the model. Two users generating in the
    same second with the same model produced an identical key, so one silently
    overwrote the other, and their images were merged into one gallery folder.
    """
    from utils.storage import ImageStorage

    s3, bucket = mock_s3
    st = ImageStorage(s3, bucket, "cdn.example.com")
    same_second = "2026-07-25-12-00-00"

    a = st.upload_image("aGk=", same_second, "gemini", 0, "aaaaaaaa-1111", "public")
    b = st.upload_image("aGk=", same_second, "gemini", 0, "bbbbbbbb-2222", "public")

    assert a != b, "two users' images collapsed onto one key"
    assert a.rsplit("/", 2)[-2] != b.rsplit("/", 2)[-2], (
        "sessions shared a gallery folder"
    )


def test_legacy_gallery_folders_are_still_listable(mock_s3):
    """Folders written before the session suffix must not vanish from the gallery."""
    from utils.storage import ImageStorage

    s3, bucket = mock_s3
    st = ImageStorage(s3, bucket, "cdn.example.com")
    s3.put_object(
        Bucket=bucket,
        Key="sessions/2026-01-01-00-00-00/gemini-20260101000000.png",
        Body=b"x",
    )

    assert "2026-01-01-00-00-00" in st.list_galleries()
    assert st.validate_gallery_id("2026-01-01-00-00-00")
    assert st.validate_gallery_id("2026-01-01-00-00-00-abcdef01")


# --- ownership ---------------------------------------------------------------


def test_a_private_session_is_not_owned_by_an_anonymous_caller():
    """ "No recorded owner" must not read as "owned by whoever asks"."""
    import lambda_function as lf

    session = {"visibility": "private", "ownerId": None}
    assert lf._caller_owns_session(session, _ctx()) is False


def test_a_private_session_is_not_owned_by_a_different_user():
    import lambda_function as lf

    session = {"visibility": "private", "ownerId": "u1"}
    assert lf._caller_owns_session(session, _ctx(uid="u2")) is False


def test_an_unauthenticated_context_never_owns_anything():
    import lambda_function as lf

    session = {"visibility": "private", "ownerId": "u1"}
    assert lf._caller_owns_session(session, _ctx(uid="u1", authed=False)) is False


def test_the_owner_owns_it():
    import lambda_function as lf

    session = {"visibility": "private", "ownerId": "u1"}
    assert lf._caller_owns_session(session, _ctx(uid="u1")) is True


def test_sessions_predating_visibility_are_public():
    """They have neither field, and public is how they were actually served."""
    import lambda_function as lf

    assert lf._session_is_private({"sessionId": "old"}) is False


# --- every read path that can reach a private session ------------------------

_PRIVATE_SESSION = {
    "sessionId": "s1",
    "visibility": "private",
    "ownerId": "u1",
    "status": "completed",
    "models": {
        "gemini": {
            "iterations": [
                {
                    "index": 0,
                    "status": "completed",
                    "imageKey": "private/s1/gemini-iter0.png",
                }
            ]
        }
    },
}


def _event(path, sub=None):
    ev = {
        "rawPath": path,
        "requestContext": {"http": {"sourceIp": "1.2.3.4"}},
        "headers": {},
    }
    if sub:
        ev["requestContext"]["authorizer"] = {"jwt": {"claims": {"sub": sub}}}
    return ev


def test_status_hides_a_private_session_from_a_stranger():
    import lambda_function as lf

    with (
        patch.object(
            lf.session_manager, "get_session", return_value=dict(_PRIVATE_SESSION)
        ),
        patch.object(lf, "resolve_tier", return_value=_ctx(uid="someone-else")),
    ):
        resp = lf.handle_status(_event("/status/s1"), "c1")
    assert resp["statusCode"] == 404, "a stranger could read a paid user's session"


def test_status_returns_404_not_403_so_existence_is_not_confirmed():
    import lambda_function as lf

    with (
        patch.object(
            lf.session_manager, "get_session", return_value=dict(_PRIVATE_SESSION)
        ),
        patch.object(lf, "resolve_tier", return_value=_ctx(uid="someone-else")),
    ):
        resp = lf.handle_status(_event("/status/s1"), "c1")
    assert resp["statusCode"] != 403


def test_status_serves_the_owner_a_presigned_url_not_a_cdn_url():
    import lambda_function as lf

    with (
        patch.object(
            lf.session_manager, "get_session", return_value=dict(_PRIVATE_SESSION)
        ),
        patch.object(lf, "resolve_tier", return_value=_ctx(uid="u1")),
        patch.object(
            lf.image_storage,
            "generate_presigned_view_url",
            return_value="https://signed/x",
        ) as signed,
        patch.object(lf.image_storage, "get_cloudfront_url") as cdn,
    ):
        resp = lf.handle_status(_event("/status/s1", sub="u1"), "c1")

    assert resp["statusCode"] == 200
    signed.assert_called_once()
    cdn.assert_not_called(), "a private image has no unsigned URL to hand out"


def test_download_hides_a_private_session_from_a_stranger():
    """A download URL is a grant of access, so this needs the same check."""
    import lambda_function as lf

    with (
        patch.object(
            lf.session_manager, "get_session", return_value=dict(_PRIVATE_SESSION)
        ),
        patch.object(lf, "resolve_tier", return_value=_ctx(uid="someone-else")),
    ):
        resp = lf.handle_download(_event("/download/s1/gemini/0"), "c1")
    assert resp["statusCode"] == 404


def test_refining_someone_elses_private_session_is_refused():
    """Otherwise /iterate is a way to read a private image by refining it."""
    import lambda_function as lf

    with patch.object(
        lf.session_manager, "get_session", return_value=dict(_PRIVATE_SESSION)
    ):
        loaded, err = lf._load_source_image("s1", "gemini", _ctx(uid="someone-else"))

    assert loaded is None
    assert err["statusCode"] == 404


def test_the_owner_may_refine_their_own_private_session():
    import lambda_function as lf

    with (
        patch.object(
            lf.session_manager, "get_session", return_value=dict(_PRIVATE_SESSION)
        ),
        patch.object(lf.image_storage, "get_image_bytes", return_value=b"png"),
    ):
        loaded, err = lf._load_source_image("s1", "gemini", _ctx(uid="u1"))

    assert err is None
    _img, _count, visibility = loaded
    assert visibility == "private", (
        "a refinement of a private session must stay private"
    )


def test_a_public_session_stays_readable_without_auth():
    """The gallery is the product's front door; this must not regress."""
    import lambda_function as lf

    public = {
        "sessionId": "s2",
        "visibility": "public",
        "ownerId": None,
        "models": {"gemini": {"iterations": []}},
    }
    with (
        patch.object(lf.session_manager, "get_session", return_value=public),
        patch.object(
            lf, "resolve_tier", return_value=_ctx(tier="anon", uid=None, authed=False)
        ),
    ):
        resp = lf.handle_status(_event("/status/s2"), "c1")
    assert resp["statusCode"] == 200


# --- the prompt feed is the other publication channel ------------------------


def test_a_private_prompt_never_reaches_the_public_feed():
    """/prompts/recent is unauthenticated, so a paid prompt must not be written.

    Prompts are free text. Publishing a paying user's prompt is the same
    disclosure as publishing their image, and it is a separate code path that
    the S3 prefix boundary does not cover.
    """
    from prompts.repository import PromptHistoryRepository

    table = MagicMock()
    written = []
    table.batch_writer.return_value.__enter__.return_value.put_item.side_effect = (
        lambda Item: written.append(Item)
    )
    repo = PromptHistoryRepository.__new__(PromptHistoryRepository)
    repo._table = table

    repo.record_prompt(
        user_id="u1", prompt="secret", session_id="s1", publish_to_feed=False
    )

    owners = [w["promptOwner"] for w in written]
    assert "GLOBAL#RECENT" not in owners
    assert "USER#u1" in owners, "the owner's own history should still be kept"


def test_a_public_prompt_still_reaches_the_feed():
    from prompts.repository import PromptHistoryRepository

    table = MagicMock()
    written = []
    table.batch_writer.return_value.__enter__.return_value.put_item.side_effect = (
        lambda Item: written.append(Item)
    )
    repo = PromptHistoryRepository.__new__(PromptHistoryRepository)
    repo._table = table

    repo.record_prompt(user_id=None, prompt="a cat", session_id="s1")

    assert [w["promptOwner"] for w in written] == ["GLOBAL#RECENT"]
