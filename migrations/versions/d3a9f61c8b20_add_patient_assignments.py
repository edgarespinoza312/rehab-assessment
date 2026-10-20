"""Add auditable clinician-patient assignments.

Revision ID: d3a9f61c8b20
Revises: c8d4e6f1a207
"""

from alembic import op
import sqlalchemy as sa


revision = "d3a9f61c8b20"
down_revision = "a1c7e9b503d6"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "patient_assignments",
        sa.Column("assignment_id", sa.Integer(), primary_key=True),
        sa.Column(
            "patient_id",
            sa.Integer(),
            sa.ForeignKey("patients.patient_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "clinician_user_id",
            sa.Integer(),
            sa.ForeignKey("users.user_id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "assigned_by_user_id",
            sa.Integer(),
            sa.ForeignKey("users.user_id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("assigned_at", sa.DateTime(), nullable=False),
        sa.Column("ended_at", sa.DateTime(), nullable=True),
        sa.Column(
            "ended_by_user_id",
            sa.Integer(),
            sa.ForeignKey("users.user_id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("end_reason", sa.String(length=240), nullable=True),
        sa.CheckConstraint(
            "ended_at IS NULL OR ended_at >= assigned_at",
            name="ck_patient_assignments_end_after_start",
        ),
    )
    op.create_index(
        "ix_patient_assignments_patient_id",
        "patient_assignments",
        ["patient_id"],
        unique=False,
    )
    op.create_index(
        "ix_patient_assignments_clinician_user_id",
        "patient_assignments",
        ["clinician_user_id"],
        unique=False,
    )
    op.create_index(
        "uq_patient_assignments_one_active",
        "patient_assignments",
        ["patient_id"],
        unique=True,
        sqlite_where=sa.text("ended_at IS NULL"),
        postgresql_where=sa.text("ended_at IS NULL"),
    )


def downgrade():
    op.drop_index("uq_patient_assignments_one_active", table_name="patient_assignments")
    op.drop_index("ix_patient_assignments_clinician_user_id", table_name="patient_assignments")
    op.drop_index("ix_patient_assignments_patient_id", table_name="patient_assignments")
    op.drop_table("patient_assignments")
