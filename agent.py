import json, httpx
from tenacity import retry, stop_after_attempt, wait_exponential
from config import (USE_OPENROUTER, OPENROUTER_API_KEY, OPENROUTER_MODEL,
                    HF_TOKEN, HF_MODEL, DEFAULT_LANGUAGE, SENDER_NAME)

SYSTEM = (
    "You are Hermes, a concise B2B outreach assistant. "
    f"Write professional, friendly emails in {DEFAULT_LANGUAGE}. "
    "Keep them under 130 words. No fake claims. "
    "Always return strict JSON: {\"subject\": \"...\", \"body\": \"...\"}."
)

@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=8))
def _openrouter(prompt: str) -> str:
    r = httpx.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers={"Authorization": f"Bearer {OPENROUTER_API_KEY}"},
        json={"model": OPENROUTER_MODEL,
              "messages": [{"role": "system", "content": SYSTEM},
                           {"role": "user", "content": prompt}],
              "temperature": 0.6},
        timeout=60,
    )
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]

@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=8))
def _hf(prompt: str) -> str:
    r = httpx.post(
        f"https://api-inference.huggingface.co/models/{HF_MODEL}",
        headers={"Authorization": f"Bearer {HF_TOKEN}"},
        json={"inputs": f"{SYSTEM}\n\n{prompt}",
              "parameters": {"max_new_tokens": 400, "return_full_text": False}},
        timeout=90,
    )
    r.raise_for_status()
    data = r.json()
    return data[0]["generated_text"] if isinstance(data, list) else str(data)

def _llm(prompt: str) -> str:
    if USE_OPENROUTER and OPENROUTER_API_KEY:
        try:
            return _openrouter(prompt)
        except Exception:
            pass
    return _hf(prompt)

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
 