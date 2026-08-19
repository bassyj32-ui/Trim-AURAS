"""Structured JSON logging to stdout for the ``logging`` tree.

Modal surfaces container stdout/stderr, so a single JSON formatter per line
keeps every log machine-parseable without adding a dependency. Attach it at
import time (web container + workers) via ``setup_logging()``; records carry
optional context fields (request_id, job_id, stage, ...) that the formatter
picks up from ``logging`` ``extra``.
"""
import json
import logging
import sys

_EXTRA_FIELDS = (
    "request_id",
    "job_id",
    "stage",
    "method",
    "path",
    "status",
    "duration_ms",
)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%SZ"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        for key in _EXTRA_FIELDS:
            if hasattr(record, key):
                payload[key] = getattr(record, key)
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def setup_logging() -> None:
    """Attach the JSON handler to the root logger (idempotent)."""
    root = logging.getLogger()
    if any(isinstance(h.formatter, JsonFormatter) for h in root.handlers):
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root.addHandler(handler)
    root.setLevel(logging.INFO)
    # uvicorn ships its own handlers — don't double-log its records.
    for name in ("uvicorn", "uvicorn.access", "uvicorn.error"):
        logging.getLogger(name).propagate = False
