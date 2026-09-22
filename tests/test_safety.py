# /markbook/tests/test_safety.py
"""Migrations, backups and autosaved drafts — the features that protect a term's marks."""
import datetime as dt

import pytest
from sqlalchemy import inspect

from backend import db, migrate, seed
from backend.services import backup as BK
from backend.services import drafts
from backend.services import records as R
from backend.services.analytics import Gradebook


def test_schema_is_at_head_and_has_every_table():
    assert not migrate.pending()
    assert migrate.current_revision() == migrate.head_revision()
    tables = set(inspect(db.engine()).get_table_names())
    assert {"students", "marks", "questions", "attendance_days", "alembic_version"} <= tables


def test_database_made_before_migrations_is_stamped_not_rebuilt():
    """A database created by the old create_schema() keeps its data and joins the migration history."""
    db.drop_schema()
    with db.engine().begin() as c:
        c.exec_driver_sql("DROP TABLE IF EXISTS alembic_version")
    db.create_schema()                                   # pre-migrations state: tables, no history
    stu = R.save_student(None, name="Legacy Student", class_name="Legacy Class")
    assert migrate.current_revision() is None

    assert migrate.upgrade() == migrate.head_revision()
    assert not migrate.pending()
    assert Gradebook.load().students[stu.id].name == "Legacy Student"      # data survived


def test_migration_blocked_by_another_connection_fails_fast(monkeypatch):
    """A lock held elsewhere must produce a message, not a startup that hangs for ever."""
    from sqlalchemy import text
    monkeypatch.setattr(migrate, "LOCK_TIMEOUT", "1s")
    with db.engine().begin() as c:
        c.exec_driver_sql("DROP TABLE IF EXISTS alembic_version")
    blocker = db.engine().connect()
    try:
        blocker.execute(text("CREATE TABLE IF NOT EXISTS alembic_version (version_num varchar(32) primary key)"))
        blocker.execute(text("LOCK TABLE alembic_version IN ACCESS EXCLUSIVE MODE"))
        with pytest.raises(migrate.MigrationError, match="in use by another program"):
            migrate.upgrade()
    finally:
        blocker.close()
    assert migrate.upgrade() == migrate.head_revision()      # fine again once the other program lets go


@pytest.mark.skipif(not BK.tools_available(), reason="pg_dump/pg_restore are not installed")
def test_backup_then_restore_brings_data_back(tmp_path):
    seed.add_sample(seed=3)
    before = len(Gradebook.load().students)
    dump = BK.backup(tmp_path)
    assert dump.exists() and dump.stat().st_size > 1000

    doomed = [s.id for s in Gradebook.load().students.values()][:5]
    R.delete_students(doomed)
    assert len(Gradebook.load().students) == before - 5

    BK.restore(dump)
    after = Gradebook.load().students
    assert len(after) == before and all(sid in after for sid in doomed)

    for _ in range(3):
        BK.backup(tmp_path)
    assert BK.prune(keep=2, folder=tmp_path) == 2 and len(BK.list_backups(tmp_path)) == 2
    seed.remove_sample()


def test_backup_reports_a_readable_error_when_the_tool_is_missing(monkeypatch):
    monkeypatch.setattr(BK, "find_tool", lambda name: None)
    with pytest.raises(BK.BackupError, match="pg_dump"):
        BK.backup()


def test_drafts_survive_a_crash_and_are_cleared_on_save():
    drafts.delete_draft(999)
    assert drafts.load_draft(999) is None

    drafts.save_draft(999, "paper", {7: {1: 8.0, 2: None}, 9: {1: 3.0}})
    back = drafts.load_draft(999)                        # keys come back as integers, not strings
    assert back["kind"] == "paper" and back["values"][7][1] == 8.0 and back["values"][9][1] == 3.0
    assert isinstance(back["saved_at"], dt.datetime)

    drafts.delete_draft(999)
    assert drafts.load_draft(999) is None


def test_unreadable_draft_is_ignored_rather_than_crashing(app_home):
    from backend.paths import drafts_dir
    (drafts_dir() / "assessment-1234.json").write_text("{not json", encoding="utf-8")
    assert drafts.load_draft(1234) is None
    drafts.delete_draft(1234)