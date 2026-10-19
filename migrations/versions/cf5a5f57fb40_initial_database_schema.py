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
    """Bootstrap core tables and preserve values from the legacy score schema.

    Patient and assessment tables predate Alembic in some Revaliv installations.
    New databases need both tables created here; existing databases are inspected
    and altered in place. Historical single-score rows are retained as
    average_score, while fields that were never recorded remain unknown (NULL).
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

    existing_columns = {
        column["name"]
        for column in sa.inspect(bind).get_columns("assessment_records")
    }
    additions = (
        ("repetitions", sa.Column("repetitions", sa.Integer(), nullable=True)),
        ("average_score", sa.Column("average_score", sa.Float(), nullable=True)),
        ("best_score", sa.Column("best_score", sa.Float(), nullable=True)),
        ("worst_score", sa.Column("worst_score", sa.Float(), nullable=True)),
        ("trend", sa.Column("trend", sa.String(length=50), nullable=True)),
    )
    missing = [(name, column) for name, column in additions if name not in existing_columns]
    if missing:
        with op.batch_alter_table("assessment_records", schema=None) as batch_op:
            for _name, column in missing:
                batch_op.add_column(column)

    current_columns = {
        column["name"]
        for column in sa.inspect(bind).get_columns("assessment_records")
    }
    if "score" in current_columns:
        if "average_score" in current_columns:
            op.execute(sa.text(
                "UPDATE assessment_records "
                "SET average_score = score "
                "WHERE average_score IS NULL AND score IS NOT NULL"
            ))
        with op.batch_alter_table("assessment_records", schema=None) as batch_op:
            batch_op.drop_column("score")


def downgrade():
    bind = op.get_bind()
    columns = {
        column["name"]
        for column in sa.inspect(bind).get_columns("assessment_records")
    }
    if "score" not in columns:
        with op.batch_alter_table("assessment_records", schema=None) as batch_op:
            batch_op.add_column(sa.Column("score", sa.Float(), nullable=True))

    current_columns = {
        column["name"]
        for column in sa.inspect(bind).get_columns("assessment_records")
    }
    if "average_score" in current_columns and "score" in current_columns:
        op.execute(sa.text(
            "UPDATE assessment_records "
            "SET score = average_score "
            "WHERE score IS NULL AND average_score IS NOT NULL"
        ))

    current_columns = {
        column["name"]
        for column in sa.inspect(bind).get_columns("assessment_records")
    }
    removable = [
        name for name in ("trend", "worst_score", "best_score", "average_score", "repetitions")
        if name in current_columns
    ]
    if removable:
        with op.batch_alter_table("assessment_records", schema=None) as batch_op:
            for name in removable:
                batch_op.drop_column(name)
