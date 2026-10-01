"""attendance codes and subject groups

Attendance stops being a yes/no flag and becomes a code (P, A, S, PM, SS), so a sick student is
no longer indistinguishable from one who stayed away. Existing registers are converted, not
dropped: present becomes P and absent becomes A.

Also adds group sets for subject group work, and lets an assessment belong to one so a group
mark can be entered once.

Revision ID: 2108b64e337a
Revises: 0005_timetable
Created: 2026-09-30 17:57:21.268720
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0006_groups'
down_revision = '0005_timetable'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('group_sets',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=120), nullable=False),
    sa.Column('class_id', sa.Integer(), nullable=False),
    sa.Column('subject_id', sa.Integer(), nullable=False),
    sa.Column('term_id', sa.Integer(), nullable=True),
    sa.Column('made_by', sa.String(length=20), nullable=False),
    sa.Column('rules', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('is_sample', sa.Boolean(), nullable=False),
    sa.ForeignKeyConstraint(['class_id'], ['classes.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['subject_id'], ['subjects.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['term_id'], ['terms.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_group_sets_class_id'), 'group_sets', ['class_id'], unique=False)
    op.create_index(op.f('ix_group_sets_subject_id'), 'group_sets', ['subject_id'], unique=False)
    op.create_index(op.f('ix_group_sets_term_id'), 'group_sets', ['term_id'], unique=False)
    op.create_table('group_rules',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('class_id', sa.Integer(), nullable=False),
    sa.Column('subject_id', sa.Integer(), nullable=True),
    sa.Column('kind', sa.String(length=10), nullable=False),
    sa.Column('student_a', sa.Integer(), nullable=False),
    sa.Column('student_b', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['class_id'], ['classes.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['student_a'], ['students.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['student_b'], ['students.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['subject_id'], ['subjects.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_group_rules_class_id'), 'group_rules', ['class_id'], unique=False)
    op.create_table('student_groups',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('set_id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=80), nullable=False),
    sa.Column('position', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['set_id'], ['group_sets.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_student_groups_set_id'), 'student_groups', ['set_id'], unique=False)
    op.create_table('group_members',
    sa.Column('group_id', sa.Integer(), nullable=False),
    sa.Column('student_id', sa.Integer(), nullable=False),
    sa.Column('is_leader', sa.Boolean(), nullable=False),
    sa.ForeignKeyConstraint(['group_id'], ['student_groups.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['student_id'], ['students.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('group_id', 'student_id'),
    )
    op.add_column('assessments', sa.Column('group_set_id', sa.Integer(), nullable=True))
    op.create_index(op.f('ix_assessments_group_set_id'), 'assessments', ['group_set_id'], unique=False)
    op.create_foreign_key(None, 'assessments', 'group_sets', ['group_set_id'], ['id'], ondelete='SET NULL')
    # keep the registers: add the column, carry the old flag across, then drop it
    op.add_column('attendance_entries', sa.Column('status', sa.String(length=2), nullable=True))
    op.add_column('attendance_entries', sa.Column('note', sa.String(length=120), nullable=False, server_default=''))
    op.execute("UPDATE attendance_entries SET status = CASE WHEN present THEN 'P' ELSE 'A' END")
    op.alter_column('attendance_entries', 'status', nullable=False, server_default='P')
    op.drop_column('attendance_entries', 'present')


def downgrade() -> None:
    op.add_column('attendance_entries', sa.Column('present', sa.BOOLEAN(), autoincrement=False, nullable=True))
    op.execute("UPDATE attendance_entries SET present = (status = 'P')")   # any absence becomes a plain absence
    op.alter_column('attendance_entries', 'present', nullable=False, server_default=sa.text('true'))
    op.drop_column('attendance_entries', 'note')
    op.drop_column('attendance_entries', 'status')
    # WARNING: constraint name is None; this directive will fail as
    # rendered.  Add a name, or use a naming convention; see
    # https://alembic.sqlalchemy.org/en/latest/naming.html
    op.drop_constraint(None, 'assessments', type_='foreignkey')
    op.drop_index(op.f('ix_assessments_group_set_id'), table_name='assessments')
    op.drop_column('assessments', 'group_set_id')
    op.drop_table('group_members')
    op.drop_index(op.f('ix_student_groups_set_id'), table_name='student_groups')
    op.drop_table('student_groups')
    op.drop_index(op.f('ix_group_rules_class_id'), table_name='group_rules')
    op.drop_table('group_rules')
    op.drop_index(op.f('ix_group_sets_term_id'), table_name='group_sets')
    op.drop_index(op.f('ix_group_sets_subject_id'), table_name='group_sets')
    op.drop_index(op.f('ix_group_sets_class_id'), table_name='group_sets')
    op.drop_table('group_sets')