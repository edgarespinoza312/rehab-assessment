"""Trusted local CLI commands for application administration."""

import click
from flask.cli import with_appcontext

from dashboard.database import db
from dashboard.models import Role, User
from dashboard.services.authentication import hash_password
from dashboard.services.user_provisioning import create_user, normalize_email


@click.command("bootstrap-admin")
@with_appcontext
def bootstrap_admin_command():
    """Create the first administrator account on a trusted local installation."""
    existing_admin = (
        User.query.join(User.roles)
        .filter(Role.name == "ADMIN")
        .first()
    )
    if existing_admin is not None:
        raise click.ClickException(
            "An administrator account already exists. "
            "Use the account recovery process instead of bootstrapping another."
        )

    display_name = click.prompt("Admin display name").strip()
    email = click.prompt("Admin email").strip()
    password = click.prompt(
        "Admin password",
        hide_input=True,
        confirmation_prompt="Confirm admin password",
    )

    try:
        user = create_user(
            display_name=display_name,
            email=email,
            password=password,
            role="ADMIN",
        )
    except ValueError as error:
        raise click.ClickException(str(error)) from error

    click.echo(f"Administrator account created for {user.email}.")


@click.command("recover-admin")
@with_appcontext
def recover_admin_command():
    """Reactivate an existing administrator and reset its password locally."""
    try:
        email = normalize_email(click.prompt("Existing administrator email"))
    except ValueError as error:
        raise click.ClickException(str(error)) from error

    user = User.query.filter_by(email=email).first()
    if user is None or not any(role.name == "ADMIN" for role in user.roles):
        raise click.ClickException(
            "No existing administrator account matches that email. "
            "This command does not create accounts or grant administrator access."
        )

    password = click.prompt(
        "New administrator password",
        hide_input=True,
        confirmation_prompt="Confirm new administrator password",
    )
    try:
        user.password_hash = hash_password(password)
        user.status = "ACTIVE"
        db.session.commit()
    except ValueError as error:
        db.session.rollback()
        raise click.ClickException(str(error)) from error
    except Exception:
        db.session.rollback()
        raise

    click.echo(
        f"Administrator account recovered for {user.email}. "
        "Sign in with the new password."
    )


def register_cli_commands(app):
    """Register trusted local maintenance commands with the Flask app."""
    app.cli.add_command(bootstrap_admin_command)
    app.cli.add_command(recover_admin_command)
