import re
import time
import random
import logging
import httpx
from duckduckgo_search import DDGS
from duckduckgo_search.exceptions import RatelimitException, DuckDuckGoSearchException
from config import MAX_LEAD_PAGES

log = logging.getLogger("hermes.leads")

EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")
SKIP = ("example.", "sentry.", "wixpress.", ".png", ".jpg", "@2x", "@sentry")


class LeadSearchError(Exception):
    pass


def _emails_from_html(html: str) -> set[str]:
    found = set(EMAIL_RE.findall(html))
    return {e for e in found if not any(s in e.lower() for s in SKIP)}


def _fetch(url: str) -> str:
    try:
        r = httpx.get(url, timeout=20, follow_redirects=True,
                      headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                                             "AppleWebKit/537.36 (KHTML, like Gecko) "
                                             "Chrome/120.0 Safari/537.36"})
        if r.status_code == 200 and "text/html" in r.headers.get("content-type", ""):
            return r.text
    except Exception:
        return ""
    return ""


def _ddg_search(query: str, max_results: int) -> list[dict]:
    """Search with retries + backoff to survive DDG rate limiting."""
    last_err = None
    for attempt in range(1, 4):
        try:
            with DDGS() as ddgs:
                return list(ddgs.text(query, region="si-sl",
                                      max_results=max_results))
        except (RatelimitException, DuckDuckGoSearchException) as e:
            last_err = e
            wait = attempt * 5 + random.uniform(0, 3)
            log.warning("DDG rate limited (attempt %s). Wait %.1fs.", attempt, wait)
            time.sleep(wait)
        except Exception as e:
            last_err = e
            break
    raise LeadSearchError(str(last_err))


def find_leads(niche: str, location: str, limit: int = 15) -> list[dict]:
    query = f"{niche} {location} kontakt email"
    leads, seen = [], set()

    hits = _ddg_search(query, MAX_LEAD_PAGES * 10)

    for hit in hits:
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
        time.sleep(random.uniform(0.5, 1.5))  # be gentle, avoid hammering
    return leads
