"""Add clinician approval and hash-linked review history for workout plans.

Revision ID: d97c2a6e4b11
Revises: a1c7e9b503d6, d3a9f61c8b20
Create Date: 2026-10-22
"""
from alembic import op
import sqlalchemy as sa


revision = "d97c2a6e4b11"
down_revision = ("a1c7e9b503d6", "d3a9f61c8b20")
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("workout_plans") as batch:
        batch.add_column(
            sa.Column(
                "created_by_user_id",
                sa.Integer(),
                sa.ForeignKey("users.user_id", ondelete="SET NULL"),
                nullable=True,
            )
        )
        batch.add_column(
            sa.Column(
                "approval_status",
                sa.String(length=16),
                nullable=False,
                server_default="draft",
            )
        )
        batch.add_column(
            sa.Column(
                "approved_by_user_id",
                sa.Integer(),
                sa.ForeignKey("users.user_id", ondelete="SET NULL"),
                nullable=True,
            )
        )
        batch.add_column(sa.Column("approved_at", sa.DateTime(), nullable=True))
        batch.add_column(sa.Column("approval_note", sa.Text(), nullable=True))
        batch.create_check_constraint(
            "ck_workout_plan_approval_status",
            "approval_status IN ('draft', 'approved', 'rejected', 'suspended')",
        )

    op.create_index(
        "ix_workout_plans_created_by_user_id",
        "workout_plans",
        ["created_by_user_id"],
    )
    op.create_table(
        "workout_plan_review_events",
        sa.Column("event_id", sa.Integer(), primary_key=True),
        sa.Column(
            "plan_id",
            sa.Integer(),
            sa.ForeignKey("workout_plans.plan_id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "reviewer_user_id",
            sa.Integer(),
            sa.ForeignKey("users.user_id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("decision", sa.String(length=16), nullable=False),
        sa.Column("previous_status", sa.String(length=16), nullable=False),
        sa.Column("new_status", sa.String(length=16), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(), nullable=False),
        sa.Column("previous_hash", sa.String(length=64), nullable=False),
        sa.Column("event_hash", sa.String(length=64), nullable=False, unique=True),
        sa.CheckConstraint(
            "decision IN ('approve', 'reject', 'suspend')",
            name="ck_workout_plan_review_decision",
        ),
        sa.CheckConstraint(
            "previous_status IN ('draft', 'approved', 'rejected', 'suspended') "
            "AND new_status IN ('draft', 'approved', 'rejected', 'suspended')",
            name="ck_workout_plan_review_statuses",
        ),
    )
    op.create_index(
        "ix_workout_plan_review_events_plan_id",
        "workout_plan_review_events",
        ["plan_id"],
    )
    op.create_index(
        "ix_workout_plan_review_events_reviewer_user_id",
        "workout_plan_review_events",
        ["reviewer_user_id"],
    )


def downgrade():
    op.drop_index(
        "ix_workout_plan_review_events_reviewer_user_id",
        table_name="workout_plan_review_events",
    )
    op.drop_index(
        "ix_workout_plan_review_events_plan_id",
        table_name="workout_plan_review_events",
    )
    op.drop_table("workout_plan_review_events")
    op.drop_index("ix_workout_plans_created_by_user_id", table_name="workout_plans")
    with op.batch_alter_table("workout_plans") as batch:
        batch.drop_constraint("ck_workout_plan_approval_status", type_="check")
        batch.drop_column("approval_note")
        batch.drop_column("approved_at")
        batch.drop_column("approved_by_user_id")
        batch.drop_column("approval_status")
        batch.drop_column("created_by_user_id")
