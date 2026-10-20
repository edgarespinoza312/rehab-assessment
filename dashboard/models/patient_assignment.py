"""Auditable clinician-to-patient assignment history."""

from datetime import datetime

from sqlalchemy import Index, text

from dashboard.database import db


class PatientAssignment(db.Model):
    __tablename__ = "patient_assignments"

    assignment_id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(
        db.Integer,
        db.ForeignKey("patients.patient_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    clinician_user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.user_id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    assigned_by_user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.user_id", ondelete="RESTRICT"),
        nullable=False,
    )
    assigned_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    ended_at = db.Column(db.DateTime, nullable=True)
    ended_by_user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.user_id", ondelete="RESTRICT"),
        nullable=True,
    )
    end_reason = db.Column(db.String(240), nullable=True)

    patient = db.relationship("Patient", backref=db.backref("assignments", lazy=True))
    clinician = db.relationship("User", foreign_keys=[clinician_user_id])
    assigned_by = db.relationship("User", foreign_keys=[assigned_by_user_id])
    ended_by = db.relationship("User", foreign_keys=[ended_by_user_id])

    __table_args__ = (
        db.CheckConstraint(
            "ended_at IS NULL OR ended_at >= assigned_at",
            name="ck_patient_assignments_end_after_start",
        ),
        Index(
            "uq_patient_assignments_one_active",
            "patient_id",
            unique=True,
            sqlite_where=text("ended_at IS NULL"),
            postgresql_where=text("ended_at IS NULL"),
        ),
    )
