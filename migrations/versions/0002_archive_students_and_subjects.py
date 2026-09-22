# /markbook/migrations/versions/0002_archive_students_and_subjects.py
"""archive students and subjects

Archiving hides a student or subject from class lists, results and exports without
deleting their marks, so an accidental removal can be undone.

Revision ID: 0002_archive
Revises: 0001_initial
Created: 2026-09-22 23:26:09.179378
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


def _has(table: str, column: str) -> bool:
    return column in {c["name"] for c in inspect(op.get_bind()).get_columns(table)}


revision = '0002_archive'
down_revision = '0001_initial'
branch_labels = None
depends_on = None


def upgrade() -> None:
    for table in ("students", "subjects"):
        if not _has(table, "archived_at"):
            op.add_column(table, sa.Column('archived_at', sa.DateTime(), nullable=True))


def downgrade() -> None:
    for table in ("subjects", "students"):
        if _has(table, "archived_at"):
            op.drop_column(table, 'archived_at')