import os

def _b(v, d=False):
    return str(os.getenv(v, str(d))).lower() in ("1", "true", "yes", "on")

TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
TELEGRAM_CHAT_ID = int(os.environ["TELEGRAM_CHAT_ID"])

USE_OPENROUTER = _b("USE_OPENROUT", True)
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")

# Comma-separated list of models to try in order (failover).
_default_models = (
    "openai/gpt-oss-120b:free,"
    "z-ai/glm-4.5-air:free,"
    "moonshotai/kimi-k2.6:free,"
    "nvidia/nemotron-3-super-120b-a12b:free,"
    "google/gemma-4-31b-it:free"
)
OPENROUTER_MODELS = [
    m.strip() for m in os.getenv("OPENROUTER_MODELS", _default_models).split(",")
    if m.strip()
]

HF_TOKEN = os.getenv("HF_TOKEN", "")
HF_MODEL = os.getenv("HF_MODEL", "meta-llama/Llama-3.1-8B-Instruct")

GAS_WEB_APP_URL = os.getenv("GAS_WEB_APP_URL", "")
EMAIL_BRIDGE_SECRET = os.getenv("EMAIL_BRIDGE_SECRET", "")
GMAIL_USER = os.getenv("GMAIL_USER", "")
MAIL_APP_PASSWORD = os.getenv("MAIL_APP_PASSWORD", "")

REQUIRE_SEND_CONFIRMATION = _b("REQUIRE_SEND_CONFIRMATION", True)
DEFAULT_LANGUAGE = os.getenv("DEFAULT_LANGUAGE", "slovenian")
MAX_LEAD_PAGES = int(os.getenv("MAX_LEAD_PAGES", "3"))
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///hermes.db")

SEND_DELAY_SECONDS = float(os.getenv("SEND_DELAY_SECONDS", "4"))
DAILY_SEND_CAP = int(os.getenv("DAILY_SEND_CAP", "200"))
SENDER_NAME = os.getenv("SENDER_NAME", GMAIL_USER)

# Deployment mode
SPACE_HOST = os.getenv("SPACE_HOST", "")          # e.g. yourname-hermes.hf.space
WEBHOOK_PORT = int(os.getenv("PORT", "7860"))     # HF=7860, Railway sets PORT
USE_WEBHOOK = _b("USE_WEBHOOK", False)            # keep false on Railway (polling)
