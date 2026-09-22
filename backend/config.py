# /markbook/backend/config.py
"""Application configuration, read from environment variables or a .env file."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")


@dataclass(frozen=True)
class Config:
    database_url: str
    default_country_code: str


def get_config() -> Config:
    return Config(
        database_url=os.getenv("DATABASE_URL", "postgresql+psycopg://markbook:markbook@localhost:5432/markbook"),
        default_country_code=os.getenv("DEFAULT_COUNTRY_CODE", "255"),
    )