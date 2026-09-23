# /markbook/migrations/versions/0003_audit_log.py
"""audit log and mark stamps

Adds the history table, and stamps each mark with when it was last changed and by whom.

Revision ID: f35999762be5
Revises: 0002_archive
Created: 2026-09-22 23:48:56.813350
"""
from alembic import op
import sqlalchemy as sa


revision = '0003_audit'
down_revision = '0002_archive'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('audit_log',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('at', sa.DateTime(), nullable=False),
    sa.Column('who', sa.String(length=80), nullable=False),
    sa.Column('action', sa.String(length=40), nullable=False),
    sa.Column('entity', sa.String(length=20), nullable=False),
    sa.Column('entity_id', sa.Integer(), nullable=True),
    sa.Column('student_id', sa.Integer(), nullable=True),
    sa.Column('assessment_id', sa.Integer(), nullable=True),
    sa.Column('old_value', sa.String(length=60), nullable=True),
    sa.Column('new_value', sa.String(length=60), nullable=True),
    sa.Column('detail', sa.Text(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_audit_log_action'), 'audit_log', ['action'], unique=False)
    op.create_index(op.f('ix_audit_log_assessment_id'), 'audit_log', ['assessment_id'], unique=False)
    op.create_index(op.f('ix_audit_log_at'), 'audit_log', ['at'], unique=False)
    op.create_index(op.f('ix_audit_log_student_id'), 'audit_log', ['student_id'], unique=False)
    op.add_column('marks', sa.Column('updated_at', sa.DateTime(), nullable=True))
    op.add_column('marks', sa.Column('updated_by', sa.String(length=80), nullable=True))


def downgrade() -> None:
    op.drop_column('marks', 'updated_by')
    op.drop_column('marks', 'updated_at')
    op.drop_index(op.f('ix_audit_log_student_id'), table_name='audit_log')
    op.drop_index(op.f('ix_audit_log_at'), table_name='audit_log')
    op.drop_index(op.f('ix_audit_log_assessment_id'), table_name='audit_log')
    op.drop_index(op.f('ix_audit_log_action'), table_name='audit_log')
    op.drop_table('audit_log')