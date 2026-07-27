"""The execution role must grant exactly the S3 prefixes the code writes.

What this test proves: `backend/template.yaml` carries an IAM grant for every
prefix `utils.storage` can write an object under, and carries no grant for a
prefix nothing writes to. The expected set is read from
`utils.storage.WRITTEN_PREFIXES` rather than restated here, so a developer
adding a prefix has to add it to that set and this test fails until the
template grants it.

What it cannot prove: that the *deployed* role holds those grants. It reads a
file, not an account. That limitation is the whole reason the test exists at
this layer -- neither `moto` nor MiniStack enforces IAM, so every runtime test
in this repository passed while the role was missing `private/*` and every
paid-tier `/generate` failed on `PutObject` with AccessDenied (health finding
H1). No runtime test could have caught it; only a template test can.
"""

import pathlib

import yaml

from utils.storage import WRITTEN_PREFIXES

TEMPLATE = pathlib.Path(__file__).resolve().parents[3] / "backend" / "template.yaml"

# Tags whose values this test does not read. Mapping them to None is enough,
# and is what tests/backend/unit/test_observability.py does for every tag.
_UNREAD_TAGS = (
    "!Ref",
    "!GetAtt",
    "!Equals",
    "!If",
    "!Not",
    "!Join",
    "!Select",
    "!Split",
    "!FindInMap",
    "!Condition",
    "!And",
    "!Or",
    "!ImportValue",
    "!Base64",
)


class _Loader(yaml.SafeLoader):
    pass


def _sub_scalar(loader, node):
    """Preserve the text of a `!Sub` scalar.

    Every resource ARN in the policy is a `!Sub` scalar. Under the blanket
    `lambda loader, node: None` constructor that test_observability registers,
    all of them would load as None and this test would assert nothing at all.

    `!Sub` also has a two-element sequence form (`[template, {vars}]`). The
    policy does not use it; raise rather than return None if that ever changes,
    so the failure is loud instead of vacuous.
    """
    if not isinstance(node, yaml.ScalarNode):
        raise TypeError(
            "!Sub sequence form found in template.yaml; this loader only "
            "handles the scalar form and would silently drop the value"
        )
    return loader.construct_scalar(node)


_Loader.add_constructor("!Sub", _sub_scalar)
for _tag in _UNREAD_TAGS:
    _Loader.add_constructor(_tag, lambda loader, node: None)


def _s3_write_resources() -> list[str]:
    """Return the Resource list of the S3ReadWriteImages policy statement."""
    doc = yaml.load(TEMPLATE.read_text(), Loader=_Loader)
    policies = doc["Resources"]["PixelPromptFunction"]["Properties"]["Policies"]

    for policy in policies:
        if not isinstance(policy, dict):
            continue
        for statement in policy.get("Statement", []):
            if statement.get("Sid") == "S3ReadWriteImages":
                resources = statement["Resource"]
                return resources if isinstance(resources, list) else [resources]

    raise AssertionError(
        "no policy statement with Sid S3ReadWriteImages in template.yaml"
    )


def test_the_loader_preserves_resource_arns():
    """Guard the guard: a loader that drops !Sub makes every other assert vacuous."""
    resources = _s3_write_resources()

    assert resources, "S3ReadWriteImages grants no resources at all"
    for resource in resources:
        assert isinstance(resource, str) and resource, (
            f"resource {resource!r} did not load as a string -- the !Sub "
            "constructor is dropping values and this test proves nothing"
        )


def test_every_written_prefix_has_a_grant():
    """A prefix the code writes to but the role cannot write to is an outage."""
    resources = _s3_write_resources()

    for prefix in sorted(WRITTEN_PREFIXES):
        assert any(f"/{prefix}/*" in resource for resource in resources), (
            f"utils.storage writes under {prefix}/ but S3ReadWriteImages grants "
            f"only {resources} -- every write to that prefix gets AccessDenied"
        )


def test_no_grant_without_a_write_path():
    """The reverse direction: a grant nothing uses is privilege with no purpose.

    This is the assertion that would have flagged the `rate-limit/*` grant
    removed in Phase 1 -- it outlived the code that wrote there by months.
    """
    resources = _s3_write_resources()

    for resource in resources:
        assert any(f"/{prefix}/*" in resource for prefix in WRITTEN_PREFIXES), (
            f"S3ReadWriteImages grants {resource}, which matches no prefix in "
            f"utils.storage.WRITTEN_PREFIXES ({sorted(WRITTEN_PREFIXES)})"
        )
