"""The application logs at INFO; the SDKs it happens to import do not.

``utils/logger.py`` set the **root** logger to INFO at import. botocore,
urllib3, the OpenAI SDK and google-genai all propagate to root, so their INFO
records were emitted to CloudWatch on every invocation -- ingestion cost and
retention against a 30-day policy, for records nobody reads.

The mechanism is worth stating because it is easy to get backwards: a record's
level is checked against the *emitting* logger's effective level, and then the
record is handed to every ancestor's handlers regardless of those ancestors'
levels. So a named logger at INFO still reaches the handler the Lambda runtime
installs on root, while root at WARNING silences the SDK loggers that have no
level of their own. Both halves are needed, which is why both are asserted
here rather than assumed.
"""

from __future__ import annotations

import json
import logging
import os

os.environ.setdefault("AUTH_ENABLED", "false")


def test_importing_the_logger_does_not_leave_root_at_info():
    """The checklist item, stated as a test: root must not be at INFO."""
    import utils.logger  # noqa: F401

    assert logging.getLogger().level != logging.INFO
    assert logging.getLogger().level >= logging.WARNING


def test_a_runtime_that_puts_root_at_info_is_corrected_on_import():
    """The half of the fix that Python's own defaults hide.

    CPython's default root level is already WARNING, so
    test_importing_the_logger_does_not_leave_root_at_info passes whether or
    not this module sets it -- verified by mutation. The Lambda Python
    runtime has in some versions installed its handler and set root to INFO,
    and inheriting that would ship every SDK's INFO records, which is the
    whole defect. Putting root at INFO first is the only way to tell the two
    apart.
    """
    import importlib

    import utils.logger

    root = logging.getLogger()
    previous = root.level
    try:
        root.setLevel(logging.INFO)
        importlib.reload(utils.logger)
        assert root.level == logging.WARNING
    finally:
        root.setLevel(previous)


def test_the_application_logger_is_at_info():
    import utils.logger

    assert utils.logger.logger.name != "root"
    assert utils.logger.logger.getEffectiveLevel() == logging.INFO


def test_a_botocore_info_record_is_not_emitted(caplog):
    """The records that were being paid for."""
    import utils.logger  # noqa: F401

    with caplog.at_level(logging.DEBUG, logger="pixel_prompt"):
        logging.getLogger("botocore.endpoint").info("Making request to bedrock")
        logging.getLogger("urllib3.connectionpool").info(
            "Starting new HTTPS connection"
        )

    assert [r.getMessage() for r in caplog.records] == []


def test_a_botocore_warning_is_still_emitted(caplog):
    """Silencing INFO must not silence the SDK records that matter."""
    import utils.logger  # noqa: F401

    with caplog.at_level(logging.WARNING):
        logging.getLogger("botocore.endpoint").warning("retrying")

    assert any("retrying" in r.getMessage() for r in caplog.records)


class TestStructuredLoggerStillWorks:
    """handle_log fans arbitrary client metadata through this; do not regress
    the JSON shape."""

    def _records(self, caplog, level, fn, *args, **kwargs):
        caplog.clear()
        with caplog.at_level(logging.DEBUG):
            fn(*args, **kwargs)
        return [
            json.loads(r.getMessage()) for r in caplog.records if r.levelno == level
        ]

    def test_info_still_emits(self, caplog):
        from utils.logger import StructuredLogger

        entries = self._records(caplog, logging.INFO, StructuredLogger.info, "hello")
        assert len(entries) == 1
        assert entries[0]["level"] == "INFO"
        assert entries[0]["message"] == "hello"
        assert "timestamp" in entries[0]

    def test_warning_still_emits(self, caplog):
        from utils.logger import StructuredLogger

        entries = self._records(
            caplog, logging.WARNING, StructuredLogger.warning, "careful"
        )
        assert len(entries) == 1
        assert entries[0]["level"] == "WARNING"

    def test_error_still_emits(self, caplog):
        from utils.logger import StructuredLogger

        entries = self._records(caplog, logging.ERROR, StructuredLogger.error, "broken")
        assert len(entries) == 1
        assert entries[0]["level"] == "ERROR"

    def test_correlation_id_and_metadata_shape_are_unchanged(self, caplog):
        from utils.logger import StructuredLogger

        entries = self._records(
            caplog,
            logging.INFO,
            StructuredLogger.info,
            "with metadata",
            correlation_id="corr-1",
            sessionId="s1",
        )
        assert entries[0]["correlationId"] == "corr-1"
        assert entries[0]["metadata"] == {"sessionId": "s1"}


def test_config_can_still_import_the_logger_at_module_scope():
    """config.py imports StructuredLogger inside its CORS warning.

    A circular-import mistake here fails at deploy, not in a unit test that
    imports config first -- so import it the other way round.
    """
    import importlib

    import utils.logger

    importlib.reload(utils.logger)
    import config

    importlib.reload(config)
    assert config.cors_allowed_origin is not None
