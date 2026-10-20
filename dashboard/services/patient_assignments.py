"""Assignment lifecycle operations with durable audit history."""

from datetime import datetime

from sqlalchemy.exc import IntegrityError

from dashboard.database import db
from dashboard.models import Patient, PatientAssignment, Role, User


class AssignmentError(ValueError):
    """Raised when an assignment transition violates policy."""


def active_assignment(patient_id):
    return PatientAssignment.query.filter_by(
        patient_id=patient_id,
        ended_at=None,
    ).one_or_none()


def active_assignments_for_clinician(user_id):
    return PatientAssignment.query.filter_by(
        clinician_user_id=user_id,
        ended_at=None,
    ).order_by(PatientAssignment.assigned_at.desc()).all()


def _has_role(user, role_name):
    return user is not None and any(role.name == role_name for role in user.roles)


def assign_patient(
    patient_id,
    clinician_user_id,
    actor_user_id,
    *,
    allow_reassignment=False,
    reason=None,
):
    """Assign an unassigned patient, or reassign only when explicitly permitted."""
    patient = db.session.get(Patient, patient_id)
    clinician = db.session.get(User, clinician_user_id)
    actor = db.session.get(User, actor_user_id)

    if patient is None:
        raise AssignmentError("Patient does not exist.")
    if clinician is None or clinician.status != "ACTIVE" or not _has_role(clinician, "CLINICIAN"):
        raise AssignmentError("The selected account is not an active clinician.")
    if actor is None or actor.status != "ACTIVE":
        raise AssignmentError("The assigning account is not active.")

    actor_is_admin = _has_role(actor, "ADMIN")
    actor_is_clinician_claiming_self = (
        _has_role(actor, "CLINICIAN") and actor.user_id == clinician.user_id
    )
    if not actor_is_admin and not actor_is_clinician_claiming_self:
        raise AssignmentError("Only an admin or the receiving clinician may assign this patient.")
    if allow_reassignment and not actor_is_admin:
        raise AssignmentError("Only an admin may reassign an already assigned patient.")

    current = active_assignment(patient_id)
    if current is not None and current.clinician_user_id == clinician_user_id:
        return current
    if current is not None and not allow_reassignment:
        raise AssignmentError("This patient is already assigned to another clinician.")

    now = datetime.utcnow()
    try:
        if current is not None:
            current.ended_at = now
            current.ended_by_user_id = actor.user_id
            current.end_reason = (reason or "Reassigned by admin")[:240]
            db.session.flush()

        assignment = PatientAssignment(
            patient_id=patient.patient_id,
            clinician_user_id=clinician.user_id,
            assigned_by_user_id=actor.user_id,
            assigned_at=now,
        )
        db.session.add(assignment)
        db.session.commit()
        return assignment
    except IntegrityError as exc:
        db.session.rollback()
        raise AssignmentError("The assignment changed concurrently; refresh and try again.") from exc


def end_assignment(patient_id, actor_user_id, reason):
    """End an active assignment without deleting its audit record."""
    actor = db.session.get(User, actor_user_id)
    if actor is None or actor.status != "ACTIVE" or not _has_role(actor, "ADMIN"):
        raise AssignmentError("Only an active admin may revoke a patient assignment.")

    assignment = active_assignment(patient_id)
    if assignment is None:
        return None

    assignment.ended_at = datetime.utcnow()
    assignment.ended_by_user_id = actor.user_id
    assignment.end_reason = (reason or "Revoked by admin")[:240]
    db.session.commit()
    return assignment
