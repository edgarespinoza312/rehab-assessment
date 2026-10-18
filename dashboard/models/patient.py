from datetime import datetime

from dashboard.database import db


class Patient(db.Model):

    __tablename__ = "patients"

    patient_id = db.Column(
        db.Integer,
        primary_key=True
    )

    first_name = db.Column(
        db.String(50),
        nullable=False
    )

    last_name = db.Column(
        db.String(50),
        nullable=False
    )

    date_of_birth = db.Column(
        db.Date
    )

    sex = db.Column(
        db.String(20)
    )

    diagnosis = db.Column(
        db.String(150)
    )

    affected_side = db.Column(
        db.String(20)
    )

    therapist_notes = db.Column(
        db.Text
    )

    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow
    )

    updated_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow
    )

    # One patient can have many assessment records
    assessments = db.relationship(
        "AssessmentRecord",
        backref="patient",
        lazy=True,
        cascade="all, delete-orphan"
    )

    workout_plans = db.relationship(
        "WorkoutPlan",
        back_populates="patient",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    workout_sessions = db.relationship(
        "CompletedWorkoutSession",
        back_populates="patient",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    user = db.relationship(
        "User",
        back_populates="patient",
        uselist=False,
    )

    def __repr__(self):
        return (
            f"<Patient {self.first_name} "
            f"{self.last_name}>"
        )