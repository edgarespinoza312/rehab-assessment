"""Auditable overlays for correcting assessment reports without mutating originals."""
from datetime import datetime

from dashboard.database import db


class AssessmentCorrection(db.Model):
    __tablename__ = "assessment_corrections"
    __table_args__ = (
        db.CheckConstraint(
            "field_name IN ('exercise', 'repetitions', 'average_score', 'best_score', 'worst_score', 'trend', 'feedback')",
            name="ck_assessment_correction_field",
        ),
        db.CheckConstraint(
            "status IN ('pending', 'accepted', 'rejected', 'stale')",
            name="ck_assessment_correction_status",
        ),
    )

    correction_id = db.Column(db.Integer, primary_key=True)
    assessment_id = db.Column(
        db.Integer,
        db.ForeignKey("assessment_records.assessment_id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    patient_id = db.Column(
        db.Integer,
        db.ForeignKey("patients.patient_id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    field_name = db.Column(db.String(32), nullable=False)
    original_value_json = db.Column(db.Text, nullable=False)
    proposed_value_json = db.Column(db.Text, nullable=False)
    source_snapshot_hash = db.Column(db.String(64), nullable=False)
    reason = db.Column(db.Text, nullable=False)
    evidence_reference = db.Column(db.String(500), nullable=True)
    status = db.Column(db.String(16), nullable=False, default="pending")
    requested_by_user_id = db.Column(
        db.Integer, db.ForeignKey("users.user_id", ondelete="RESTRICT"), nullable=False
    )
    reviewed_by_user_id = db.Column(
        db.Integer, db.ForeignKey("users.user_id", ondelete="RESTRICT"), nullable=True
    )
    review_rationale = db.Column(db.Text, nullable=True)
    requested_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    reviewed_at = db.Column(db.DateTime, nullable=True)

    assessment = db.relationship("AssessmentRecord")
    patient = db.relationship("Patient")
    requested_by = db.relationship("User", foreign_keys=[requested_by_user_id])
    reviewed_by = db.relationship("User", foreign_keys=[reviewed_by_user_id])
    events = db.relationship(
        "AssessmentCorrectionEvent",
        back_populates="correction",
        order_by="AssessmentCorrectionEvent.event_id",
        passive_deletes=True,
    )


class AssessmentCorrectionEvent(db.Model):
    """Hash-linked event history for the correction request lifecycle."""
    __tablename__ = "assessment_correction_events"

    event_id = db.Column(db.Integer, primary_key=True)
    correction_id = db.Column(
        db.Integer,
        db.ForeignKey("assessment_corrections.correction_id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    actor_user_id = db.Column(
        db.Integer, db.ForeignKey("users.user_id", ondelete="RESTRICT"), nullable=False
    )
    event_type = db.Column(db.String(32), nullable=False)
    previous_status = db.Column(db.String(16), nullable=False)
    new_status = db.Column(db.String(16), nullable=False)
    detail = db.Column(db.Text, nullable=False)
    occurred_at = db.Column(db.DateTime, nullable=False)
    previous_hash = db.Column(db.String(64), nullable=False)
    event_hash = db.Column(db.String(64), nullable=False, unique=True)

    correction = db.relationship("AssessmentCorrection", back_populates="events")
    actor = db.relationship("User")
