# /markbook/tests/conftest.py
"""Tests run against a separate PostgreSQL database (TEST_DATABASE_URL), recreated for each test session.
Logs, drafts and backups are written to a throwaway folder, never the real one."""
import os
import tempfile

import pytest

_HOME = tempfile.mkdtemp(prefix="markbook-tests-")
os.environ["MARKBOOK_HOME"] = _HOME

from backend import db, migrate  # noqa: E402  (must come after MARKBOOK_HOME is set)

TEST_URL = os.getenv("TEST_DATABASE_URL", "postgresql+psycopg://markbook:markbook@localhost:5432/markbook_test")


@pytest.fixture(scope="session", autouse=True)
def database():
    db.init_engine(TEST_URL)
    db.drop_schema()
    with db.engine().begin() as c:
        c.exec_driver_sql("DROP TABLE IF EXISTS alembic_version")
    migrate.upgrade()                    # the tests build the schema the way the app does
    yield
    db.drop_schema()
    with db.engine().begin() as c:
        c.exec_driver_sql("DROP TABLE IF EXISTS alembic_version")


@pytest.fixture
def app_home():
    return _HOME