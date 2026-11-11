"""Add scoped review delegation for plan and assessment-correction governance.

Revision ID: c41f6b2a9d30
Revises: b2e5c7a9134d
Create Date: 2026-10-22
"""
from alembic import op
import sqlalchemy as sa


revision = "c41f6b2a9d30"
down_revision = "b2e5c7a9134d"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "patient_review_delegations",
        sa.Column("delegation_id", sa.Integer(), primary_key=True),
        sa.Column("patient_id", sa.Integer(), nullable=False),
        sa.Column("delegated_to_user_id", sa.Integer(), nullable=False),
        sa.Column("delegated_by_user_id", sa.Integer(), nullable=False),
        sa.Column("scope", sa.String(length=32), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
        sa.Column("revoked_by_user_id", sa.Integer(), nullable=True),
        sa.Column("revocation_reason", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "scope IN ('plan_approval', 'assessment_correction')",
            name="ck_patient_review_delegation_scope",
        ),
        sa.CheckConstraint(
            "delegated_to_user_id != delegated_by_user_id",
            name="ck_patient_review_delegation_distinct_users",
        ),
        sa.CheckConstraint(
            "length(reason) >= 8",
            name="ck_patient_review_delegation_reason",
        ),
        sa.ForeignKeyConstraint(
            ["patient_id"], ["patients.patient_id"],
            name="fk_patient_review_delegation_patient", ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["delegated_to_user_id"], ["users.user_id"],
            name="fk_patient_review_delegation_reviewer", ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["delegated_by_user_id"], ["users.user_id"],
            name="fk_patient_review_delegation_grantor", ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["revoked_by_user_id"], ["users.user_id"],
            name="fk_patient_review_delegation_revoked_by", ondelete="RESTRICT",
        ),
    )
    op.create_index(
        "ix_patient_review_delegations_patient_id",
        "patient_review_delegations",
        ["patient_id"],
    )
    op.create_index(
        "ix_patient_review_delegations_delegated_to_user_id",
        "patient_review_delegations",
        ["delegated_to_user_id"],
    )


def downgrade():
    op.drop_index(
        "ix_patient_review_delegations_delegated_to_user_id",
        table_name="patient_review_delegations",
    )
    op.drop_index(
        "ix_patient_review_delegations_patient_id",
        table_name="patient_review_delegations",
    )
    op.drop_table("patient_review_delegations")
