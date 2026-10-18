"""Append-only human review events for advisory progression results."""

from datetime import datetime

from dashboard.database import db


class ProgressionReviewEvent(db.Model):
    """One immutable reviewer interaction with an advisory evidence snapshot."""

    __tablename__ = "progression_review_events"

    review_event_id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(
        db.Integer,
        db.ForeignKey("patients.patient_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    exercise_id = db.Column(
        db.String(100),
        db.ForeignKey("exercise_identities.exercise_id"),
        nullable=False,
        index=True,
    )
    side = db.Column(db.String(8), nullable=True)
    advisory_fingerprint = db.Column(db.String(64), nullable=False, index=True)
    disposition = db.Column(db.String(16), nullable=False)
    reviewer_reference = db.Column(db.String(120), nullable=False)
    note = db.Column(db.Text, nullable=True)
    reviewed_at = db.Column(db.DateTime, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        db.CheckConstraint(
            "side IN ('left', 'right') OR side IS NULL",
            name="ck_progression_review_side",
        ),
        db.CheckConstraint(
            "disposition IN ('REVIEWED', 'ACKNOWLEDGED', 'DISMISSED')",
            name="ck_progression_review_disposition",
        ),
    )
