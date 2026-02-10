"""
E2E tests exercising the critical user journey with real S3 state via LocalStack.

These tests validate the full request lifecycle: session creation, iteration,
outpainting, rate limiting, and gallery queries — all backed by real S3.
"""

import json

import pytest

from .conftest import skip_no_localstack

pytestmark = [pytest.mark.e2e, skip_no_localstack]


# ── Helpers ────────────────────────────────────────────────────────────


def _make_event(method="POST", path="/generate", body=None, source_ip="10.0.0.1"):
    event = {
        "rawPath": path,
        "requestContext": {"http": {"method": method, "sourceIp": source_ip}},
        "headers": {},
    }
    if body is not None:
        event["body"] = json.dumps(body)
    return event


def _body(resp):
    return json.loads(resp["body"])


# ── Tests ──────────────────────────────────────────────────────────────


class TestGenerateWorkflow:
    """POST /generate creates a session in S3 with correct state."""

    def test_generate_creates_session_in_s3(self, e2e_handler):
        handler, sm, *_ = e2e_handler
        resp = handler(_make_event(body={"prompt": "sunset over mountains"}), None)

        assert resp["statusCode"] == 200
        data = _body(resp)
        assert "sessionId" in data
        assert data["prompt"] == "sunset over mountains"

        # Verify session exists in S3
        session = sm.get_session(data["sessionId"])
        assert session is not None
        assert session["prompt"] == "sunset over mountains"
        assert session["status"] in ("completed", "in_progress", "partial")


class TestStatusEndpoint:
    """GET /status/{id} returns session state from S3."""

    def test_status_returns_session_state(self, e2e_handler):
        handler, sm, *_ = e2e_handler
        # Create a session first
        resp = handler(_make_event(body={"prompt": "a red car"}), None)
        session_id = _body(resp)["sessionId"]

        # Fetch status
        status_resp = handler(
            _make_event(method="GET", path=f"/status/{session_id}"), None
        )
        assert status_resp["statusCode"] == 200
        status_data = _body(status_resp)
        assert status_data["sessionId"] == session_id
        assert "models" in status_data

    def test_status_not_found(self, e2e_handler):
        handler, *_ = e2e_handler
        resp = handler(
            _make_event(method="GET", path="/status/nonexistent-id"), None
        )
        assert resp["statusCode"] == 404


class TestIterateWorkflow:
    """POST /iterate adds a new iteration to the session in S3."""

    def test_iterate_adds_iteration_to_session(self, e2e_handler):
        handler, sm, cm, *_ = e2e_handler

        # Generate initial images
        gen_resp = handler(_make_event(body={"prompt": "a blue sky"}), None)
        session_id = _body(gen_resp)["sessionId"]

        # Pick first enabled model from response
        models = _body(gen_resp)["models"]
        model_name = next(iter(models))

        # Iterate
        iter_resp = handler(
            _make_event(
                path="/iterate",
                body={
                    "sessionId": session_id,
                    "model": model_name,
                    "prompt": "make sky darker",
                },
            ),
            None,
        )
        assert iter_resp["statusCode"] == 200
        iter_data = _body(iter_resp)
        assert iter_data["status"] == "completed"
        assert iter_data["iteration"] == 1

        # Verify context was updated
        context = cm.get_context_for_iteration(session_id, model_name)
        assert len(context) >= 1


class TestOutpaintWorkflow:
    """POST /outpaint stores an expanded image in S3."""

    def test_outpaint_stores_expanded_image(self, e2e_handler):
        handler, sm, *_ = e2e_handler

        # Generate
        gen_resp = handler(_make_event(body={"prompt": "forest path"}), None)
        session_id = _body(gen_resp)["sessionId"]
        model_name = next(iter(_body(gen_resp)["models"]))

        # Outpaint
        out_resp = handler(
            _make_event(
                path="/outpaint",
                body={
                    "sessionId": session_id,
                    "model": model_name,
                    "preset": "16:9",
                    "prompt": "expand the forest",
                },
            ),
            None,
        )
        assert out_resp["statusCode"] == 200
        out_data = _body(out_resp)
        assert out_data["status"] == "completed"
        assert out_data["preset"] == "16:9"


