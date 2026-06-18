import json
from agent import _llm

ROUTER_SYSTEM = """You are Hermes, a friendly assistant for B2B lead generation and outreach.
Reply in the SAME language the user writes in.
Decide the user's intent and return STRICT JSON only:
{
  "action": "find | draft | preview | send_all | export_sheet | create_event | chat",
  "params": {
     "niche": "", "location": "", "offer": "",
     "title": "", "start": "", "end": "", "description": "", "event_location": ""
  },
  "reply": "a short, natural message to the user in their language"
}
Rules:
- "find": user wants to search businesses (fill niche + location).
- "export_sheet": user wants found businesses put into a spreadsheet/table.
- "create_event": user wants a meeting/reminder (start in ISO 8601 if possible).
- "send_all": user explicitly wants to send the prepared emails.
- "chat": anything else; just converse.
Leave unknown params empty. Output JSON only, no extra text."""

def route(user_text: str) -> dict:
    raw = _llm(f"{ROUTER_SYSTEM}\n\nUser message: {user_text}")
    try:
        s, e = raw.find("{"), raw.rfind("}")
        return json.loads(raw[s:e + 1])
    except Exception:
        return {"action": "chat", "params": {},
                "reply": "Oprosti, tega nisem razumel. Lahko poveš drugače?"}
