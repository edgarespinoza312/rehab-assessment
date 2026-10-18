"""Controlled, server-side user provisioning for the prototype."""

import re

from dashboard.database import db
from dashboard.models import Patient, Role, User
from dashboard.services.authentication import hash_password

# OPERATOR remains in the schema for existing accounts, but is not provisionable
# until its intended workspace and capabilities are defined.
VALID_ROLES = {"PATIENT", "CLINICIAN", "ADMIN"}
MAX_DISPLAY_NAME_LENGTH = 120
MAX_EMAIL_LENGTH = 255
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _role(name: str) -> Role:
    if name not in VALID_ROLES:
        raise ValueError(f"invalid role: {name}")
    role = Role.query.filter_by(name=name).first()
    if role is None:
        role = Role(name=name)
        db.session.add(role)
        db.session.flush()
    return role


def create_user(*, display_name, email, password, role, patient_id=None):
    """Create an active user; callers must be trusted server-side code."""
    if not isinstance(display_name, str) or not display_name.strip():
        raise ValueError("display_name is required")
    normalized_display_name = display_name.strip()
    if len(normalized_display_name) > MAX_DISPLAY_NAME_LENGTH:
        raise ValueError(
            f"display_name must be at most {MAX_DISPLAY_NAME_LENGTH} characters"
        )
    normalized_email = normalize_email(email)
    if role not in VALID_ROLES:
        raise ValueError(f"invalid role: {role}")
    if User.query.filter_by(email=normalized_email).first() is not None:
        raise ValueError("email is already in use")
    patient = None
    if patient_id is not None:
        patient = db.session.get(Patient, patient_id)
        if patient is None:
            raise ValueError("patient does not exist")
        if User.query.filter_by(patient_id=patient_id).first() is not None:
            raise ValueError("patient is already linked")

    # Validate/hash before creating a role row or any other database state.
    password_hash = hash_password(password)
    try:
        role_obj = _role(role)
        user = User(
            display_name=normalized_display_name,
            email=normalized_email,
            password_hash=password_hash,
            status="ACTIVE",
            patient=patient,
        )
        user.roles.append(role_obj)
        db.session.add(user)
        db.session.commit()
        return user
    except Exception:
        db.session.rollback()
        raise

def normalize_email(email: str) -> str:
    if not isinstance(email, str):
        raise ValueError("email is required")
    normalized = email.strip().lower()
    if len(normalized) > MAX_EMAIL_LENGTH:
        raise ValueError(f"email must be at most {MAX_EMAIL_LENGTH} characters")
    if not normalized or not EMAIL_PATTERN.fullmatch(normalized):
        raise ValueError("enter a valid email address")
    return normalized


def create_patient_account(*, display_name, email, password):
    """Create and link a new patient account atomically."""
    if not isinstance(display_name, str) or not display_name.strip():
        raise ValueError("display name is required")
    normalized_display_name = display_name.strip()
    if len(normalized_display_name) > MAX_DISPLAY_NAME_LENGTH:
        raise ValueError(
            f"display name must be at most {MAX_DISPLAY_NAME_LENGTH} characters"
        )
    parts = normalized_display_name.split(maxsplit=1)
    first_name = parts[0]
    last_name = parts[1] if len(parts) == 2 else "Patient"
    patient = Patient(first_name=first_name[:50], last_name=last_name[:50])
    db.session.add(patient)
    db.session.flush()
    try:
        user = create_user(
            display_name=normalized_display_name,
            email=email,
            password=password,
            role="PATIENT",
            patient_id=patient.patient_id,
        )
    except Exception:
        db.session.rollback()
        raise
    return user


def disable_user(user_id: int):
    user = db.session.get(User, user_id)
    if user is None:
        raise ValueError("user does not exist")
    user.status = "DISABLED"
    db.session.commit()
    return user


def assign_role(user_id: int, role: str):
    user = db.session.get(User, user_id)
    if user is None:
        raise ValueError("user does not exist")
    role_obj = _role(role)
    if role_obj not in user.roles:
        user.roles.append(role_obj)
        db.session.commit()
    return user


def link_patient(user_id: int, patient_id: int):
    user = db.session.get(User, user_id)
    patient = db.session.get(Patient, patient_id)
    if user is None or patient is None:
        raise ValueError("user or patient does not exist")
    linked = User.query.filter(
        User.patient_id == patient_id,
        User.user_id != user_id,
    ).first()
    if linked is not None:
        raise ValueError("patient is already linked")
    user.patient = patient
    db.session.commit()
    return user


def unlink_patient(user_id: int):
    user = db.session.get(User, user_id)
    if user is None:
        raise ValueError("user does not exist")
    user.patient = None
    db.session.commit()
    return user
