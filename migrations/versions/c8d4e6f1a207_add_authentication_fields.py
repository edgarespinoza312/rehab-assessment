"""Add application authentication fields.

Revision ID: c8d4e6f1a207
Revises: b4f7a1c9d203
"""

from alembic import op
import sqlalchemy as sa


revision = "c8d4e6f1a207"
down_revision = "b4f7a1c9d203"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("users", sa.Column("email", sa.String(length=255)))
    op.add_column("users", sa.Column("password_hash", sa.String(length=255)))
    op.create_index("ix_users_email", "users", ["email"], unique=True)


def downgrade():
    op.drop_index("ix_users_email", table_name="users")
    op.drop_column("users", "password_hash")
    op.drop_column("users", "email")
