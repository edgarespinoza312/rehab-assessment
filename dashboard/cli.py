"""Trusted local CLI commands for application administration."""

import click
from flask.cli import with_appcontext

from dashboard.models import Role, User
from dashboard.services.user_provisioning import create_user


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


def register_cli_commands(app):
    """Register trusted local maintenance commands with the Flask app."""
    app.cli.add_command(bootstrap_admin_command)
