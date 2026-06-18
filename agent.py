import json
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from config import (USE_OPENROUTER, OPENROUTER_API_KEY, OPENROUTER_MODEL,
                    HF_TOKEN, HF_MODEL, DEFAULT_LANGUAGE, SENDER_NAME)


class RateLimited(Exception):
    pass


class LLMUnavailable(Exception):
    pass


SYSTEM = (
    "You are Hermes, a concise B2B outreach assistant. "
    f"Write professional, friendly emails in {DEFAULT_LANGUAGE}. "
    "Keep them under 130 words. No fake claims. "
    "Always return strict JSON: {\"subject\": \"...\", \"body\": \"...\"}."
)


@retry(
    retry=retry_if_exception_type(RateLimited),
    stop=stop_after_attempt(4),
    wait=wait_exponential(min=2, max=20),
    reraise=True,
)
def _openrouter(system: str, prompt: str) -> str:
    r = httpx.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers={"Authorization": f"Bearer {OPENROUTER_API_KEY}"},
        json={"model": OPENROUTER_MODEL,
              "messages": [{"role": "system", "content": system},
                           {"role": "user", "content": prompt}],
              "temperature": 0.6},
        timeout=60,
    )
    if r.status_code == 429:
        raise RateLimited("OpenRouter 429")
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]


@retry(
    stop=stop_after_attempt(2),
    wait=wait_exponential(min=1, max=6),
    reraise=True,
)
def _hf(system: str, prompt: str) -> str:
    # Current HF Router (OpenAI-compatible). Old api-inference endpoint is deprecated.
    r = httpx.post(
        "https://router.huggingface.co/v1/chat/completions",
        headers={"Authorization": f"Bearer {HF_TOKEN}"},
        json={"model": HF_MODEL,
              "messages": [{"role": "system", "content": system},
                           {"role": "user", "content": prompt}],
              "temperature": 0.6},
        timeout=90,
    )
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]


def _llm(prompt: str, system: str = SYSTEM) -> str:
    """Try OpenRouter, then HF. Raise LLMUnavailable if both fail."""
    errors = []
    if USE_OPENROUTER and OPENROUTER_API_KEY:
        try:
            return _openrouter(system, prompt)
        except Exception as e:
            errors.append(f"OpenRouter: {e}")
    if HF_TOKEN:
        try:
            return _hf(system, prompt)
        except Exception as e:
            errors.append(f"HF: {e}")
    raise LLMUnavailable(" | ".join(errors) or "no LLM configured")


def draft_email(lead: dict, offer: str) -> dict:
    prompt = (
        f"Business name: {lead.get('name')}\n"
        f"Website: {lead.get('website')}\n"
        f"Niche: {lead.get('niche')} | Location: {lead.get('location')}\n"
        f"My offer/goal: {offer}\n"
        f"Sign the email as: {SENDER_NAME}\n"
        "Include one short, polite call to action."
    )
    raw = _llm(prompt)
    try:
        start, end = raw.find("{"), raw.rfind("}")
        obj = json.loads(raw[start:end + 1])
        return {"subject": obj["subject"].strip(), "body": obj["body"].strip()}
    except Exception:
        return {"subject": f"Sodelovanje – {lead.get('name','')}".strip(),
                "body": raw.strip()}
