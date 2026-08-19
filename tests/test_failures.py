import pytest

from app.failures import is_transient


class TestFailureClassification:
    def test_http_errors_transient(self):
        import httpx
        assert is_transient(httpx.ConnectError("boom"))
        assert is_transient(httpx.TimeoutException("slow"))

    def test_timeout_and_connection_transient(self):
        assert is_transient(TimeoutError("timed out"))
        assert is_transient(ConnectionError("refused"))

    def test_tenacity_retryerror_transient(self):
        import tenacity
        f = tenacity.Future(attempt_number=1)
        assert is_transient(tenacity.RetryError(f))

    def test_marker_in_message_transient(self):
        assert is_transient(RuntimeError("HTTP 503 Service Unavailable"))
        assert is_transient(RuntimeError("connection reset by peer"))
        assert is_transient(RuntimeError("rate limit exceeded"))

    def test_permanent_valueerror(self):
        assert not is_transient(ValueError("Job 12 not found after 5 attempts"))
        assert not is_transient(ValueError("Clip 99 not found"))
        assert not is_transient(ValueError("start must be < end"))

    def test_permanent_runtime_errors(self):
        assert not is_transient(RuntimeError("Couldn't pick any watchable clips from this video"))
        assert not is_transient(RuntimeError("Job has no saved transcript"))
        assert not is_transient(RuntimeError("Frame.io share access denied: permission"))


class TestTransientMarkerGuardrails:
    """Regression guard: permanent pipeline messages must never match transient."""

    def test_no_false_positives_on_key_messages(self):
        permanent = [
            "Couldn't pick any watchable clips from this video. Use a video with clear speech.",
            "Job has no saved transcript. Run the initial pipeline first.",
            "New boundaries must be inside the original clip (0.00s–10.00s)",
            "Clip 42 not found",
            "Job 7 not found after 5 attempts",
            "Source must be an http(s) video link",
            "YouTube is disabled at this stage",
        ]
        for msg in permanent:
            assert not is_transient(RuntimeError(msg)), f"false positive: {msg}"