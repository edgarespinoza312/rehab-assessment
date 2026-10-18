"""Application identity and normalized role models.

These models establish domain boundaries only. They do not authenticate users.
"""

from datetime import datetime

from dashboard.database import db


class User(db.Model):
    __tablename__ = "users"

    user_id = db.Column(db.Integer, primary_key=True)
    display_name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(255), nullable=True, unique=True, index=True)
    password_hash = db.Column(db.String(255), nullable=True)
    status = db.Column(db.String(16), nullable=False, default="ACTIVE")
    patient_id = db.Column(
        db.Integer,
        db.ForeignKey("patients.patient_id", ondelete="SET NULL"),
        nullable=True,
        unique=True,
        index=True,
    )
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    patient = db.relationship("Patient", back_populates="user", uselist=False)
    roles = db.relationship(
        "Role",
        secondary="user_roles",
        back_populates="users",
    )

    __table_args__ = (
        db.CheckConstraint(
            "status IN ('ACTIVE', 'DISABLED')",
            name="ck_users_status",
        ),
    )


class Role(db.Model):
    __tablename__ = "roles"

    role_id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(32), nullable=False, unique=True)
    users = db.relationship(
        "User",
        secondary="user_roles",
        back_populates="roles",
    )

    __table_args__ = (
        db.CheckConstraint(
            "name IN ('PATIENT', 'CLINICIAN', 'ADMIN', 'OPERATOR')",
            name="ck_roles_name",
        ),
    )


class UserRole(db.Model):
    __tablename__ = "user_roles"

    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.user_id", ondelete="CASCADE"),
        primary_key=True,
    )
    role_id = db.Column(
        db.Integer,
        db.ForeignKey("roles.role_id", ondelete="CASCADE"),
        primary_key=True,
    )
