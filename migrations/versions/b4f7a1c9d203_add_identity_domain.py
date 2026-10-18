"""Add users, roles, and optional patient-user identity links.

Revision ID: b4f7a1c9d203
Revises: 9e6c4d2b8a10
Create Date: 2026-10-03
"""

from alembic import op
import sqlalchemy as sa


revision = "b4f7a1c9d203"
down_revision = "9e6c4d2b8a10"
branch_labels = None
depends_on = None


ROLES = ("PATIENT", "CLINICIAN", "ADMIN", "OPERATOR")


def upgrade():
    op.create_table(
        "users",
        sa.Column("user_id", sa.Integer(), primary_key=True),
        sa.Column("display_name", sa.String(length=120), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column(
            "patient_id",
            sa.Integer(),
            sa.ForeignKey("patients.patient_id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "status IN ('ACTIVE', 'DISABLED')",
            name="ck_users_status",
        ),
        sa.UniqueConstraint("patient_id", name="uq_users_patient_id"),
    )
    op.create_index("ix_users_patient_id", "users", ["patient_id"])

    op.create_table(
        "roles",
        sa.Column("role_id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=32), nullable=False, unique=True),
        sa.CheckConstraint(
            "name IN ('PATIENT', 'CLINICIAN', 'ADMIN', 'OPERATOR')",
            name="ck_roles_name",
        ),
    )
    op.bulk_insert(
        sa.table("roles", sa.column("name", sa.String(length=32))),
        [{"name": role} for role in ROLES],
    )

    op.create_table(
        "user_roles",
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.user_id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "role_id",
            sa.Integer(),
            sa.ForeignKey("roles.role_id", ondelete="CASCADE"),
            primary_key=True,
        ),
    )


def downgrade():
    op.drop_table("user_roles")
    op.drop_table("roles")
    op.drop_index("ix_users_patient_id", table_name="users")
    op.drop_table("users")
