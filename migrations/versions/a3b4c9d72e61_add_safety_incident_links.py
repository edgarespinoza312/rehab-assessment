"""Add linked incident records for coordinated cross-case signal review.

Revision ID: a3b4c9d72e61
Revises: f7c82d14a911
Create Date: 2026-10-22
"""
from alembic import op
import sqlalchemy as sa


revision = "a3b4c9d72e61"
down_revision = "f7c82d14a911"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "safety_incident_links",
        sa.Column("link_id", sa.Integer(), primary_key=True),
        sa.Column("incident_id", sa.Integer(), nullable=False),
        sa.Column("related_incident_id", sa.Integer(), nullable=False),
        sa.Column("link_type", sa.String(length=32), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("created_by_user_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "link_type IN ('shared_mechanism', 'recurrence', 'cross_case_signal', 'shared_exposure')",
            name="ck_safety_incident_link_type",
        ),
        sa.CheckConstraint(
            "incident_id != related_incident_id",
            name="ck_safety_incident_link_not_self",
        ),
        sa.UniqueConstraint(
            "incident_id", "related_incident_id",
            name="uq_safety_incident_link_pair",
        ),
        sa.ForeignKeyConstraint(
            ["incident_id"], ["safety_incidents.incident_id"],
            name="fk_safety_link_incident", ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["related_incident_id"], ["safety_incidents.incident_id"],
            name="fk_safety_link_related_incident", ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"], ["users.user_id"],
            name="fk_safety_link_created_by", ondelete="RESTRICT",
        ),
    )
    op.create_index(
        "ix_safety_incident_links_incident_id", "safety_incident_links", ["incident_id"]
    )
    op.create_index(
        "ix_safety_incident_links_related_incident_id",
        "safety_incident_links",
        ["related_incident_id"],
    )


def downgrade():
    op.drop_index(
        "ix_safety_incident_links_related_incident_id", table_name="safety_incident_links"
    )
    op.drop_index(
        "ix_safety_incident_links_incident_id", table_name="safety_incident_links"
    )
    op.drop_table("safety_incident_links")
