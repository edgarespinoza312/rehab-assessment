from dashboard.models import Patient, PatientAssignment, Role, User
from dashboard.services.authentication import hash_password


def seed_clinician(app, *, email="clinician@test.invalid"):
    """Create a test clinician and assign existing unassigned test patients.

    Reuse the unique role row rather than inserting a duplicate role for every
    test fixture. Real authorization tests that need an unassigned clinician
    should build that fixture explicitly instead of using this convenience
    helper.
    """
    from dashboard.database import db

    role = Role.query.filter_by(name="CLINICIAN").one_or_none()
    if role is None:
        role = Role(name="CLINICIAN")
        db.session.add(role)
        db.session.flush()

    user = User(
        display_name="Test Clinician",
        email=email,
        password_hash=hash_password("test-password"),
    )
    user.roles = [role]
    db.session.add(user)
    db.session.flush()

    # Most existing API/workflow tests assume their seeded clinician can
    # access the patients created in setUp. Make that relationship explicit
    # under the new assignment policy, without taking patients away from an
    # already assigned clinician.
    for patient in Patient.query.all():
        active = PatientAssignment.query.filter_by(
            patient_id=patient.patient_id,
            ended_at=None,
        ).first()
        if active is None:
            db.session.add(PatientAssignment(
                patient_id=patient.patient_id,
                clinician_user_id=user.user_id,
                assigned_by_user_id=user.user_id,
            ))

    db.session.commit()
    return user


def login_client(app, client, *, email="clinician@test.invalid"):
    with client.session_transaction() as session:
        session.clear()
    client.get("/login")
    with client.session_transaction() as session:
        csrf = session["revaliv_csrf_token"]
    response = client.post("/login", data={
        "csrf_token": csrf,
        "email": email,
        "password": "test-password",
        "role": "CLINICIAN",
    })
    assert response.status_code == 302
    return client


def request_with_auth(app, method, path, **kwargs):
    client = app.test_client()
    login_client(app, client)
    if method.lower() == "post":
        client.get("/login")
        with client.session_transaction() as session:
            csrf = session["revaliv_csrf_token"]
        if kwargs.get("json") is not None:
            headers = dict(kwargs.get("headers") or {})
            headers["X-CSRF-Token"] = csrf
            kwargs["headers"] = headers
        else:
            data = dict(kwargs.get("data") or {})
            data.setdefault("csrf_token", csrf)
            kwargs["data"] = data
    return getattr(client, method.lower())(path, **kwargs)
