"""
LLM integration for generating QA test case ideas from selected document
text.

Provider is chosen by LLM_PROVIDER in .env:
    - "mock"  : no network call, deterministic heuristic output. Default,
                so the project runs out of the box with zero setup.
    - "groq"  : real call to Groq's OpenAI-compatible chat completions API.

Both providers return the same shape (list[dict] matching schemas.TestCase)
so routers never need to know which one is active.
"""
import json
import logging
import re
import time

import httpx

from app.config import settings
from app.exceptions import LLMResponseError, LLMUnavailableError

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You are a senior QA engineer at a medical device company, writing test "
    "case ideas for a home blood pressure monitor. The device is safety-"
    "critical: a missed bug can mean patient harm, so favor concrete, "
    "verifiable checks over vague ones, and pay special attention to error "
    "conditions, boundary values, and safety-critical behavior described in "
    "the text. Every test case must be something a QA engineer could "
    "actually execute step by step, with an unambiguous pass/fail outcome."
)

USER_PROMPT_TEMPLATE = """Below is one or more sections from the CardioTrack CT-200 device manual, selected by a user for QA test case generation.

--- SELECTED CONTENT START ---
{content}
--- SELECTED CONTENT END ---

Generate between 3 and 5 QA test case ideas based ONLY on the content above. Do not invent behavior the text doesn't support.

Respond with ONLY a JSON array (no prose, no markdown fences), where each element has exactly these keys:
- "title": short name for the test case
- "steps": concrete, numbered steps to execute the test (as a single string)
- "expected_result": the specific, verifiable outcome that constitutes a pass
- "priority": one of "high", "medium", "low", based on patient-safety impact

Example of the expected shape (content unrelated, for format only):
[{{"title": "Battery low warning triggers E1", "steps": "1. Insert batteries below 20% charge. 2. Power on device.", "expected_result": "Display shows E1 within 3 seconds of power-on.", "priority": "high"}}]
"""

# Statuses worth retrying: rate-limited or a transient server-side hiccup.
# 4xx client errors other than 429 (bad request, auth failure) won't
# succeed on retry, so we fail fast on those instead of wasting 3 calls
# against a key that's simply wrong.
_RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}


def _extract_json_array(raw_text: str) -> list[dict]:
    """
    LLMs occasionally wrap JSON in prose or markdown fences despite
    instructions. Strip fences, then grab the first [...] block.
    """
    cleaned = raw_text.strip()
    cleaned = re.sub(r"^```(json)?", "", cleaned).strip()
    cleaned = re.sub(r"```$", "", cleaned).strip()

    match = re.search(r"\[.*\]", cleaned, re.DOTALL)
    if not match:
        raise LLMResponseError(
            "The AI provider's response didn't contain the expected JSON array."
        )
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError as exc:
        raise LLMResponseError(
            "The AI provider's response contained malformed JSON."
        ) from exc


def _mock_generate(content: str) -> list[dict]:
    """
    Deterministic stand-in used when no LLM key is configured. Produces
    plausible, content-aware test cases by keying off keywords actually
    present in the selected text, so the mock still *looks* tailored to
    what was selected rather than being a static fixture.
    """
    lower = content.lower()
    cases = []

    if "e3" in lower or "overpressure" in lower:
        cases.append({
            "title": "Overpressure triggers E3 and auto-deflates",
            "steps": "1. Simulate cuff pressure exceeding the safe limit during inflation. "
                     "2. Observe device display and cuff behavior.",
            "expected_result": "Device displays E3 and automatically stops inflation / deflates "
                                "within 2 seconds of detecting overpressure.",
            "priority": "high",
        })
    if "e1" in lower or "battery" in lower:
        cases.append({
            "title": "Low battery displays E1",
            "steps": "1. Insert batteries at a charge level below the documented low-battery "
                     "threshold. 2. Power on the device.",
            "expected_result": "Display shows error code E1 instead of attempting a measurement.",
            "priority": "medium",
        })
    if "e2" in lower or "cuff placement" in lower or "invalid" in lower:
        cases.append({
            "title": "Improper cuff placement is rejected",
            "steps": "1. Fit the cuff loosely/incorrectly per the manual's diagram. "
                     "2. Start a measurement.",
            "expected_result": "Device displays E2 and does not report a SYS/DIA reading.",
            "priority": "high",
        })
    if "300" in lower or "range" in lower or "mmhg" in lower:
        cases.append({
            "title": "Pressure reading at upper boundary (300 mmHg)",
            "steps": "1. Simulate a cuff pressure reading at exactly 300 mmHg. "
                     "2. Observe device response.",
            "expected_result": "Device handles the boundary value without crashing, incorrect "
                                "display, or unsafe inflation behavior.",
            "priority": "medium",
        })

    # Generic-but-concrete fallbacks, appended until we have at least 3
    # cases (the assignment requires 3-5 regardless of section length).
    fallbacks = [
        {
            "title": "Section content matches displayed/behavioral spec",
            "steps": "1. Review the selected manual section. 2. Exercise the described "
                     "feature on a physical or simulated device. 3. Compare actual "
                     "behavior to the documented behavior.",
            "expected_result": "Device behavior matches the manual section exactly; any "
                                "deviation is logged as a defect.",
            "priority": "low",
        },
        {
            "title": "Behavior is consistent across repeated attempts",
            "steps": "1. Repeat the scenario described in this section 5 times in a row. "
                     "2. Record the outcome of each attempt.",
            "expected_result": "The device behaves identically and correctly on every "
                                "repetition, with no intermittent failures.",
            "priority": "medium",
        },
        {
            "title": "Manual wording matches on-device/UI behavior exactly",
            "steps": "1. Compare the exact wording and thresholds in this manual section "
                     "against the actual device firmware/UI. 2. Note any mismatch.",
            "expected_result": "No discrepancy exists between documented and actual "
                                "device behavior for this section.",
            "priority": "low",
        },
    ]
    for fb in fallbacks:
        if len(cases) >= 3:
            break
        cases.append(fb)

    return cases[:5]


