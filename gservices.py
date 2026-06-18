import httpx
from config import GAS_WEB_APP_URL, EMAIL_BRIDGE_SECRET

def _post(payload: dict) -> dict:
    payload["secret"] = EMAIL_BRIDGE_SECRET
    r = httpx.post(GAS_WEB_APP_URL, json=payload, timeout=45)
    r.raise_for_status()
    return r.json()

def append_leads_to_sheet(rows: list[dict]) -> dict:
    return _post({"action": "append_leads", "rows": rows})

def create_calendar_event(title: str, start_iso: str, end_iso: str | None = None,
                          description: str = "", location: str = "") -> dict:
    return _post({"action": "create_event", "title": title, "start": start_iso,
                  "end": end_iso, "description": description, "location": location})
 