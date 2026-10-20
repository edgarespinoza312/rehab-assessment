import unittest

from dashboard.app import app
from dashboard.database import db
from dashboard.models import Role, User


class BootstrapAdminCommandTests(unittest.TestCase):
    def setUp(self):
        self.context = app.app_context()
        self.context.push()
        db.session.rollback()
        db.drop_all()
        db.create_all()

    def tearDown(self):
        db.session.rollback()
        db.drop_all()
        db.create_all()
        self.context.pop()

    def test_bootstrap_creates_first_admin_with_hidden_password_prompt(self):
        result = app.test_cli_runner().invoke(
            args=["bootstrap-admin"],
            input="Initial Admin\nadmin@example.test\n"
                  "correct horse battery staple\n"
                  "correct horse battery staple\n",
        )

        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("Administrator account created for admin@example.test.", result.output)
        user = User.query.filter_by(email="admin@example.test").one()
        self.assertEqual({role.name for role in user.roles}, {"ADMIN"})
        self.assertTrue(user.password_hash)
        self.assertNotEqual(user.password_hash, "correct horse battery staple")

    def test_bootstrap_refuses_to_create_second_admin(self):
        role = Role(name="ADMIN")
        user = User(
            display_name="Existing Admin",
            email="existing-admin@example.test",
            password_hash="existing-hash",
            status="ACTIVE",
        )
        user.roles.append(role)
        db.session.add(user)
        db.session.commit()

        result = app.test_cli_runner().invoke(args=["bootstrap-admin"])

        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("administrator account already exists", result.output.lower())
        self.assertEqual(User.query.filter(User.roles.any(Role.name == "ADMIN")).count(), 1)
