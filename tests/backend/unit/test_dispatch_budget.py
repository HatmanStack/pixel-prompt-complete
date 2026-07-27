"""The dispatch budget must fit under the gateway ceiling whenever there is one.

API Gateway HTTP APIs cap the integration timeout at 30 seconds and the quota
is not adjustable. `/generate` ran a 70-second dispatch budget behind it, so the
gateway returned 504 while the Lambda kept generating, storing, metering and
charging for a request the caller had been told had failed (health finding H2).

Two things are asserted here, at the only layer that can assert them:

1. The template never declares an integration timeout above the AWS hard cap.
   A value above 30000 fails the *deploy*, not the request, which is a worse
   failure to discover late.
1. The synchronous-mode invariant, as a pure function over explicit inputs.
   `GENERATE_ASYNC=false` runs the provider dispatch inside the request, so its
   budget must fit under the ceiling; async mode moves the dispatch behind an
   `Invoke` where the function's own 900s timeout applies and no gateway does.

What this cannot prove: that the *deployed* API has those timeouts. It reads a
file, not an account. And it deliberately does not run at import — see
`config.sync_mode_fits_gateway`. `GENERATE_ASYNC=false` exists for the
environments that have no gateway at all (`sam local start-api`, the MiniStack
E2E suite), and raising there would enforce a constraint that does not apply.
"""

import importlib
import os
import pathlib
from unittest.mock import patch

import pytest
import yaml

TEMPLATE = pathlib.Path(__file__).resolve().parents[3] / "backend" / "template.yaml"