def _call_groq_once(content: str) -> httpx.Response:
    # Auth header is built fresh per attempt and never logged or included
    # in any exception we raise -- httpx's own exceptions can otherwise
    # echo the request, which would leak the key into logs/error responses.
    return httpx.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={"Authorization": f"Bearer {settings.groq_api_key}"},
        json={
            "model": settings.groq_model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": USER_PROMPT_TEMPLATE.format(content=content)},
            ],
            "temperature": 0.3,
        },
        timeout=settings.llm_timeout_seconds,
    )


def _groq_generate(content: str) -> list[dict]:
    if not settings.groq_api_key:
        # A config-time invariant (see Settings._require_key_for_groq)
        # should make this unreachable, but a defensive check here means
        # a key that's cleared at runtime fails clearly instead of
        # sending a request that Groq will reject anyway.
        raise LLMUnavailableError(
            "LLM_PROVIDER is set to 'groq' but GROQ_API_KEY is empty."
        )

    last_error: Exception | None = None
    max_attempts = settings.llm_max_retries + 1

    for attempt in range(1, max_attempts + 1):
        try:
            response = _call_groq_once(content)
        except httpx.TimeoutException as exc:
            last_error = exc
            logger.warning("Groq request timed out (attempt %d/%d)", attempt, max_attempts)
        except httpx.RequestError as exc:
            # DNS failure, connection refused, etc. -- never retriable in
            # a way more attempts within the same request would fix if
            # it's a persistent network issue, but transient blips do
            # happen, so we still retry within the configured budget.
            last_error = exc
            logger.warning("Groq request failed (attempt %d/%d): %s", attempt, max_attempts, type(exc).__name__)
        else:
            if response.status_code == 200:
                raw_text = response.json()["choices"][0]["message"]["content"]
                return _extract_json_array(raw_text)

            if response.status_code not in _RETRYABLE_STATUS_CODES:
                # Bad request / bad auth / model not found -- retrying
                # won't help, so surface immediately with a sanitized
                # message rather than the raw response body (which Groq
                # sometimes echoes the request into).
                raise LLMResponseError(
                    f"AI provider returned HTTP {response.status_code}, which is not retriable."
                )
            last_error = LLMResponseError(f"AI provider returned HTTP {response.status_code}.")
            logger.warning(
                "Groq returned retriable status %d (attempt %d/%d)",
                response.status_code, attempt, max_attempts,
            )

        if attempt < max_attempts:
            time.sleep(min(2 ** (attempt - 1) * 0.5, 4.0))  # 0.5s, 1s, 2s, ... capped

    if isinstance(last_error, LLMResponseError):
        raise last_error
    raise LLMUnavailableError(
        "Could not reach the AI provider after multiple attempts. Please try again shortly."
    ) from last_error


def generate_test_cases(content: str) -> tuple[list[dict], str, str]:
    """
    Returns (test_cases, model_name, provider_name).

    Raises LLMUnavailableError (network/timeout) or LLMResponseError
    (reachable but unusable response) on failure -- routers translate
    these into HTTP 502s via the handlers registered in main.py, rather
    than letting them surface as an opaque 500.
    """
    if settings.llm_provider == "groq":
        return _groq_generate(content), settings.groq_model, "groq"
    return _mock_generate(content), "mock-heuristic-v1", "mock"
