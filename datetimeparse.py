from datetime import timedelta
import dateparser

_SETTINGS = {
    "PREFER_DATES_FROM": "future",
    "RETURN_AS_TIMEZONE_AWARE": False,
    "TIMEZONE": "Europe/Ljubljana",
}
_LANGS = ["sl", "en"]

def parse_when(text: str) -> tuple[str | None, str | None]:
    if not text:
        return None, None
    dt = dateparser.parse(text, languages=_LANGS, settings=_SETTINGS)
    if not dt:
        return None, None
    return dt.isoformat(), (dt + timedelta(minutes=30)).isoformat()
