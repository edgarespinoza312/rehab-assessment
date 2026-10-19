"""Initial database schema

Revision ID: cf5a5f57fb40
Revises:
Create Date: 2026-07-28 15:34:20.541237
"""
from alembic import op
import sqlalchemy as sa


revision = "cf5a5f57fb40"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    """Bootstrap legacy patient tables, then migrate their assessment fields.

    The application historically created its two core tables before Alembic was
    introduced. A fresh file-based database has no such tables, so bootstrap
    them when absent. Existing tables are left intact and upgraded in place.
    """
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not inspector.has_table("patients"):
        op.create_table(
            "patients",
            sa.Column("patient_id", sa.Integer(), primary_key=True),
            sa.Column("first_name", sa.String(length=50), nullable=False),
            sa.Column("last_name", sa.String(length=50), nullable=False),
            sa.Column("date_of_birth", sa.Date(), nullable=True),
            sa.Column("sex", sa.String(length=20), nullable=True),
            sa.Column("diagnosis", sa.String(length=150), nullable=True),
            sa.Column("affected_side", sa.String(length=20), nullable=True),
            sa.Column("therapist_notes", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
        )

    inspector = sa.inspect(bind)
    if not inspector.has_table("assessment_records"):
        op.create_table(
            "assessment_records",
            sa.Column("assessment_id", sa.Integer(), primary_key=True),
            sa.Column(
                "patient_id",
                sa.Integer(),
                sa.ForeignKey("patients.patient_id"),
                nullable=False,
            ),
            sa.Column("exercise", sa.String(length=100), nullable=False),
            sa.Column("score", sa.Float(), nullable=True),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
        )

    column_names = {
        column["name"]
        for column in sa.inspect(bind).get_columns("assessment_records")
    }
    additions = (
        ("repetitions", sa.Column("repetitions", sa.Integer(), nullable=False)),
        ("average_score", sa.Column("average_score", sa.Float(), nullable=False)),
        ("best_score", sa.Column("best_score", sa.Float(), nullable=False)),
        ("worst_score", sa.Column("worst_score", sa.Float(), nullable=False)),
        ("trend", sa.Column("trend", sa.String(length=50), nullable=True)),
    )
    needs_changes = any(name not in column_names for name, _ in additions) or (
        "score" in column_names
    )
    if needs_changes:
        with op.batch_alter_table("assessment_records", schema=None) as batch_op:
            for name, column in additions:
                if name not in column_names:
                    batch_op.add_column(column)
            if "score" in column_names:
                batch_op.drop_column("score")


def downgrade():
    with op.batch_alter_table("assessment_records", schema=None) as batch_op:
        batch_op.add_column(sa.Column("score", sa.Float(), nullable=True))
        batch_op.drop_column("trend")
        batch_op.drop_column("worst_score")
        batch_op.drop_column("best_score")
        batch_op.drop_column("average_score")
        batch_op.drop_column("repetitions")
