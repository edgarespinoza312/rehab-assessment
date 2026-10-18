"""Database models for reusable workout plans and patient workout history."""

from datetime import datetime

from dashboard.database import db


class ExerciseIdentity(db.Model):
    """Stable key into the code-owned exercise/profile registry."""

    __tablename__ = "exercise_identities"

    exercise_id = db.Column(db.String(100), primary_key=True)


class WorkoutPlan(db.Model):
    __tablename__ = "workout_plans"

    plan_id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(
        db.Integer,
        db.ForeignKey("patients.patient_id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    name = db.Column(db.String(120), nullable=False)
    description = db.Column(db.Text, nullable=False, default="")
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    patient = db.relationship("Patient", back_populates="workout_plans")
    exercises = db.relationship(
        "WorkoutPlanExercise",
        back_populates="plan",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="WorkoutPlanExercise.position",
    )


class WorkoutPlanExercise(db.Model):
    __tablename__ = "workout_plan_exercises"
    __table_args__ = (
        db.UniqueConstraint(
            "plan_id", "position", name="uq_workout_plan_exercise_position"
        ),
        db.CheckConstraint("position >= 0", name="ck_workout_plan_position"),
        db.CheckConstraint(
            "side IN ('left', 'right')", name="ck_workout_plan_exercise_side"
        ),
        db.CheckConstraint(
            "target_repetitions > 0", name="ck_workout_plan_target_repetitions"
        ),
        db.CheckConstraint(
            "(resistance_value IS NULL AND resistance_unit IS NULL) OR "
            "(resistance_value IS NOT NULL AND resistance_unit IS NOT NULL)",
            name="ck_workout_plan_resistance_pair",
        ),
        db.CheckConstraint(
            "resistance_value IS NULL OR resistance_value >= 0",
            name="ck_workout_plan_resistance_nonnegative",
        ),
    )

    plan_exercise_id = db.Column(db.Integer, primary_key=True)
    plan_id = db.Column(
        db.Integer,
        db.ForeignKey("workout_plans.plan_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    position = db.Column(db.Integer, nullable=False)
    exercise_id = db.Column(
        db.String(100),
        db.ForeignKey("exercise_identities.exercise_id"),
        nullable=False,
        index=True,
    )
    side = db.Column(db.String(8), nullable=False)
    target_repetitions = db.Column(db.Integer, nullable=False)
    resistance_value = db.Column(db.Numeric(10, 3))
    resistance_unit = db.Column(db.String(24))
    resistance_type = db.Column(db.String(40))

    plan = db.relationship("WorkoutPlan", back_populates="exercises")
    exercise_identity = db.relationship("ExerciseIdentity")


class CompletedWorkoutSession(db.Model):
    __tablename__ = "workout_sessions"
    __table_args__ = (
        db.CheckConstraint(
            "status IN ('completed', 'cancelled')",
            name="ck_workout_session_status",
        ),
    )

    workout_session_id = db.Column(db.Integer, primary_key=True)
    runtime_session_id = db.Column(db.String(36), nullable=False, unique=True)
    patient_id = db.Column(
        db.Integer,
        db.ForeignKey("patients.patient_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    workout_plan_id = db.Column(
        db.Integer,
        db.ForeignKey("workout_plans.plan_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    preset_id = db.Column(db.String(120), nullable=False)
    workout_name = db.Column(db.String(120), nullable=False)
    status = db.Column(db.String(16), nullable=False)
    started_at = db.Column(db.DateTime, nullable=False)
    completed_at = db.Column(db.DateTime, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    patient = db.relationship("Patient", back_populates="workout_sessions")
    workout_plan = db.relationship("WorkoutPlan")
    exercise_results = db.relationship(
        "WorkoutExerciseResult",
        back_populates="workout_session",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="WorkoutExerciseResult.position",
    )


class WorkoutExerciseResult(db.Model):
    __tablename__ = "workout_exercise_results"
    __table_args__ = (
        db.UniqueConstraint(
            "workout_session_id",
            "position",
            name="uq_workout_result_session_position",
        ),
        db.CheckConstraint("position >= 0", name="ck_workout_result_position"),
        db.CheckConstraint(
            "side IN ('left', 'right')", name="ck_workout_result_side"
        ),
        db.CheckConstraint(
            "target_repetitions > 0", name="ck_workout_result_target_repetitions"
        ),
        db.CheckConstraint(
            "completed_repetitions >= 0 AND "
            "completed_repetitions <= target_repetitions",
            name="ck_workout_result_completed_repetitions",
        ),
        db.CheckConstraint(
            "status IN ('complete', 'incomplete')",
            name="ck_workout_result_status",
        ),
        db.CheckConstraint(
            "(resistance_value IS NULL AND resistance_unit IS NULL) OR "
            "(resistance_value IS NOT NULL AND resistance_unit IS NOT NULL)",
            name="ck_workout_result_resistance_pair",
        ),
        db.CheckConstraint(
            "resistance_value IS NULL OR resistance_value >= 0",
            name="ck_workout_result_resistance_nonnegative",
        ),
    )

    workout_exercise_result_id = db.Column(db.Integer, primary_key=True)
    workout_session_id = db.Column(
        db.Integer,
        db.ForeignKey("workout_sessions.workout_session_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    workout_plan_exercise_id = db.Column(
        db.Integer,
        db.ForeignKey("workout_plan_exercises.plan_exercise_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    position = db.Column(db.Integer, nullable=False)
    exercise_id = db.Column(
        db.String(100),
        db.ForeignKey("exercise_identities.exercise_id"),
        nullable=False,
        index=True,
    )
    display_name = db.Column(db.String(120), nullable=False)
    side = db.Column(db.String(8), nullable=False)
    target_repetitions = db.Column(db.Integer, nullable=False)
    completed_repetitions = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(16), nullable=False)
    resistance_value = db.Column(db.Numeric(10, 3))
    resistance_unit = db.Column(db.String(24))
    resistance_type = db.Column(db.String(40))

    average_score = db.Column(db.Float)
    best_score = db.Column(db.Float)
    worst_score = db.Column(db.Float)
    rom_score = db.Column(db.Float)
    tempo_score = db.Column(db.Float)
    completion_score = db.Column(db.Float)
    stability_score = db.Column(db.Float)
    compensation_score = db.Column(db.Float)
    symmetry_score = db.Column(db.Float)
    feedback = db.Column(db.Text)
    started_at = db.Column(db.DateTime, nullable=False)
    completed_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    workout_session = db.relationship(
        "CompletedWorkoutSession", back_populates="exercise_results"
    )
    exercise_identity = db.relationship("ExerciseIdentity")
    workout_plan_exercise = db.relationship("WorkoutPlanExercise")
