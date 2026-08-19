import json
import logging

import pytest

sentry_sdk = pytest.importorskip("sentry_sdk")


def test_json_formatter_emits_structured_line():
    from app.logging_conf import JsonFormatter

    fmt = JsonFormatter()
    record = logging.LogRecord(
        name="trimaura.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="hello %s",
        args=("world",),
        exc_info=None,
    )
    record.request_id = "req-123"
    record.job_id = 7
    record.stage = "RENDERING"

    payload = json.loads(fmt.format(record))
    assert payload["msg"] == "hello world"
    assert payload["request_id"] == "req-123"
    assert payload["job_id"] == 7
    assert payload["stage"] == "RENDERING"
    assert payload["level"] == "INFO"


def test_setup_logging_idempotent():
    from app.logging_conf import JsonFormatter, setup_logging

    setup_logging()
    root = logging.getLogger()
    setup_logging()  # second call must not add another handler
    formatters = [h.formatter for h in root.handlers if isinstance(h.formatter, JsonFormatter)]
    assert len(formatters) == 1


def test_init_sentry_noop_without_dsn():
    from app import observability

    observability._initialized = False
    observability.init_sentry()  # DSN empty in tests — must not raise
    assert observability._initialized is True


def test_capture_job_failure_sends_tagged_event(monkeypatch):
    from app import observability

    tags = {}

    class FakeScope:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def set_tag(self, k, v):
            tags[k] = v

    monkeypatch.setattr(sentry_sdk, "push_scope", lambda: FakeScope())
    messages = []
    monkeypatch.setattr(
        sentry_sdk, "capture_message", lambda m, level="error": messages.append(m)
    )

    observability.capture_job_failure(42, "RENDERING", "boom")
    assert tags == {"job_id": 42, "stage": "RENDERING"}
    assert messages and "42" in messages[0] and "RENDERING" in messages[0]
