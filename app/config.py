"""Settings loaded from .env."""
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")


def _bool(key: str, default: bool = False) -> bool:
    return os.getenv(key, str(default)).strip().lower() in {"1", "true", "yes"}


def _int(key: str, default: int) -> int:
    try:
        return int(os.getenv(key, default))
    except (TypeError, ValueError):
        return default


# --- credentials -----------------------------------------------------------
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
REED_API_KEY = os.getenv("REED_API_KEY", "")
ADZUNA_APP_ID = os.getenv("ADZUNA_APP_ID", "")
ADZUNA_APP_KEY = os.getenv("ADZUNA_APP_KEY", "")
APIFY_TOKEN = os.getenv("APIFY_TOKEN", "")

# --- profile ---------------------------------------------------------------
HOME_POSTCODE = os.getenv("HOME_POSTCODE", "LE11")
MAX_COMMUTE_MILES = _int("MAX_COMMUTE_MILES", 50)
SALARY_FLOOR = _int("SALARY_FLOOR", 28000)
NEEDS_SPONSORSHIP = _bool("NEEDS_SPONSORSHIP")
HAS_CLEARANCE = _bool("HAS_CLEARANCE")

# --- pipeline --------------------------------------------------------------
MATCH_THRESHOLD = _int("MATCH_THRESHOLD", 55)
ALIGNMENT_TARGET = _int("ALIGNMENT_TARGET", 90)
DAILY_JOB_CAP = _int("DAILY_JOB_CAP", 80)
LLM_MODEL = os.getenv("LLM_MODEL", "claude-sonnet-5")
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{ROOT / 'data' / 'jobs.db'}")

# --- paths -----------------------------------------------------------------
DATA_DIR = ROOT / "data"
CV_DIR = DATA_DIR / "cv_variants"
OUTPUT_DIR = DATA_DIR / "generated"
MASTER_PROFILE = DATA_DIR / "MASTER_SKILLS_PROFILE.md"

for _d in (DATA_DIR, CV_DIR, OUTPUT_DIR):
    _d.mkdir(parents=True, exist_ok=True)

# Cost per unit, used for the running total on the dashboard.
APIFY_COST_PER_RESULT = 0.0004
APIFY_COST_PER_START = 0.001
