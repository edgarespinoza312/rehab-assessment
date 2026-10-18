"""Add append-only progression advisory review events.

Revision ID: 9e6c4d2b8a10
Revises: 7d2c4e8a1f30
Create Date: 2026-10-03
"""

from alembic import op
import sqlalchemy as sa


revision = "9e6c4d2b8a10"
down_revision = "7d2c4e8a1f30"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "progression_review_events",
        sa.Column("review_event_id", sa.Integer(), primary_key=True),
        sa.Column(
            "patient_id",
            sa.Integer(),
            sa.ForeignKey("patients.patient_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "exercise_id",
            sa.String(length=100),
            sa.ForeignKey("exercise_identities.exercise_id"),
            nullable=False,
        ),
        sa.Column("side", sa.String(length=8), nullable=True),
        sa.Column("advisory_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("disposition", sa.String(length=16), nullable=False),
        sa.Column("reviewer_reference", sa.String(length=120), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "side IN ('left', 'right') OR side IS NULL",
            name="ck_progression_review_side",
        ),
        sa.CheckConstraint(
            "disposition IN ('REVIEWED', 'ACKNOWLEDGED', 'DISMISSED')",
            name="ck_progression_review_disposition",
        ),
    )
    op.create_index(
        "ix_progression_review_events_patient_id",
        "progression_review_events",
        ["patient_id"],
    )
    op.create_index(
        "ix_progression_review_events_exercise_id",
        "progression_review_events",
        ["exercise_id"],
    )
    op.create_index(
        "ix_progression_review_events_advisory_fingerprint",
        "progression_review_events",
        ["advisory_fingerprint"],
    )


def downgrade():
    op.drop_index(
        "ix_progression_review_events_advisory_fingerprint",
        table_name="progression_review_events",
    )
    op.drop_index(
        "ix_progression_review_events_exercise_id",
        table_name="progression_review_events",
    )
    op.drop_index(
        "ix_progression_review_events_patient_id",
        table_name="progression_review_events",
    )
    op.drop_table("progression_review_events")
