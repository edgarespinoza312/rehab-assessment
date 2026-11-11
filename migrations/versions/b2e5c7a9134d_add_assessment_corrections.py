"""Add reviewed correction overlays for historical assessment records.

Revision ID: b2e5c7a9134d
Revises: a3b4c9d72e61
Create Date: 2026-10-22
"""
from alembic import op
import sqlalchemy as sa


revision = "b2e5c7a9134d"
down_revision = "a3b4c9d72e61"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "assessment_corrections",
        sa.Column("correction_id", sa.Integer(), primary_key=True),
        sa.Column("assessment_id", sa.Integer(), nullable=False),
        sa.Column("patient_id", sa.Integer(), nullable=False),
        sa.Column("field_name", sa.String(length=32), nullable=False),
        sa.Column("original_value_json", sa.Text(), nullable=False),
        sa.Column("proposed_value_json", sa.Text(), nullable=False),
        sa.Column("source_snapshot_hash", sa.String(length=64), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("evidence_reference", sa.String(length=500), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="pending"),
        sa.Column("requested_by_user_id", sa.Integer(), nullable=False),
        sa.Column("reviewed_by_user_id", sa.Integer(), nullable=True),
        sa.Column("review_rationale", sa.Text(), nullable=True),
        sa.Column("requested_at", sa.DateTime(), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(), nullable=True),
        sa.CheckConstraint(
            "field_name IN ('exercise', 'repetitions', 'average_score', 'best_score', 'worst_score', 'trend', 'feedback')",
            name="ck_assessment_correction_field",
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'accepted', 'rejected', 'stale')",
            name="ck_assessment_correction_status",
        ),
        sa.ForeignKeyConstraint(
            ["assessment_id"], ["assessment_records.assessment_id"],
            name="fk_assessment_correction_assessment", ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["patient_id"], ["patients.patient_id"],
            name="fk_assessment_correction_patient", ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["requested_by_user_id"], ["users.user_id"],
            name="fk_assessment_correction_requested_by", ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["reviewed_by_user_id"], ["users.user_id"],
            name="fk_assessment_correction_reviewed_by", ondelete="RESTRICT",
        ),
    )
    op.create_index(
        "ix_assessment_corrections_assessment_id",
        "assessment_corrections",
        ["assessment_id"],
    )
    op.create_index(
        "ix_assessment_corrections_patient_id",
        "assessment_corrections",
        ["patient_id"],
    )
    op.create_table(
        "assessment_correction_events",
        sa.Column("event_id", sa.Integer(), primary_key=True),
        sa.Column("correction_id", sa.Integer(), nullable=False),
        sa.Column("actor_user_id", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(length=32), nullable=False),
        sa.Column("previous_status", sa.String(length=16), nullable=False),
        sa.Column("new_status", sa.String(length=16), nullable=False),
        sa.Column("detail", sa.Text(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(), nullable=False),
        sa.Column("previous_hash", sa.String(length=64), nullable=False),
        sa.Column("event_hash", sa.String(length=64), nullable=False, unique=True),
        sa.ForeignKeyConstraint(
            ["correction_id"], ["assessment_corrections.correction_id"],
            name="fk_assessment_correction_event_correction", ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["actor_user_id"], ["users.user_id"],
            name="fk_assessment_correction_event_actor", ondelete="RESTRICT",
        ),
    )
    op.create_index(
        "ix_assessment_correction_events_correction_id",
        "assessment_correction_events",
        ["correction_id"],
    )


def downgrade():
    op.drop_index(
        "ix_assessment_correction_events_correction_id",
        table_name="assessment_correction_events",
    )
    op.drop_table("assessment_correction_events")
    op.drop_index(
        "ix_assessment_corrections_patient_id",
        table_name="assessment_corrections",
    )
    op.drop_index(
        "ix_assessment_corrections_assessment_id",
        table_name="assessment_corrections",
    )
    op.drop_table("assessment_corrections")
