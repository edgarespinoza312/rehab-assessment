from dashboard.models import Role, User
from dashboard.services.authentication import hash_password


def seed_clinician(app, *, email="clinician@test.invalid"):
    user = User(
        display_name="Test Clinician",
        email=email,
        password_hash=hash_password("test-password"),
    )
    user.roles = [Role(name="CLINICIAN")]
    from dashboard.database import db
    db.session.add(user)
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
