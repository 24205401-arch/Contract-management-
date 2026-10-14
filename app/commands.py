import click
from flask import current_app

from . import models as m


def register_commands(app):
    @app.cli.command("seed-demo")
    def seed_demo():
        """Creates demo users, companies, and a sample work order."""
        if m.username_exists("staffuser"):
            click.echo("Demo data already exists — skipping.")
            return

        m.create_user("staffuser", "staff@example.com", "testpass123", None, "admin")

        client_co = m.create_company("Acme Builders", m.ROLE_CLIENT, email="acme@example.com")
        m.create_user("acmeuser", "acme@example.com", "testpass123", client_co["_id"], "admin")

        partner_co = m.create_company("FastFix Plumbing Co", m.ROLE_PARTNER, email="fastfix@example.com")
        m.create_user("fastfixuser", "fastfix@example.com", "testpass123", partner_co["_id"], "admin")

        order = m.create_work_order(
            client_co["_id"], "Fix office restroom pipes", "Two leaking pipes, one blocked drain.",
            m.TYPE_PLUMBING, 15000, None,
        )
        m.create_quote(order["_id"], 14000, "Includes parts")
        m.create_subcontract(order["_id"], partner_co["_id"], 12000, "Overflow work")

        click.echo(
            "Demo data created.\n"
            "  staff login:    staffuser / testpass123  (our own company)\n"
            "  client login:   acmeuser / testpass123   (Acme Builders)\n"
            "  partner login:  fastfixuser / testpass123 (FastFix Plumbing Co)\n"
        )

    @app.cli.command("create-staff")
    @click.argument("username")
    @click.option("--email", default="", help="Optional email address.")
    @click.password_option()
    def create_staff(username, email, password):
        """Creates an internal staff account. Not available via public signup on purpose."""
        if m.username_exists(username):
            click.echo(f"Username '{username}' is already taken.")
            return
        m.create_user(username, email, password, None, "admin")
        click.echo(f"Staff account '{username}' created.")
