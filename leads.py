import re, httpx
from bs4 import BeautifulSoup  # noqa: F401  (available for richer parsing later)
from duckduckgo_search import DDGS
from config import MAX_LEAD_PAGES

EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")
SKIP = ("example.", "sentry.", "wixpress.", ".png", ".jpg", "@2x")

def _emails_from_html(html: str) -> set[str]:
    found = set(EMAIL_RE.findall(html))
    return {e for e in found if not any(s in e.lower() for s in SKIP)}

def _fetch(url: str) -> str:
    try:
        r = httpx.get(url, timeout=20, follow_redirects=True,
                      headers={"User-Agent": "Mozilla/5.0 HermesBot"})
        if r.status_code == 200 and "text/html" in r.headers.get("content-type", ""):
            return r.text
    except Exception:
        return ""
    return ""

def find_leads(niche: str, location: str, limit: int = 15) -> list[dict]:
    query = f"{niche} {location} kontakt email"
    results, leads, seen = [], [], set()
    with DDGS() as ddgs:
        for hit in ddgs.text(query, max_results=MAX_LEAD_PAGES * 10):
            results.append(hit)
    for hit in results:
        url = hit.get("href") or hit.get("url", "")
        name = hit.get("title", "")[:300]
        if not url:
            continue
        html = _fetch(url)
        emails = _emails_from_html(html)
        if not emails:
            emails |= _emails_from_html(_fetch(url.rstrip("/") + "/kontakt"))
        for e in emails:
            if e.lower() in seen:
                continue
            seen.add(e.lower())
            leads.append({"name": name, "email": e, "website": url,
                          "niche": niche, "location": location})
            if len(leads) >= limit:
                return leads
    return leads
