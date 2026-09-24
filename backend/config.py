# /markbook/backend/config.py
"""Application configuration, read from environment variables or a .env file."""
from __future__ import annotations

import os
from dataclasses import dataclass
from dotenv import load_dotenv

from .paths import PROJECT_ROOT, install_dir

# An installed copy keeps its .env beside markbook.exe; the source tree keeps it in the project.
for candidate in (install_dir() / ".env", PROJECT_ROOT / ".env"):
    if candidate.exists():
        load_dotenv(candidate)
        break


@dataclass(frozen=True)
class Config:
    database_url: str
    default_country_code: str


def get_config() -> Config:
    return Config(
        database_url=os.getenv("DATABASE_URL", "postgresql+psycopg://markbook:markbook@localhost:5432/markbook"),
        default_country_code=os.getenv("DEFAULT_COUNTRY_CODE", "255"),
    )