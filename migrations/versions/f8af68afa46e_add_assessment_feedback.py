"""Add assessment feedback

Revision ID: f8af68afa46e
Revises: cf5a5f57fb40
Create Date: 2026-07-28 16:23:02.539029
"""
from alembic import op
import sqlalchemy as sa


revision = "f8af68afa46e"
down_revision = "cf5a5f57fb40"
branch_labels = None
depends_on = None


def upgrade():
    columns = {
        column["name"]
        for column in sa.inspect(op.get_bind()).get_columns("assessment_records")
    }
    if "feedback" not in columns:
        with op.batch_alter_table("assessment_records", schema=None) as batch_op:
            batch_op.add_column(sa.Column("feedback", sa.Text(), nullable=True))


def downgrade():
    columns = {
        column["name"]
        for column in sa.inspect(op.get_bind()).get_columns("assessment_records")
    }
    if "feedback" in columns:
        with op.batch_alter_table("assessment_records", schema=None) as batch_op:
            batch_op.drop_column("feedback")
