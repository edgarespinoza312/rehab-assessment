"""Allow missing metrics on legacy assessment snapshots.

Revision ID: a1c7e9b503d6
Revises: c8d4e6f1a207
"""

from alembic import op
import sqlalchemy as sa


revision = "a1c7e9b503d6"
down_revision = "c8d4e6f1a207"
branch_labels = None
depends_on = None


_METRIC_COLUMNS = (
    ("repetitions", sa.Integer()),
    ("average_score", sa.Float()),
    ("best_score", sa.Float()),
    ("worst_score", sa.Float()),
)


def upgrade():
    """Permit older records to represent facts the earlier schema never stored."""
    bind = op.get_bind()
    columns = {
        column["name"]: column
        for column in sa.inspect(bind).get_columns("assessment_records")
    }
    missing = [name for name, _type in _METRIC_COLUMNS if name not in columns]
    if missing:
        raise RuntimeError(
            "Cannot migrate assessment metrics; missing columns: "
            + ", ".join(missing)
        )

    non_nullable = [
        (name, sql_type)
        for name, sql_type in _METRIC_COLUMNS
        if not columns[name]["nullable"]
    ]
    if non_nullable:
        with op.batch_alter_table("assessment_records", schema=None) as batch_op:
            for name, sql_type in non_nullable:
                batch_op.alter_column(
                    name,
                    existing_type=sql_type,
                    existing_nullable=False,
                    nullable=True,
                )


def downgrade():
    """Refuse to invent values if unknown legacy metrics remain."""
    bind = op.get_bind()
    columns = {
        column["name"]: column
        for column in sa.inspect(bind).get_columns("assessment_records")
    }
    non_null_columns = []
    for name, sql_type in _METRIC_COLUMNS:
        if name not in columns:
            raise RuntimeError(f"Cannot downgrade; missing assessment column {name}.")
        has_unknown = bind.execute(
            sa.text(f"SELECT 1 FROM assessment_records WHERE {name} IS NULL LIMIT 1")
        ).first()
        if has_unknown:
            raise RuntimeError(
                f"Cannot restore NOT NULL on {name}; unknown legacy values remain."
            )
        if columns[name]["nullable"]:
            non_null_columns.append((name, sql_type))

    if non_null_columns:
        with op.batch_alter_table("assessment_records", schema=None) as batch_op:
            for name, sql_type in non_null_columns:
                batch_op.alter_column(
                    name,
                    existing_type=sql_type,
                    existing_nullable=True,
                    nullable=False,
                )
