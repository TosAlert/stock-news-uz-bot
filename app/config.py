from pathlib import Path
from dotenv import load_dotenv
import os

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

def env(name: str, default=None):
    return os.getenv(name, default)

TELEGRAM_BOT_TOKEN = env("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHANNEL_ID = env("TELEGRAM_CHANNEL_ID", "")
TELEGRAM_API_ID = env("TELEGRAM_API_ID", "")
TELEGRAM_API_HASH = env("TELEGRAM_API_HASH", "")
TELEGRAM_SESSION_STRING = env("TELEGRAM_SESSION_STRING", "")

ALPACA_API_KEY = env("ALPACA_API_KEY", "")
ALPACA_API_SECRET = env("ALPACA_API_SECRET", "")
ALPACA_PAGE_LIMIT = int(env("ALPACA_PAGE_LIMIT", "50"))

GEMINI_API_KEY = env("GEMINI_API_KEY", "")
GEMINI_MODEL = env("GEMINI_MODEL", "gemini-2.5-flash")

SEC_USER_AGENT = env("SEC_USER_AGENT", "StockNewsUZ/1.0 contact@example.com")

MIN_IMPACT_SCORE = int(env("MIN_IMPACT_SCORE", "4"))
MAX_TELEGRAM_CHARS = int(env("MAX_TELEGRAM_CHARS", "3800"))

# GitHub Actions schedule is 5 minutes minimum. We look back longer
# to tolerate schedule delays; published IDs prevent duplicates.
NEWS_LOOKBACK_MINUTES = int(env("NEWS_LOOKBACK_MINUTES", "60"))
MAX_AI_ITEMS_PER_RUN = int(env("MAX_AI_ITEMS_PER_RUN", "15"))
STATE_PATH = ROOT / env("STATE_PATH", "data/state.json")

WATCHLIST_FILE = ROOT / env("WATCHLIST_FILE", "config/watchlist.txt")
MACRO_RSS_URLS = [
    x.strip() for x in env("MACRO_RSS_URLS", "").split(";") if x.strip()
]
SEC_COMPANIES_FILE = ROOT / "config/sec_companies.json"

def watchlist():
    if not WATCHLIST_FILE.exists():
        return []
    return [
        x.strip().upper()
        for x in WATCHLIST_FILE.read_text(encoding="utf-8").splitlines()
        if x.strip() and not x.startswith("#")
    ]
