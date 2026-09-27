# /markbook/migrations/versions/0005_timetable.py
"""timetable sessions for attendance

Weekly lessons per class, and a register now belongs to one of them. Registers taken before this
migration keep slot_id empty and stay valid as whole-day registers.

Revision ID: 47d5cb265218
Revises: 0004_terms
Created: 2026-09-24 14:15:54.486005
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

UNIQUE_OLD = "attendance_days_class_id_date_key"
UNIQUE_NEW = "attendance_days_class_date_slot_key"


def _constraints(table: str) -> set:
    return {c["name"] for c in inspect(op.get_bind()).get_unique_constraints(table)}


revision = '0005_timetable'
down_revision = '0004_terms'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('timetable_slots',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('class_id', sa.Integer(), nullable=False),
    sa.Column('subject_id', sa.Integer(), nullable=False),
    sa.Column('term_id', sa.Integer(), nullable=True),
    sa.Column('weekday', sa.Integer(), nullable=False),
    sa.Column('starts_at', sa.Time(), nullable=False),
    sa.Column('ends_at', sa.Time(), nullable=False),
    sa.Column('room', sa.String(length=40), nullable=False),
    sa.Column('is_sample', sa.Boolean(), nullable=False),
    sa.ForeignKeyConstraint(['class_id'], ['classes.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['subject_id'], ['subjects.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['term_id'], ['terms.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_timetable_slots_class_id'), 'timetable_slots', ['class_id'], unique=False)
    op.create_index(op.f('ix_timetable_slots_subject_id'), 'timetable_slots', ['subject_id'], unique=False)
    op.create_index(op.f('ix_timetable_slots_term_id'), 'timetable_slots', ['term_id'], unique=False)
    op.add_column('attendance_days', sa.Column('slot_id', sa.Integer(), nullable=True))
    op.add_column('attendance_days', sa.Column('subject_id', sa.Integer(), nullable=True))
    for name in _constraints('attendance_days'):          # one register per class per day becomes one per session
        if name != UNIQUE_NEW:
            op.drop_constraint(name, 'attendance_days', type_='unique')
    op.create_index(op.f('ix_attendance_days_slot_id'), 'attendance_days', ['slot_id'], unique=False)
    op.create_index(op.f('ix_attendance_days_subject_id'), 'attendance_days', ['subject_id'], unique=False)
    op.create_unique_constraint(UNIQUE_NEW, 'attendance_days', ['class_id', 'date', 'slot_id'])
    op.create_foreign_key("attendance_days_slot_id_fkey", 'attendance_days', 'timetable_slots', ['slot_id'], ['id'], ondelete='SET NULL')
    op.create_foreign_key("attendance_days_subject_id_fkey", 'attendance_days', 'subjects', ['subject_id'], ['id'], ondelete='SET NULL')


def downgrade() -> None:
    op.drop_constraint("attendance_days_subject_id_fkey", 'attendance_days', type_='foreignkey')
    op.drop_constraint("attendance_days_slot_id_fkey", 'attendance_days', type_='foreignkey')
    op.drop_constraint(UNIQUE_NEW, 'attendance_days', type_='unique')
    op.drop_index(op.f('ix_attendance_days_subject_id'), table_name='attendance_days')
    op.drop_index(op.f('ix_attendance_days_slot_id'), table_name='attendance_days')
    op.execute("DELETE FROM attendance_days a USING attendance_days b "      # keep one register per day
               "WHERE a.id > b.id AND a.class_id = b.class_id AND a.date = b.date")
    op.create_unique_constraint(UNIQUE_OLD, 'attendance_days', ['class_id', 'date'])
    op.drop_column('attendance_days', 'subject_id')
    op.drop_column('attendance_days', 'slot_id')
    op.drop_index(op.f('ix_timetable_slots_term_id'), table_name='timetable_slots')
    op.drop_index(op.f('ix_timetable_slots_subject_id'), table_name='timetable_slots')
    op.drop_index(op.f('ix_timetable_slots_class_id'), table_name='timetable_slots')
    op.drop_table('timetable_slots')