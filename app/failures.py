"""Transient-vs-permanent failure classification.

Shared by the pipeline orchestrator (so transient failures never mark a job
FAILED — that would fire a 'Failed' push and stop the frontend's SSE watcher
before Modal's retries=1 gets a chance to re-run it) and by the Modal worker
wrappers (which decide whether to re-raise for Modal's automatic retry or
swallow permanent errors so a bad source URL never burns a re-run).

Permanent errors are things a re-run will never fix: bad/unsupported source
URL, "Couldn't pick any watchable clips", invalid trim bounds, job/clip not
found. Transient errors are infra blips worth exactly one retry: timeouts,
connection resets, rate limits, 5xx, Modal container loss, tenacity
exhaustion after the in-pipeline AI retries.
"""

import httpx
import tenacity

_TRANSIENT_MARKERS = (
    "timeout", "timed out", "connection", "temporarily", "rate limit",
    "too many requests", " 429", " 500", " 502", " 503", " 504",
    "retry", "socket", "econnreset", "econnrefused", "ssl",
)


def is_transient(exc: BaseException) -> bool:
    """True if an exception is worth re-running the pipeline once."""
    if isinstance(exc, (httpx.HTTPError, TimeoutError, ConnectionError, OSError)):
        return True
    if isinstance(exc, tenacity.RetryError):
        return True
    # Modal infra errors (RemoteError, FunctionTimeoutError, ...) are transient.
    if type(exc).__module__.startswith("modal"):
        return True
    msg = str(exc).lower()
    return any(m in msg for m in _TRANSIENT_MARKERS)