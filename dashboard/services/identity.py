"""Identity context and centralized prototype authorization boundary."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from dashboard.models import PatientAssignment, User


class UserStatus(str, Enum):
    ACTIVE = "ACTIVE"
    DISABLED = "DISABLED"


class ApplicationRole(str, Enum):
    PATIENT = "PATIENT"
    CLINICIAN = "CLINICIAN"
    ADMIN = "ADMIN"
    OPERATOR = "OPERATOR"


class Capability(str, Enum):
    ACCESS_PATIENT_PORTAL = "ACCESS_PATIENT_PORTAL"
    ACCESS_CLINICIAN_PORTAL = "ACCESS_CLINICIAN_PORTAL"
    VIEW_OWN_PATIENT_DATA = "VIEW_OWN_PATIENT_DATA"
    START_OWN_ASSESSMENT = "START_OWN_ASSESSMENT"
    VIEW_OWN_RESULTS = "VIEW_OWN_RESULTS"
    VIEW_OWN_PROGRESSION = "VIEW_OWN_PROGRESSION"
    VIEW_ASSIGNED_PATIENT = "VIEW_ASSIGNED_PATIENT"
    VIEW_PATIENT_PROGRESSION = "VIEW_PATIENT_PROGRESSION"
    VIEW_ADVISORY = "VIEW_ADVISORY"
    REVIEW_ADVISORY = "REVIEW_ADVISORY"
    MANAGE_ACCOUNTS = "MANAGE_ACCOUNTS"
    CREATE_WORKOUT_PLAN = "CREATE_WORKOUT_PLAN"
    ACCESS_ASSESSMENT_SETUP = "ACCESS_ASSESSMENT_SETUP"
    DELETE_PATIENT_RECORD = "DELETE_PATIENT_RECORD"
    DELETE_ASSESSMENT_RECORD = "DELETE_ASSESSMENT_RECORD"


@dataclass(frozen=True)
class IdentityContext:
    """Server-owned identity passed to authorization checks."""

    user_id: int | None
    roles: frozenset[ApplicationRole]
    trust_state: str = "anonymous"
    patient_id: int | None = None
    status: UserStatus | None = None

    @property
    def is_authenticated(self) -> bool:
        return self.user_id is not None

    @property
    def is_trusted_development_identity(self) -> bool:
        return self.trust_state == "trusted-development"


def anonymous_identity() -> IdentityContext:
    return IdentityContext(user_id=None, roles=frozenset())


def trusted_development_identity(
    user_id: int,
    *,
    roles: set[ApplicationRole] | frozenset[ApplicationRole],
    patient_id: int | None = None,
) -> IdentityContext:
    """Create a test/local identity; never derive this from browser input."""

    return IdentityContext(
        user_id=user_id,
        roles=frozenset(roles),
        trust_state="trusted-development",
        patient_id=patient_id,
        status=UserStatus.ACTIVE,
    )


def identity_from_user(user: User) -> IdentityContext:
    """Adapt a persisted user for a future authenticated identity adapter."""

    return IdentityContext(
        user_id=user.user_id,
        roles=frozenset(ApplicationRole(role.name) for role in user.roles),
        trust_state="authenticated-adapter",
        patient_id=user.patient_id,
        status=UserStatus(user.status),
    )


class AuthorizationService:
    """Central policy boundary; clinical access requires an active assignment."""

    @staticmethod
    def _has_active_assignment(identity: IdentityContext, patient_id: int) -> bool:
        if identity.is_trusted_development_identity:
            return True
        return PatientAssignment.query.filter_by(
            patient_id=patient_id,
            clinician_user_id=identity.user_id,
            ended_at=None,
        ).first() is not None

    @staticmethod
    def can(
        identity: IdentityContext,
        capability: Capability,
        *,
        patient_id: int | None = None,
    ) -> bool:
        if not identity.is_authenticated or identity.status != UserStatus.ACTIVE:
            return False
        if identity.trust_state not in {
            "trusted-development",
            "authenticated-adapter",
        }:
            return False

        patient_role = ApplicationRole.PATIENT in identity.roles
        clinician_role = ApplicationRole.CLINICIAN in identity.roles

        if capability in {
            Capability.CREATE_WORKOUT_PLAN,
            Capability.ACCESS_ASSESSMENT_SETUP,
        }:
            return patient_role or clinician_role

        if capability in {
            Capability.ACCESS_PATIENT_PORTAL,
            Capability.VIEW_OWN_PATIENT_DATA,
            Capability.START_OWN_ASSESSMENT,
            Capability.VIEW_OWN_RESULTS,
            Capability.VIEW_OWN_PROGRESSION,
        }:
            return (
                patient_role
                and patient_id is not None
                and identity.patient_id == patient_id
            )

        if capability == Capability.ACCESS_CLINICIAN_PORTAL:
            return clinician_role

        if capability == Capability.MANAGE_ACCOUNTS:
            return ApplicationRole.ADMIN in identity.roles

        if capability == Capability.VIEW_PATIENT_PROGRESSION:
            return (
                (
                    patient_role
                    and patient_id is not None
                    and identity.patient_id == patient_id
                )
                or (
                    clinician_role
                    and patient_id is not None
                    and AuthorizationService._has_active_assignment(identity, patient_id)
                )
            )

        if capability in {
            Capability.VIEW_ASSIGNED_PATIENT,
            Capability.VIEW_ADVISORY,
            Capability.REVIEW_ADVISORY,
            Capability.DELETE_PATIENT_RECORD,
            Capability.DELETE_ASSESSMENT_RECORD,
        }:
            return (
                clinician_role
                and patient_id is not None
                and AuthorizationService._has_active_assignment(identity, patient_id)
            )

        return False


def can(
    identity: IdentityContext,
    capability: Capability,
    *,
    patient_id: int | None = None,
) -> bool:
    """Convenience wrapper around the centralized authorization service."""

    return AuthorizationService.can(
        identity,
        capability,
        patient_id=patient_id,
    )
