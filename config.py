"""Central tuning and environment configuration for Demand Seeker."""
from __future__ import annotations

import os
import csv
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


def env_bool(name: str, default: bool) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


def env_list(name: str, default: str) -> list[str]:
    """Parse a comma-separated environment value while honoring CSV quotes."""
    return [value.strip() for value in next(csv.reader([os.getenv(name, default)])) if value.strip()]


DAYS_SHORT = int(os.getenv("DAYS_SHORT", "7"))
DAYS_LONG = int(os.getenv("DAYS_LONG", "30"))
MIN_OBSERVATIONS_FOR_HIGH_CONFIDENCE = int(os.getenv("MIN_OBSERVATIONS_FOR_HIGH_CONFIDENCE", "50"))

# Demand weights must total 1.0. Scoring code normalizes them if they are changed.
DEMAND_WEIGHT_VOLUME = float(os.getenv("DEMAND_WEIGHT_VOLUME", "0.30"))
DEMAND_WEIGHT_GROWTH = float(os.getenv("DEMAND_WEIGHT_GROWTH", "0.20"))
DEMAND_WEIGHT_BUDGET = float(os.getenv("DEMAND_WEIGHT_BUDGET", "0.20"))
DEMAND_WEIGHT_RECENCY = float(os.getenv("DEMAND_WEIGHT_RECENCY", "0.15"))
DEMAND_WEIGHT_SOURCE_DIVERSITY = float(os.getenv("DEMAND_WEIGHT_SOURCE_DIVERSITY", "0.15"))

COLLECT_UPWORK = env_bool("COLLECT_UPWORK", True)
COLLECT_REDDIT = env_bool("COLLECT_REDDIT", True)
COLLECT_GOOGLE_TRENDS = env_bool("COLLECT_GOOGLE_TRENDS", False)

UPWORK_CSV_PATH = Path(os.getenv("UPWORK_CSV_PATH", str(BASE_DIR / "data/raw/upwork.csv")))
REDDIT_QUERIES = env_list(
    "REDDIT_QUERIES",
    '"need a developer","website help","API integration","website broken","automation help"',
)
REDDIT_LIMIT_PER_QUERY = int(os.getenv("REDDIT_LIMIT_PER_QUERY", "25"))
REDDIT_USER_AGENT = os.getenv("REDDIT_USER_AGENT", "demand-seeker/1.0 market-research")
GOOGLE_TRENDS_GEO = os.getenv("GOOGLE_TRENDS_GEO", "US")
GOOGLE_TRENDS_KEYWORDS = env_list(
    "GOOGLE_TRENDS_KEYWORDS",
    "API integration,AI chatbot,website speed optimization,WordPress fix,Stripe integration",
)

DATABASE_PATH = Path(os.getenv("DATABASE_PATH", str(BASE_DIR / "data/demand_seeker.sqlite3")))
PROCESSED_DIR = Path(os.getenv("PROCESSED_DIR", str(BASE_DIR / "data/processed")))
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
LOG_PATH = BASE_DIR / "logs/demand_seeker.log"

CRM_BASE_URL = os.getenv("CRM_BASE_URL", "").rstrip("/")
BOT_API_SECRET = os.getenv("BOT_API_SECRET", "")
CRM_SYNC_ENABLED = env_bool("CRM_SYNC_ENABLED", False)
CRM_MARKET_DEMAND_ENDPOINT = os.getenv("CRM_MARKET_DEMAND_ENDPOINT", "/api/bot/market-demand")