class TestIterationLimit:
    """Session enforces MAX_ITERATIONS per model."""

    def test_iteration_limit_enforced(self, e2e_handler):
        handler, sm, *_ = e2e_handler

        gen_resp = handler(_make_event(body={"prompt": "test limit"}), None)
        session_id = _body(gen_resp)["sessionId"]
        model_name = next(iter(_body(gen_resp)["models"]))

        # Already at iteration 0 from generate. Add 6 more to reach limit of 7.
        for i in range(6):
            resp = handler(
                _make_event(
                    path="/iterate",
                    body={
                        "sessionId": session_id,
                        "model": model_name,
                        "prompt": f"iteration {i + 1}",
                    },
                ),
                None,
            )
            assert resp["statusCode"] == 200, f"Iteration {i + 1} failed: {_body(resp)}"

        # 8th attempt (index 7) should be rejected
        resp = handler(
            _make_event(
                path="/iterate",
                body={
                    "sessionId": session_id,
                    "model": model_name,
                    "prompt": "one too many",
                },
            ),
            None,
        )
        assert resp["statusCode"] == 400
        assert "limit" in _body(resp).get("error", "").lower()


class TestContextWindow:
    """Context window maintains only the last 3 entries."""

    def test_context_window_rolling_three(self, e2e_handler):
        handler, sm, cm, *_ = e2e_handler

        gen_resp = handler(_make_event(body={"prompt": "context test"}), None)
        session_id = _body(gen_resp)["sessionId"]
        model_name = next(iter(_body(gen_resp)["models"]))

        # Add 4 more iterations (5 total including initial generate)
        for i in range(4):
            handler(
                _make_event(
                    path="/iterate",
                    body={
                        "sessionId": session_id,
                        "model": model_name,
                        "prompt": f"refine {i + 1}",
                    },
                ),
                None,
            )

        context = cm.get_context_for_iteration(session_id, model_name)
        assert len(context) == 3, f"Expected 3 context entries, got {len(context)}"


class TestRateLimitWithRealS3:
    """Rate limiter increments real S3 counters."""

    def test_rate_limit_with_real_s3_counters(self, e2e_handler):
        handler, sm, cm, storage, rl = e2e_handler

        # Manually set a very low limit for testing
        rl.ip_limit = 2
        rl.global_limit = 1000

        # First two requests should pass
        r1 = handler(_make_event(body={"prompt": "req 1"}, source_ip="192.168.1.1"), None)
        assert r1["statusCode"] == 200

        r2 = handler(_make_event(body={"prompt": "req 2"}, source_ip="192.168.1.1"), None)
        assert r2["statusCode"] == 200

        # Third request from same IP should be rate limited
        r3 = handler(_make_event(body={"prompt": "req 3"}, source_ip="192.168.1.1"), None)
        assert r3["statusCode"] == 429


class TestGalleryAfterGeneration:
    """Gallery endpoints work with real S3 data."""

    def test_gallery_list_after_generation(self, e2e_handler):
        handler, *_ = e2e_handler

        # Gallery list should work even when empty
        resp = handler(_make_event(method="GET", path="/gallery/list"), None)
        assert resp["statusCode"] == 200
        assert "galleries" in _body(resp)


class TestCorsHeaders:
    """CORS headers present on all response types."""

    def _check_cors(self, resp):
        assert resp["headers"]["Access-Control-Allow-Origin"] == "*"
        assert "POST" in resp["headers"]["Access-Control-Allow-Methods"]

    def test_cors_on_200(self, e2e_handler):
        handler, *_ = e2e_handler
        resp = handler(_make_event(body={"prompt": "cors test"}), None)
        self._check_cors(resp)

    def test_cors_on_400(self, e2e_handler):
        handler, *_ = e2e_handler
        resp = handler(_make_event(body={}), None)
        assert resp["statusCode"] == 400
        self._check_cors(resp)

    def test_cors_on_404(self, e2e_handler):
        handler, *_ = e2e_handler
        resp = handler(_make_event(method="GET", path="/nonexistent"), None)
        assert resp["statusCode"] == 404
        self._check_cors(resp)

    def test_cors_on_429(self, e2e_handler):
        handler, sm, cm, storage, rl = e2e_handler
        rl.global_limit = 0  # Force rate limit
        resp = handler(_make_event(body={"prompt": "blocked"}), None)
        assert resp["statusCode"] == 429
        self._check_cors(resp)
