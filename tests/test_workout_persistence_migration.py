import importlib.util
from pathlib import Path
import unittest

from sqlalchemy import create_engine, insert, inspect, text
from alembic.migration import MigrationContext
from alembic.operations import Operations

from dashboard.models import AssessmentRecord, Patient


MIGRATION_PATH = (
    Path(__file__).parents[1]
    / "migrations"
    / "versions"
    / "7d2c4e8a1f30_add_workout_persistence.py"
)
SPEC = importlib.util.spec_from_file_location(
    "add_workout_persistence_migration", MIGRATION_PATH
)
MIGRATION = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MIGRATION)


class WorkoutPersistenceMigrationTests(unittest.TestCase):
    def test_upgrade_and_downgrade_preserve_existing_patient_history(self):
        engine = create_engine("sqlite://")
        with engine.begin() as connection:
            connection.exec_driver_sql("PRAGMA foreign_keys=ON")
            Patient.__table__.create(connection)
            AssessmentRecord.__table__.create(connection)
            connection.execute(
                insert(Patient.__table__).values(
                    patient_id=42,
                    first_name="Taylor",
                    last_name="Existing",
                )
            )
            connection.execute(
                insert(AssessmentRecord.__table__).values(
                    assessment_id=7,
                    patient_id=42,
                    exercise="Left Bicep Curl",
                    repetitions=4,
                    average_score=82,
                    best_score=91,
                    worst_score=70,
                )
            )
            connection.exec_driver_sql(
                "CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)"
            )
            connection.exec_driver_sql(
                "INSERT INTO alembic_version VALUES ('f8af68afa46e')"
            )

            with Operations.context(MigrationContext.configure(connection)):
                MIGRATION.upgrade()

            inspector = inspect(connection)
            for table in (
                "exercise_identities",
                "workout_plans",
                "workout_plan_exercises",
                "workout_sessions",
                "workout_exercise_results",
            ):
                self.assertIn(table, inspector.get_table_names())
            self.assertEqual(
                connection.execute(
                    text("SELECT exercise_id FROM exercise_identities")
                ).scalar_one(),
                "bicep_curl",
            )
            self.assertEqual(
                connection.execute(
                    text("SELECT first_name FROM patients WHERE patient_id=42")
                ).scalar_one(),
                "Taylor",
            )
            self.assertEqual(
                connection.execute(
                    text(
                        "SELECT exercise, average_score FROM assessment_records "
                        "WHERE assessment_id=7"
                    )
                ).one(),
                ("Left Bicep Curl", 82.0),
            )

            with Operations.context(MigrationContext.configure(connection)):
                MIGRATION.downgrade()

            remaining = set(inspect(connection).get_table_names())
            self.assertNotIn("workout_plans", remaining)
            self.assertNotIn("workout_sessions", remaining)
            self.assertEqual(
                connection.execute(
                    text("SELECT COUNT(*) FROM assessment_records")
                ).scalar_one(),
                1,
            )
            self.assertEqual(
                connection.execute(
                    text("SELECT COUNT(*) FROM patients")
                ).scalar_one(),
                1,
            )
        engine.dispose()


if __name__ == "__main__":
    unittest.main()
