"""Add reusable workout plans and patient workout history.

Revision ID: 7d2c4e8a1f30
Revises: f8af68afa46e
Create Date: 2026-10-02
"""

from alembic import op
import sqlalchemy as sa


revision = "7d2c4e8a1f30"
down_revision = "f8af68afa46e"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "exercise_identities",
        sa.Column("exercise_id", sa.String(length=100), primary_key=True),
    )
    op.bulk_insert(
        sa.table("exercise_identities", sa.column("exercise_id", sa.String())),
        [{"exercise_id": "bicep_curl"}],
    )

    op.create_table(
        "workout_plans",
        sa.Column("plan_id", sa.Integer(), primary_key=True),
        sa.Column(
            "patient_id",
            sa.Integer(),
            sa.ForeignKey("patients.patient_id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_workout_plans_patient_id", "workout_plans", ["patient_id"])

    op.create_table(
        "workout_plan_exercises",
        sa.Column("plan_exercise_id", sa.Integer(), primary_key=True),
        sa.Column(
            "plan_id",
            sa.Integer(),
            sa.ForeignKey("workout_plans.plan_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column(
            "exercise_id",
            sa.String(length=100),
            sa.ForeignKey("exercise_identities.exercise_id"),
            nullable=False,
        ),
        sa.Column("side", sa.String(length=8), nullable=False),
        sa.Column("target_repetitions", sa.Integer(), nullable=False),
        sa.Column("resistance_value", sa.Numeric(10, 3)),
        sa.Column("resistance_unit", sa.String(length=24)),
        sa.Column("resistance_type", sa.String(length=40)),
        sa.CheckConstraint("position >= 0", name="ck_workout_plan_position"),
        sa.CheckConstraint(
            "side IN ('left', 'right')", name="ck_workout_plan_exercise_side"
        ),
        sa.CheckConstraint(
            "target_repetitions > 0", name="ck_workout_plan_target_repetitions"
        ),
        sa.CheckConstraint(
            "(resistance_value IS NULL AND resistance_unit IS NULL) OR "
            "(resistance_value IS NOT NULL AND resistance_unit IS NOT NULL)",
            name="ck_workout_plan_resistance_pair",
        ),
        sa.CheckConstraint(
            "resistance_value IS NULL OR resistance_value >= 0",
            name="ck_workout_plan_resistance_nonnegative",
        ),
        sa.UniqueConstraint(
            "plan_id", "position", name="uq_workout_plan_exercise_position"
        ),
    )
    op.create_index(
        "ix_workout_plan_exercises_plan_id",
        "workout_plan_exercises",
        ["plan_id"],
    )
    op.create_index(
        "ix_workout_plan_exercises_exercise_id",
        "workout_plan_exercises",
        ["exercise_id"],
    )

    op.create_table(
        "workout_sessions",
        sa.Column("workout_session_id", sa.Integer(), primary_key=True),
        sa.Column("runtime_session_id", sa.String(length=36), nullable=False),
        sa.Column(
            "patient_id",
            sa.Integer(),
            sa.ForeignKey("patients.patient_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "workout_plan_id",
            sa.Integer(),
            sa.ForeignKey("workout_plans.plan_id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("preset_id", sa.String(length=120), nullable=False),
        sa.Column("workout_name", sa.String(length=120), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "status IN ('completed', 'cancelled')",
            name="ck_workout_session_status",
        ),
        sa.UniqueConstraint(
            "runtime_session_id", name="uq_workout_sessions_runtime_session_id"
        ),
    )
    op.create_index(
        "ix_workout_sessions_patient_id", "workout_sessions", ["patient_id"]
    )
    op.create_index(
        "ix_workout_sessions_workout_plan_id",
        "workout_sessions",
        ["workout_plan_id"],
    )

    op.create_table(
        "workout_exercise_results",
        sa.Column("workout_exercise_result_id", sa.Integer(), primary_key=True),
        sa.Column(
            "workout_session_id",
            sa.Integer(),
            sa.ForeignKey("workout_sessions.workout_session_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "workout_plan_exercise_id",
            sa.Integer(),
            sa.ForeignKey(
                "workout_plan_exercises.plan_exercise_id", ondelete="SET NULL"
            ),
            nullable=True,
        ),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column(
            "exercise_id",
            sa.String(length=100),
            sa.ForeignKey("exercise_identities.exercise_id"),
            nullable=False,
        ),
        sa.Column("display_name", sa.String(length=120), nullable=False),
        sa.Column("side", sa.String(length=8), nullable=False),
        sa.Column("target_repetitions", sa.Integer(), nullable=False),
        sa.Column("completed_repetitions", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("resistance_value", sa.Numeric(10, 3)),
        sa.Column("resistance_unit", sa.String(length=24)),
        sa.Column("resistance_type", sa.String(length=40)),
        sa.Column("average_score", sa.Float()),
        sa.Column("best_score", sa.Float()),
        sa.Column("worst_score", sa.Float()),
        sa.Column("rom_score", sa.Float()),
        sa.Column("tempo_score", sa.Float()),
        sa.Column("completion_score", sa.Float()),
        sa.Column("stability_score", sa.Float()),
        sa.Column("compensation_score", sa.Float()),
        sa.Column("symmetry_score", sa.Float()),
        sa.Column("feedback", sa.Text()),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("completed_at", sa.DateTime()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("position >= 0", name="ck_workout_result_position"),
        sa.CheckConstraint("side IN ('left', 'right')", name="ck_workout_result_side"),
        sa.CheckConstraint(
            "target_repetitions > 0", name="ck_workout_result_target_repetitions"
        ),
        sa.CheckConstraint(
            "completed_repetitions >= 0 AND "
            "completed_repetitions <= target_repetitions",
            name="ck_workout_result_completed_repetitions",
        ),
        sa.CheckConstraint(
            "status IN ('complete', 'incomplete')",
            name="ck_workout_result_status",
        ),
        sa.CheckConstraint(
            "(resistance_value IS NULL AND resistance_unit IS NULL) OR "
            "(resistance_value IS NOT NULL AND resistance_unit IS NOT NULL)",
            name="ck_workout_result_resistance_pair",
        ),
        sa.CheckConstraint(
            "resistance_value IS NULL OR resistance_value >= 0",
            name="ck_workout_result_resistance_nonnegative",
        ),
        sa.UniqueConstraint(
            "workout_session_id",
            "position",
            name="uq_workout_result_session_position",
        ),
    )
    op.create_index(
        "ix_workout_exercise_results_workout_session_id",
        "workout_exercise_results",
        ["workout_session_id"],
    )
    op.create_index(
        "ix_workout_exercise_results_workout_plan_exercise_id",
        "workout_exercise_results",
        ["workout_plan_exercise_id"],
    )
    op.create_index(
        "ix_workout_exercise_results_exercise_id",
        "workout_exercise_results",
        ["exercise_id"],
    )


def downgrade():
    op.drop_index(
        "ix_workout_exercise_results_exercise_id",
        table_name="workout_exercise_results",
    )
    op.drop_index(
        "ix_workout_exercise_results_workout_plan_exercise_id",
        table_name="workout_exercise_results",
    )
    op.drop_index(
        "ix_workout_exercise_results_workout_session_id",
        table_name="workout_exercise_results",
    )
    op.drop_table("workout_exercise_results")
    op.drop_index(
        "ix_workout_sessions_workout_plan_id", table_name="workout_sessions"
    )
    op.drop_index("ix_workout_sessions_patient_id", table_name="workout_sessions")
    op.drop_table("workout_sessions")
    op.drop_index(
        "ix_workout_plan_exercises_exercise_id",
        table_name="workout_plan_exercises",
    )
    op.drop_index(
        "ix_workout_plan_exercises_plan_id",
        table_name="workout_plan_exercises",
    )
    op.drop_table("workout_plan_exercises")
    op.drop_index("ix_workout_plans_patient_id", table_name="workout_plans")
    op.drop_table("workout_plans")
    op.drop_table("exercise_identities")
