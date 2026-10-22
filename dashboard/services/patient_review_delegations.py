"""Purpose-specific clinical review delegation with assignment-bound revocation."""
from datetime import datetime

from dashboard.database import db
from dashboard.models import PatientReviewDelegation, User
from dashboard.services.patient_assignments import active_assignment


VALID_REVIEW_SCOPES = {"plan_approval", "assessment_correction"}


class ReviewDelegationError(ValueError):
    """Invalid or unauthorized review-delegation request."""


def create_review_delegation(
    patient_id: int,
    actor_user_id: int,
    reviewer_user_id: int,
    *,
    scope: str,
    reason: str,
) -> PatientReviewDelegation:
    actor = db.session.get(User, actor_user_id)
    reviewer = db.session.get(User, reviewer_user_id)
    assignment = active_assignment(patient_id)
    if actor is None or actor.status != "ACTIVE" or not any(
        role.name == "CLINICIAN" for role in actor.roles
    ):
        raise ReviewDelegationError("an active clinician must grant the review")
    if assignment is None or assignment.clinician_user_id != actor.user_id:
        raise ReviewDelegationError("only the currently assigned clinician may delegate review")
    if reviewer is None or reviewer.status != "ACTIVE" or not any(
        role.name == "CLINICIAN" for role in reviewer.roles
    ):
        raise ReviewDelegationError("reviewer must be an active clinician")
    if reviewer.user_id == actor.user_id:
        raise ReviewDelegationError("reviewer must be independent of the delegating clinician")
    if not isinstance(scope, str) or scope not in VALID_REVIEW_SCOPES:
        raise ReviewDelegationError("scope must be plan_approval or assessment_correction")
    if not isinstance(reason, str) or not 8 <= len(reason.strip()) <= 4000:
        raise ReviewDelegationError("reason must be 8 to 4000 characters")

    existing = PatientReviewDelegation.query.filter_by(
        patient_id=patient_id,
        delegated_to_user_id=reviewer.user_id,
        delegated_by_user_id=actor.user_id,
        scope=scope,
        revoked_at=None,
    ).first()
    if existing is not None:
        raise ReviewDelegationError("an equivalent active delegation already exists")

    delegation = PatientReviewDelegation(
        patient_id=patient_id,
        delegated_to_user_id=reviewer.user_id,
        delegated_by_user_id=actor.user_id,
        scope=scope,
        reason=reason.strip(),
        created_at=datetime.utcnow(),
    )
    db.session.add(delegation)
    db.session.commit()
    return delegation


def has_active_review_delegation(
    reviewer_user_id: int,
    patient_id: int,
    scope: str,
) -> bool:
    """Delegation is narrow and valid only while its grantor retains assignment."""
    if scope not in VALID_REVIEW_SCOPES:
        return False
    reviewer = db.session.get(User, reviewer_user_id)
    if reviewer is None or reviewer.status != "ACTIVE" or not any(
        role.name == "CLINICIAN" for role in reviewer.roles
    ):
        return False
    assignment = active_assignment(patient_id)
    if assignment is None:
        return False
    return PatientReviewDelegation.query.filter_by(
        patient_id=patient_id,
        delegated_to_user_id=reviewer_user_id,
        delegated_by_user_id=assignment.clinician_user_id,
        scope=scope,
        revoked_at=None,
    ).first() is not None


def revoke_review_delegation(
    delegation_id: int,
    actor_user_id: int,
    *,
    reason: str,
) -> PatientReviewDelegation:
    actor = db.session.get(User, actor_user_id)
    if actor is None or actor.status != "ACTIVE":
        raise ReviewDelegationError("active user is required to revoke a delegation")
    if not isinstance(reason, str) or not 8 <= len(reason.strip()) <= 4000:
        raise ReviewDelegationError("revocation reason must be 8 to 4000 characters")
    delegation = db.session.get(PatientReviewDelegation, delegation_id)
    if delegation is None:
        raise LookupError(f"review delegation {delegation_id} does not exist")
    roles = {role.name for role in actor.roles}
    if actor.user_id != delegation.delegated_by_user_id and "ADMIN" not in roles:
        raise ReviewDelegationError("only the grantor or an active admin may revoke this delegation")
    if delegation.revoked_at is not None:
        raise ReviewDelegationError("review delegation is already revoked")
    delegation.revoked_at = datetime.utcnow()
    delegation.revoked_by_user_id = actor.user_id
    delegation.revocation_reason = reason.strip()
    db.session.commit()
    return delegation


def delegation_to_dict(delegation: PatientReviewDelegation) -> dict:
    return {
        "delegation_id": delegation.delegation_id,
        "patient_id": delegation.patient_id,
        "delegated_to_user_id": delegation.delegated_to_user_id,
        "delegated_by_user_id": delegation.delegated_by_user_id,
        "scope": delegation.scope,
        "reason": delegation.reason,
        "created_at": delegation.created_at.isoformat(),
        "active": delegation.active,
        "revoked_at": delegation.revoked_at.isoformat() if delegation.revoked_at else None,
        "revoked_by_user_id": delegation.revoked_by_user_id,
        "revocation_reason": delegation.revocation_reason,
    }
