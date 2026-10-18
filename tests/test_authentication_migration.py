import importlib.util
from pathlib import Path
import unittest

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect, text


MIGRATION_PATH = (
    Path(__file__).parents[1]
    / "migrations"
    / "versions"
    / "c8d4e6f1a207_add_authentication_fields.py"
)
SPEC = importlib.util.spec_from_file_location(
    "add_authentication_fields_migration",
    MIGRATION_PATH,
)
MIGRATION = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MIGRATION)


class AuthenticationMigrationTests(unittest.TestCase):
    def test_upgrade_adds_only_authentication_fields(self):
        engine = create_engine("sqlite://")
        with engine.begin() as connection:
            connection.exec_driver_sql(
                "CREATE TABLE users ("
                "user_id INTEGER PRIMARY KEY, "
                "display_name VARCHAR(120) NOT NULL, "
                "status VARCHAR(16) NOT NULL, "
                "patient_id INTEGER, "
                "created_at DATETIME NOT NULL, "
                "updated_at DATETIME NOT NULL)"
            )
            with Operations.context(MigrationContext.configure(connection)):
                MIGRATION.upgrade()

            columns = {
                column["name"]
                for column in inspect(connection).get_columns("users")
            }
            self.assertIn("email", columns)
            self.assertIn("password_hash", columns)
            self.assertEqual(
                connection.execute(
                    text(
                        "SELECT name FROM sqlite_master "
                        "WHERE type='index' AND name='ix_users_email'"
                    )
                ).scalar_one(),
                "ix_users_email",
            )
        engine.dispose()


if __name__ == "__main__":
    unittest.main()
