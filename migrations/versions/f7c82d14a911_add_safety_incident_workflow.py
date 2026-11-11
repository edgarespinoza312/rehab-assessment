"""Add safety incident lifecycle, correction tracking, and review history.

Revision ID: f7c82d14a911
Revises: d97c2a6e4b11
Create Date: 2026-10-22
"""
from alembic import op
import sqlalchemy as sa


revision = "f7c82d14a911"
down_revision = "d97c2a6e4b11"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "safety_incidents",
        sa.Column("incident_id", sa.Integer(), primary_key=True),
        sa.Column("incident_key", sa.String(length=36), nullable=False, unique=True),
        sa.Column("category", sa.String(length=60), nullable=False),
        sa.Column("summary", sa.String(length=500), nullable=False),
        sa.Column("details", sa.Text(), nullable=False, server_default=""),
        sa.Column("severity", sa.String(length=16), nullable=False),
        sa.Column("likelihood", sa.String(length=16), nullable=False),
        sa.Column("evidence_strength", sa.String(length=16), nullable=False),
        sa.Column("exposure_count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("control_failure", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("risk_score", sa.Float(), nullable=False),
        sa.Column("priority_tier", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="reported"),
        sa.Column("restriction_scopes", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("restriction_reason", sa.Text(), nullable=True),
        sa.Column("root_cause_status", sa.String(length=16), nullable=False, server_default="not_assessed"),
        sa.Column("root_cause_notes", sa.Text(), nullable=True),
        sa.Column("reporter_user_id", sa.Integer(), nullable=False),
        sa.Column("owner_user_id", sa.Integer(), nullable=True),
        sa.Column("acknowledged_by_user_id", sa.Integer(), nullable=True),
        sa.Column("independent_reviewer_user_id", sa.Integer(), nullable=True),
        sa.Column("closed_by_user_id", sa.Integer(), nullable=True),
        sa.Column("closure_rationale", sa.Text(), nullable=True),
        sa.Column("external_board_reference", sa.String(length=255), nullable=True),
        sa.Column("reported_at", sa.DateTime(), nullable=False),
        sa.Column("acknowledged_at", sa.DateTime(), nullable=True),
        sa.Column("next_review_at", sa.DateTime(), nullable=False),
        sa.Column("response_due_at", sa.DateTime(), nullable=False),
        sa.Column("closed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "severity IN ('low', 'moderate', 'serious', 'critical')",
            name="ck_safety_incident_severity",
        ),
        sa.CheckConstraint(
            "likelihood IN ('unlikely', 'possible', 'likely', 'very_likely')",
            name="ck_safety_incident_likelihood",
        ),
        sa.CheckConstraint(
            "evidence_strength IN ('weak', 'moderate', 'strong')",
            name="ck_safety_incident_evidence_strength",
        ),
        sa.CheckConstraint("exposure_count >= 1", name="ck_safety_incident_exposure_positive"),
        sa.CheckConstraint(
            "priority_tier IN ('routine', 'elevated', 'urgent', 'critical')",
            name="ck_safety_incident_priority",
        ),
        sa.CheckConstraint(
            "status IN ('reported', 'investigating', 'restricted', 'awaiting_independent_review', 'closed', 'reopened')",
            name="ck_safety_incident_status",
        ),
        sa.CheckConstraint(
            "root_cause_status IN ('not_assessed', 'known', 'unknown')",
            name="ck_safety_incident_root_cause_status",
        ),
        sa.ForeignKeyConstraint(
            ["reporter_user_id"], ["users.user_id"],
            name="fk_safety_incident_reporter", ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["owner_user_id"], ["users.user_id"],
            name="fk_safety_incident_owner", ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["acknowledged_by_user_id"], ["users.user_id"],
            name="fk_safety_incident_acknowledged_by", ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["independent_reviewer_user_id"], ["users.user_id"],
            name="fk_safety_incident_independent_reviewer", ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["closed_by_user_id"], ["users.user_id"],
            name="fk_safety_incident_closed_by", ondelete="RESTRICT",
        ),
    )
    op.create_index("ix_safety_incidents_incident_key", "safety_incidents", ["incident_key"])
    op.create_index("ix_safety_incidents_reporter_user_id", "safety_incidents", ["reporter_user_id"])
    op.create_index("ix_safety_incidents_owner_user_id", "safety_incidents", ["owner_user_id"])

    op.create_table(
        "safety_incident_events",
        sa.Column("event_id", sa.Integer(), primary_key=True),
        sa.Column("incident_id", sa.Integer(), nullable=False),
        sa.Column("actor_user_id", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(length=80), nullable=False),
        sa.Column("previous_status", sa.String(length=32), nullable=False),
        sa.Column("new_status", sa.String(length=32), nullable=False),
        sa.Column("detail", sa.Text(), nullable=False, server_default=""),
        sa.Column("occurred_at", sa.DateTime(), nullable=False),
        sa.Column("previous_hash", sa.String(length=64), nullable=False),
        sa.Column("event_hash", sa.String(length=64), nullable=False, unique=True),
        sa.ForeignKeyConstraint(
            ["incident_id"], ["safety_incidents.incident_id"],
            name="fk_safety_event_incident", ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["actor_user_id"], ["users.user_id"],
            name="fk_safety_event_actor", ondelete="RESTRICT",
        ),
    )
    op.create_index("ix_safety_incident_events_incident_id", "safety_incident_events", ["incident_id"])

    op.create_table(
        "safety_corrective_actions",
        sa.Column("action_id", sa.Integer(), primary_key=True),
        sa.Column("incident_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=240), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("owner_user_id", sa.Integer(), nullable=False),
        sa.Column("created_by_user_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="open"),
        sa.Column("due_at", sa.DateTime(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("completion_evidence", sa.Text(), nullable=True),
        sa.Column("verified_by_user_id", sa.Integer(), nullable=True),
        sa.Column("verified_at", sa.DateTime(), nullable=True),
        sa.Column("effectiveness_result", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "status IN ('open', 'in_progress', 'completed', 'verified', 'cancelled')",
            name="ck_safety_action_status",
        ),
        sa.ForeignKeyConstraint(
            ["incident_id"], ["safety_incidents.incident_id"],
            name="fk_safety_action_incident", ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["owner_user_id"], ["users.user_id"],
            name="fk_safety_action_owner", ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"], ["users.user_id"],
            name="fk_safety_action_created_by", ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["verified_by_user_id"], ["users.user_id"],
            name="fk_safety_action_verified_by", ondelete="RESTRICT",
        ),
    )
    op.create_index("ix_safety_corrective_actions_incident_id", "safety_corrective_actions", ["incident_id"])
    op.create_index("ix_safety_corrective_actions_owner_user_id", "safety_corrective_actions", ["owner_user_id"])


def downgrade():
    op.drop_index("ix_safety_corrective_actions_owner_user_id", table_name="safety_corrective_actions")
    op.drop_index("ix_safety_corrective_actions_incident_id", table_name="safety_corrective_actions")
    op.drop_table("safety_corrective_actions")
    op.drop_index("ix_safety_incident_events_incident_id", table_name="safety_incident_events")
    op.drop_table("safety_incident_events")
    op.drop_index("ix_safety_incidents_owner_user_id", table_name="safety_incidents")
    op.drop_index("ix_safety_incidents_reporter_user_id", table_name="safety_incidents")
    op.drop_index("ix_safety_incidents_incident_key", table_name="safety_incidents")
    op.drop_table("safety_incidents")
