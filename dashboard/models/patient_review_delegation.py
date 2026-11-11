"""Narrow, revocable, purpose-specific independent clinical review delegation."""
from datetime import datetime

from dashboard.database import db


class PatientReviewDelegation(db.Model):
    """A temporary review-only grant that never conveys general patient access."""
    __tablename__ = "patient_review_delegations"
    __table_args__ = (
        db.CheckConstraint(
            "scope IN ('plan_approval', 'assessment_correction')",
            name="ck_patient_review_delegation_scope",
        ),
        db.CheckConstraint(
            "delegated_to_user_id != delegated_by_user_id",
            name="ck_patient_review_delegation_distinct_users",
        ),
        db.CheckConstraint(
            "length(reason) >= 8",
            name="ck_patient_review_delegation_reason",
        ),
    )

    delegation_id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(
        db.Integer, db.ForeignKey("patients.patient_id", ondelete="RESTRICT"),
        nullable=False, index=True,
    )
    delegated_to_user_id = db.Column(
        db.Integer, db.ForeignKey("users.user_id", ondelete="RESTRICT"),
        nullable=False, index=True,
    )
    delegated_by_user_id = db.Column(
        db.Integer, db.ForeignKey("users.user_id", ondelete="RESTRICT"),
        nullable=False,
    )
    scope = db.Column(db.String(32), nullable=False)
    reason = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    revoked_at = db.Column(db.DateTime, nullable=True)
    revoked_by_user_id = db.Column(
        db.Integer, db.ForeignKey("users.user_id", ondelete="RESTRICT"),
        nullable=True,
    )
    revocation_reason = db.Column(db.Text, nullable=True)

    patient = db.relationship("Patient")
    delegated_to = db.relationship("User", foreign_keys=[delegated_to_user_id])
    delegated_by = db.relationship("User", foreign_keys=[delegated_by_user_id])
    revoked_by = db.relationship("User", foreign_keys=[revoked_by_user_id])

    @property
    def active(self) -> bool:
        return self.revoked_at is None
