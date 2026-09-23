# /markbook/migrations/versions/0004_terms.py
"""terms and academic years

Marks now belong to a term. Everything recorded before this migration is put into one term
(named from the Term setting, spanning the dates actually used), so no existing mark is orphaned.

Revision ID: d51be1bfb672
Revises: 0003_audit
Created: 2026-09-23 00:12:24.612626
"""
from alembic import op
import sqlalchemy as sa


revision = '0004_terms'
down_revision = '0003_audit'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('terms',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=60), nullable=False),
    sa.Column('year', sa.String(length=20), nullable=False),
    sa.Column('starts_on', sa.Date(), nullable=False),
    sa.Column('ends_on', sa.Date(), nullable=False),
    sa.Column('weight', sa.Numeric(precision=7, scale=2, asdecimal=False), nullable=False),
    sa.Column('is_sample', sa.Boolean(), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('name', 'year')
    )
    op.add_column('assessments', sa.Column('term_id', sa.Integer(), nullable=True))
    op.create_index(op.f('ix_assessments_term_id'), 'assessments', ['term_id'], unique=False)
    op.create_foreign_key(None, 'assessments', 'terms', ['term_id'], ['id'], ondelete='RESTRICT')
    op.add_column('attendance_days', sa.Column('term_id', sa.Integer(), nullable=True))
    op.create_index(op.f('ix_attendance_days_term_id'), 'attendance_days', ['term_id'], unique=False)
    op.create_foreign_key(None, 'attendance_days', 'terms', ['term_id'], ['id'], ondelete='RESTRICT')
    op.add_column('classes', sa.Column('year', sa.String(length=20), nullable=False, server_default=''))
    op.add_column('classes', sa.Column('rollover', sa.String(length=10), nullable=False, server_default='promote'))
    _backfill()


def _backfill() -> None:
    """Put existing work into a first term, so nothing loses its place."""
    c = op.get_bind()
    span = c.execute(sa.text("SELECT min(date), max(date) FROM assessments")).first()
    days = c.execute(sa.text("SELECT min(date), max(date) FROM attendance_days")).first()
    starts = min([d for d in (span[0], days[0]) if d], default=None)
    ends = max([d for d in (span[1], days[1]) if d], default=None)
    if not starts:
        return                                   # nothing recorded yet: the first term is made in the app
    named = c.execute(sa.text("SELECT value FROM settings WHERE key = 'term'")).scalar()
    name = (str(named).strip().strip('"') if named else "") or "Term 1"
    year = str(ends.year)
    if name.endswith(year):                      # "Term 1, 2026" -> "Term 1"
        name = name[: -len(year)].rstrip(" ,/-") or "Term 1"
    term_id = c.execute(sa.text(
        "INSERT INTO terms (name, year, starts_on, ends_on, weight, is_sample) "
        "VALUES (:n, :y, :s, :e, 1, false) RETURNING id"), {"n": name[:60], "y": year, "s": starts, "e": ends}).scalar()
    c.execute(sa.text("UPDATE assessments SET term_id = :t WHERE term_id IS NULL"), {"t": term_id})
    c.execute(sa.text("UPDATE attendance_days SET term_id = :t WHERE term_id IS NULL"), {"t": term_id})
    c.execute(sa.text("UPDATE classes SET year = :y WHERE year = ''"), {"y": year})
    c.execute(sa.text("DELETE FROM settings WHERE key = 'current_term'"))
    c.execute(sa.text("INSERT INTO settings (key, value) VALUES ('current_term', to_jsonb(CAST(:t AS int)))"), {"t": term_id})


def downgrade() -> None:
    op.drop_column('classes', 'rollover')
    op.drop_column('classes', 'year')
    # WARNING: constraint name is None; this directive will fail as
    # rendered.  Add a name, or use a naming convention; see
    # https://alembic.sqlalchemy.org/en/latest/naming.html
    op.drop_constraint(None, 'attendance_days', type_='foreignkey')
    op.drop_index(op.f('ix_attendance_days_term_id'), table_name='attendance_days')
    op.drop_column('attendance_days', 'term_id')
    # WARNING: constraint name is None; this directive will fail as
    # rendered.  Add a name, or use a naming convention; see
    # https://alembic.sqlalchemy.org/en/latest/naming.html
    op.drop_constraint(None, 'assessments', type_='foreignkey')
    op.drop_index(op.f('ix_assessments_term_id'), table_name='assessments')
    op.drop_column('assessments', 'term_id')
    op.drop_table('terms')