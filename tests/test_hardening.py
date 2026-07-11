"""
Tests for the reliability/security hardening added on top of the
original implementation:
  - LLM retry/backoff and error classification (unit-level, mocking httpx)
  - Upload size enforcement (API-level)
  - Config fails fast on invalid settings (unit-level)

Kept in a separate file from test_api.py so the original end-to-end
suite stays untouched and it's obvious, file-by-file, what's newly
covered.

Run with: pytest -v
"""
import httpx
import pytest

from app.exceptions import LLMResponseError, LLMUnavailableError


# ---------- API-level: upload size limit ----------
# `client` comes from tests/conftest.py.

def test_upload_rejects_oversized_file(client, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "max_upload_size_bytes", 1024)  # 1 KB, for a fast test
    oversized_content = ("# Title\n" + ("x" * 2000)).encode("utf-8")

    resp = client.post(
        "/documents/upload",
        files={"file": ("big.md", oversized_content, "text/markdown")},
    )
    assert resp.status_code == 413
    assert "limit" in resp.json()["detail"].lower()


def test_upload_rejects_non_markdown_extension(client):
    resp = client.post(
        "/documents/upload",
        files={"file": ("manual.txt", b"# Title\nbody", "text/plain")},
    )
    assert resp.status_code == 400


def test_response_includes_request_id_header(client):
    resp = client.get("/")
    assert "x-request-id" in resp.headers


def test_error_envelope_is_consistent_shape(client):
    # A 404 (NotFoundError) and a 400 (ValidationError) both go through
    # the same app_error_handler, so both must return {"detail": "..."}.
    not_found = client.get("/nodes/999999")
    bad_selection = client.post("/selections", json={"node_ids": [999999]})
    assert not_found.status_code == 404
    assert bad_selection.status_code == 400
    assert set(not_found.json().keys()) == {"detail"}
    assert set(bad_selection.json().keys()) == {"detail"}


# ---------- Unit-level: LLM retry/backoff and error classification ----------

class _FakeResponse:
    def __init__(self, status_code: int, json_body: dict | None = None):
        self.status_code = status_code
        self._json_body = json_body or {}

    def json(self):
        return self._json_body


def test_groq_retries_on_transient_failure_then_succeeds(monkeypatch):
    """A 503 followed by a 200 should succeed without the caller ever
    seeing an error -- this is the retry/backoff path in app/llm.py."""
    from app import llm

    monkeypatch.setattr(llm.settings, "llm_provider", "groq")
    monkeypatch.setattr(llm.settings, "groq_api_key", "test-key")
    monkeypatch.setattr(llm.settings, "llm_max_retries", 2)
    monkeypatch.setattr(llm.time, "sleep", lambda _: None)  # skip real backoff delay in tests

    good_body = {
        "choices": [{"message": {"content": '[{"title": "t", "steps": "s", '
                                              '"expected_result": "e", "priority": "high"}]'}}]
    }
    responses = [_FakeResponse(503), _FakeResponse(200, good_body)]

    def fake_call(content):
        return responses.pop(0)

    monkeypatch.setattr(llm, "_call_groq_once", fake_call)

    cases, model, provider = llm.generate_test_cases("some selected content")
    assert provider == "groq"
    assert cases[0]["title"] == "t"


def test_groq_gives_up_after_max_retries(monkeypatch):
    from app import llm

    monkeypatch.setattr(llm.settings, "llm_provider", "groq")
    monkeypatch.setattr(llm.settings, "groq_api_key", "test-key")
    monkeypatch.setattr(llm.settings, "llm_max_retries", 1)
    monkeypatch.setattr(llm.time, "sleep", lambda _: None)

    monkeypatch.setattr(llm, "_call_groq_once", lambda content: _FakeResponse(503))

    with pytest.raises(LLMResponseError):
        llm.generate_test_cases("some selected content")


def test_groq_does_not_retry_non_retriable_status(monkeypatch):
    """A 401 (bad key) should fail immediately, not burn through the
    retry budget -- retrying an auth failure can't ever succeed."""
    from app import llm

    monkeypatch.setattr(llm.settings, "llm_provider", "groq")
    monkeypatch.setattr(llm.settings, "groq_api_key", "test-key")
    monkeypatch.setattr(llm.settings, "llm_max_retries", 3)

    call_count = {"n": 0}

    def fake_call(content):
        call_count["n"] += 1
        return _FakeResponse(401)

    monkeypatch.setattr(llm, "_call_groq_once", fake_call)

    with pytest.raises(LLMResponseError):
        llm.generate_test_cases("some selected content")
    assert call_count["n"] == 1


def test_groq_network_failure_raises_unavailable_error(monkeypatch):
    from app import llm

    monkeypatch.setattr(llm.settings, "llm_provider", "groq")
    monkeypatch.setattr(llm.settings, "groq_api_key", "test-key")
    monkeypatch.setattr(llm.settings, "llm_max_retries", 0)
    monkeypatch.setattr(llm.time, "sleep", lambda _: None)

    def fake_call(content):
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(llm, "_call_groq_once", fake_call)

    with pytest.raises(LLMUnavailableError):
        llm.generate_test_cases("some selected content")


def test_malformed_json_from_llm_raises_response_error(monkeypatch):
    from app import llm

    monkeypatch.setattr(llm.settings, "llm_provider", "groq")
    monkeypatch.setattr(llm.settings, "groq_api_key", "test-key")

    bad_body = {"choices": [{"message": {"content": "here is your answer: not json at all"}}]}
    monkeypatch.setattr(llm, "_call_groq_once", lambda content: _FakeResponse(200, bad_body))

    with pytest.raises(LLMResponseError):
        llm.generate_test_cases("some selected content")


# ---------- Unit-level: config fails fast ----------

def test_settings_reject_groq_without_api_key(monkeypatch):
    from app.config import Settings

    monkeypatch.setenv("LLM_PROVIDER", "groq")
    monkeypatch.setenv("GROQ_API_KEY", "")
    with pytest.raises(ValueError):
        Settings(_env_file=None)


def test_settings_reject_unknown_llm_provider(monkeypatch):
    from app.config import Settings

    monkeypatch.setenv("LLM_PROVIDER", "chatgpt")
    with pytest.raises(ValueError):
        Settings(_env_file=None)
