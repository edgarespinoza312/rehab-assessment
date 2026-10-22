"""Structured safety case, hash-linked events, and corrective-action models.

The hash chain detects ordinary record alteration but is not a substitute for an
externally anchored, access-controlled immutable audit store.
"""
from datetime import datetime

from dashboard.database import db


class SafetyIncident(db.Model):
    __tablename__ = "safety_incidents"
    __table_args__ = (
        db.CheckConstraint(
            "severity IN ('low', 'moderate', 'serious', 'critical')",
            name="ck_safety_incident_severity",
        ),
        db.CheckConstraint(
            "likelihood IN ('unlikely', 'possible', 'likely', 'very_likely')",
            name="ck_safety_incident_likelihood",
        ),
        db.CheckConstraint(
            "evidence_strength IN ('weak', 'moderate', 'strong')",
            name="ck_safety_incident_evidence_strength",
        ),
        db.CheckConstraint(
            "exposure_count >= 1",
            name="ck_safety_incident_exposure_positive",
        ),
        db.CheckConstraint(
            "priority_tier IN ('routine', 'elevated', 'urgent', 'critical')",
            name="ck_safety_incident_priority",
        ),
        db.CheckConstraint(
            "status IN ('reported', 'investigating', 'restricted', 'awaiting_independent_review', 'closed', 'reopened')",
            name="ck_safety_incident_status",
        ),
        db.CheckConstraint(
            "root_cause_status IN ('not_assessed', 'known', 'unknown')",
            name="ck_safety_incident_root_cause_status",
        ),
    )

    incident_id = db.Column(db.Integer, primary_key=True)
    incident_key = db.Column(db.String(36), nullable=False, unique=True, index=True)
    category = db.Column(db.String(60), nullable=False)
    summary = db.Column(db.String(500), nullable=False)
    details = db.Column(db.Text, nullable=False, default="")
    severity = db.Column(db.String(16), nullable=False)
    likelihood = db.Column(db.String(16), nullable=False)
    evidence_strength = db.Column(db.String(16), nullable=False)
    exposure_count = db.Column(db.Integer, nullable=False, default=1)
    control_failure = db.Column(db.Boolean, nullable=False, default=False)
    risk_score = db.Column(db.Float, nullable=False)
    priority_tier = db.Column(db.String(16), nullable=False)
    status = db.Column(db.String(32), nullable=False, default="reported")
    restriction_scopes = db.Column(db.Text, nullable=False, default="[]")
    restriction_reason = db.Column(db.Text, nullable=True)
    root_cause_status = db.Column(db.String(16), nullable=False, default="not_assessed")
    root_cause_notes = db.Column(db.Text, nullable=True)
    reporter_user_id = db.Column(
        db.Integer, db.ForeignKey("users.user_id", ondelete="RESTRICT"),
        nullable=False, index=True,
    )
    owner_user_id = db.Column(
        db.Integer, db.ForeignKey("users.user_id", ondelete="RESTRICT"),
        nullable=True, index=True,
    )
    acknowledged_by_user_id = db.Column(
        db.Integer, db.ForeignKey("users.user_id", ondelete="RESTRICT"), nullable=True
    )
    independent_reviewer_user_id = db.Column(
        db.Integer, db.ForeignKey("users.user_id", ondelete="RESTRICT"), nullable=True
    )
    closed_by_user_id = db.Column(
        db.Integer, db.ForeignKey("users.user_id", ondelete="RESTRICT"), nullable=True
    )
    closure_rationale = db.Column(db.Text, nullable=True)
    external_board_reference = db.Column(db.String(255), nullable=True)
    reported_at = db.Column(db.DateTime, nullable=False)
    acknowledged_at = db.Column(db.DateTime, nullable=True)
    next_review_at = db.Column(db.DateTime, nullable=False)
    response_due_at = db.Column(db.DateTime, nullable=False)
    closed_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(
        db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    reporter = db.relationship("User", foreign_keys=[reporter_user_id])
    owner = db.relationship("User", foreign_keys=[owner_user_id])
    independent_reviewer = db.relationship("User", foreign_keys=[independent_reviewer_user_id])
    closed_by = db.relationship("User", foreign_keys=[closed_by_user_id])
    events = db.relationship(
        "SafetyIncidentEvent",
        back_populates="incident",
        order_by="SafetyIncidentEvent.event_id",
        passive_deletes=True,
    )
    corrective_actions = db.relationship(
        "SafetyCorrectiveAction",
        back_populates="incident",
        order_by="SafetyCorrectiveAction.action_id",
        passive_deletes=True,
    )


class SafetyIncidentEvent(db.Model):
    """Append-only-by-service, hash-linked case history."""
    __tablename__ = "safety_incident_events"

    event_id = db.Column(db.Integer, primary_key=True)
    incident_id = db.Column(
        db.Integer, db.ForeignKey("safety_incidents.incident_id", ondelete="RESTRICT"),
        nullable=False, index=True,
    )
    actor_user_id = db.Column(
        db.Integer, db.ForeignKey("users.user_id", ondelete="RESTRICT"), nullable=False
    )
    event_type = db.Column(db.String(80), nullable=False)
    previous_status = db.Column(db.String(32), nullable=False)
    new_status = db.Column(db.String(32), nullable=False)
    detail = db.Column(db.Text, nullable=False, default="")
    occurred_at = db.Column(db.DateTime, nullable=False)
    previous_hash = db.Column(db.String(64), nullable=False)
    event_hash = db.Column(db.String(64), nullable=False, unique=True)

    incident = db.relationship("SafetyIncident", back_populates="events")
    actor = db.relationship("User")


class SafetyCorrectiveAction(db.Model):
    """Corrective/preventive action with separate completion and verification."""
    __tablename__ = "safety_corrective_actions"
    __table_args__ = (
        db.CheckConstraint(
            "status IN ('open', 'in_progress', 'completed', 'verified', 'cancelled')",
            name="ck_safety_action_status",
        ),
    )

    action_id = db.Column(db.Integer, primary_key=True)
    incident_id = db.Column(
        db.Integer, db.ForeignKey("safety_incidents.incident_id", ondelete="RESTRICT"),
        nullable=False, index=True,
    )
    title = db.Column(db.String(240), nullable=False)
    description = db.Column(db.Text, nullable=False, default="")
    owner_user_id = db.Column(
        db.Integer, db.ForeignKey("users.user_id", ondelete="RESTRICT"),
        nullable=False, index=True,
    )
    created_by_user_id = db.Column(
        db.Integer, db.ForeignKey("users.user_id", ondelete="RESTRICT"), nullable=False
    )
    status = db.Column(db.String(16), nullable=False, default="open")
    due_at = db.Column(db.DateTime, nullable=False)
    completed_at = db.Column(db.DateTime, nullable=True)
    completion_evidence = db.Column(db.Text, nullable=True)
    verified_by_user_id = db.Column(
        db.Integer, db.ForeignKey("users.user_id", ondelete="RESTRICT"), nullable=True
    )
    verified_at = db.Column(db.DateTime, nullable=True)
    effectiveness_result = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(
        db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    incident = db.relationship("SafetyIncident", back_populates="corrective_actions")
    owner = db.relationship("User", foreign_keys=[owner_user_id])
    created_by = db.relationship("User", foreign_keys=[created_by_user_id])
    verified_by = db.relationship("User", foreign_keys=[verified_by_user_id])
