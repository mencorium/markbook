# /markbook/tests/conftest.py
"""Tests run against a separate PostgreSQL database (TEST_DATABASE_URL), recreated for each test session."""
import os

import pytest

from backend import db

TEST_URL = os.getenv("TEST_DATABASE_URL", "postgresql+psycopg://markbook:markbook@localhost:5432/markbook_test")


@pytest.fixture(scope="session", autouse=True)
def database():
    db.init_engine(TEST_URL)
    db.drop_schema()
    db.create_schema()
    yield
    db.drop_schema()