# Tags whose values this test does not read, mapped to None exactly as
# tests/backend/unit/test_observability.py does. TimeoutInMillis is a plain
# integer scalar, so nothing here needs a value-preserving constructor.
_UNREAD_TAGS = (
    "!Ref",
    "!Sub",
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

# The AWS hard cap on an HTTP API integration timeout, in milliseconds.
# Not adjustable via a service quota increase.
GATEWAY_MAX_TIMEOUT_MS = 30_000


class _Loader(yaml.SafeLoader):
    pass


for _tag in _UNREAD_TAGS:
    _Loader.add_constructor(_tag, lambda loader, node: None)


def _reload_config():
    import config

    return importlib.reload(config)


@pytest.fixture(autouse=True)
def _restore_config():
    """Every test here reloads config; put the session's copy back afterwards."""
    yield
    _reload_config()


def _declared_timeouts() -> dict[str, int]:
    """Every `TimeoutInMillis` in the function's HttpApi events, by event name."""
    doc = yaml.load(TEMPLATE.read_text(), Loader=_Loader)
    events = doc["Resources"]["PixelPromptFunction"]["Properties"]["Events"]

    found = {}
    for name, event in events.items():
        timeout = (event.get("Properties") or {}).get("TimeoutInMillis")
        if timeout is not None:
            found[name] = timeout
    return found


def test_the_write_routes_declare_an_integration_timeout():
    """generate/iterate/outpaint are the routes that can outlive the ceiling.

    Declaring the value makes the real bound visible in the template. Before
    this, `grep -c TimeoutInMillis backend/template.yaml` returned 0 and the
    30-second limit existed only as an undocumented service default.
    """
    declared = _declared_timeouts()

    for event_name in ("GenerateApi", "IterateApi", "OutpaintApi"):
        assert event_name in declared, (
            f"{event_name} declares no TimeoutInMillis, so the 30s gateway "
            "ceiling is invisible at the place a reader looks for it"
        )


def test_no_declared_timeout_exceeds_the_aws_cap():
    """A value above the cap fails the deploy, not the request."""
    declared = _declared_timeouts()

    assert declared, "no TimeoutInMillis found at all; this test proves nothing"
    for event_name, timeout in declared.items():
        assert timeout <= GATEWAY_MAX_TIMEOUT_MS, (
            f"{event_name} declares TimeoutInMillis={timeout}, above the "
            f"{GATEWAY_MAX_TIMEOUT_MS} AWS hard cap -- CloudFormation rejects this"
        )


def test_the_configured_ceiling_fits_under_the_aws_cap():
    import config

    assert config.gateway_integration_timeout_seconds * 1000 <= GATEWAY_MAX_TIMEOUT_MS


def test_the_configured_ceiling_matches_the_template():
    """The code's idea of the ceiling and the deployed one must not drift."""
    import config

    declared = _declared_timeouts()
    ceiling_ms = config.gateway_integration_timeout_seconds * 1000

    for event_name, timeout in declared.items():
        assert timeout == ceiling_ms, (
            f"{event_name} declares {timeout}ms but "
            f"config.gateway_integration_timeout_seconds is "
            f"{config.gateway_integration_timeout_seconds}s ({ceiling_ms}ms)"
        )


@pytest.mark.parametrize(
    "api_client_timeout,generate_async,expected_valid",
    [
        # Synchronous mode: the provider dispatch happens inside the request,
        # so budget = api_client_timeout + 10 must clear the ceiling.
        (19.0, False, True),  # budget 29 -- exactly the ceiling
        (18.0, False, True),  # budget 28
        (20.0, False, False),  # budget 30 -- one second over
        (60.0, False, False),  # budget 70 -- the shipped default, does not fit
        # Asynchronous mode: the dispatch runs behind an Invoke with the
        # function's own 900s timeout. No gateway is in front of it, so the
        # same budget is legitimate and the ceiling does not apply.
        (60.0, True, True),
        (19.0, True, True),
    ],
)
def test_the_deployed_combination_is_classified_correctly(
    api_client_timeout, generate_async, expected_valid
):
    """The invariant as a pure function of two inputs, not an import-time raise.

    Asserting it here rather than in config's module body is deliberate: at the
    shipped defaults the synchronous combination is *always* over the ceiling,
    and API_CLIENT_TIMEOUT is neither a SAM parameter nor a Lambda environment
    variable, so no deployment could ever satisfy a raise. See ADR-A1.
    """
    env = {
        "API_CLIENT_TIMEOUT": str(api_client_timeout),
        "GENERATE_ASYNC": "true" if generate_async else "false",
        "AUTH_ENABLED": "false",
        "S3_BUCKET": "test-bucket",
    }
    with patch.dict(os.environ, env):
        config = _reload_config()

        assert config.api_client_timeout == api_client_timeout
        assert config.generate_async is generate_async
        assert config.generate_dispatch_budget_seconds == api_client_timeout + 10

        # A configuration is sound when the dispatch is asynchronous -- no
        # gateway sits in front of it -- or when the synchronous budget fits
        # under the ceiling.
        sound = config.generate_async or config.sync_mode_fits_gateway(
            config.generate_dispatch_budget_seconds
        )
        assert sound is expected_valid


@pytest.mark.parametrize(
    "budget,fits",
    [
        (28.0, True),
        (29.0, True),
        (29.5, False),
        (30.0, False),
        (70.0, False),
    ],
)
def test_the_predicate_is_a_pure_function_of_the_budget(budget, fits):
    import config

    assert config.sync_mode_fits_gateway(budget) is fits


def test_importing_config_in_synchronous_mode_does_not_raise():
    """GENERATE_ASYNC=false must stay usable at the shipped API_CLIENT_TIMEOUT.

    This is the escape hatch `sam local start-api` and the MiniStack E2E suite
    depend on. An import-time budget check would fire here -- the default budget
    is 70 against a ceiling of 29 -- and there would be no way to satisfy it.
    """
    env = {
        "GENERATE_ASYNC": "false",
        "AUTH_ENABLED": "false",
        "S3_BUCKET": "test-bucket",
    }
    with patch.dict(os.environ, env):
        os.environ.pop("API_CLIENT_TIMEOUT", None)
        config = _reload_config()

        assert config.generate_async is False
        assert config.api_client_timeout == 60.0
        # The combination the invariant calls invalid -- and it still imports.
        assert (
            config.sync_mode_fits_gateway(config.generate_dispatch_budget_seconds)
            is False
        )


def test_generate_async_defaults_to_true():
    env = {"AUTH_ENABLED": "false", "S3_BUCKET": "test-bucket"}
    with patch.dict(os.environ, env):
        os.environ.pop("GENERATE_ASYNC", None)
        config = _reload_config()

        assert config.generate_async is True
