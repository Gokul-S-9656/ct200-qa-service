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
import re

import httpx

from app.config import settings

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
        raise ValueError(f"No JSON array found in LLM response: {raw_text[:200]}")
    return json.loads(match.group(0))


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


def _groq_generate(content: str) -> list[dict]:
    if not settings.groq_api_key:
        raise RuntimeError(
            "LLM_PROVIDER is set to 'groq' but GROQ_API_KEY is empty. "
            "Add a key to .env or set LLM_PROVIDER=mock."
        )

    response = httpx.post(
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
        timeout=30.0,
    )
    response.raise_for_status()
    raw_text = response.json()["choices"][0]["message"]["content"]
    return _extract_json_array(raw_text)


def generate_test_cases(content: str) -> tuple[list[dict], str, str]:
    """
    Returns (test_cases, model_name, provider_name).
    """
    if settings.llm_provider == "groq":
        return _groq_generate(content), settings.groq_model, "groq"
    return _mock_generate(content), "mock-heuristic-v1", "mock"
