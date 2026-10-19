import importlib.util
from pathlib import Path
import unittest

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect, text


MIGRATIONS = Path(__file__).parents[1] / "migrations" / "versions"


def _load_migration(filename, module_name):
    spec = importlib.util.spec_from_file_location(
        module_name,
        MIGRATIONS / filename,
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


LEGACY_MIGRATION = _load_migration(
    "cf5a5f57fb40_initial_database_schema.py",
    "legacy_initial_schema_migration",
)
NULLABLE_METRICS_MIGRATION = _load_migration(
    "a1c7e9b503d6_allow_unknown_legacy_assessment_metrics.py",
    "allow_unknown_legacy_assessment_metrics",
)


class LegacyAssessmentMigrationTests(unittest.TestCase):
    def test_legacy_single_scores_are_preserved_without_fabricating_metrics(self):
        engine = create_engine("sqlite://")
        with engine.begin() as connection:
            connection.exec_driver_sql(
                "CREATE TABLE patients ("
                "patient_id INTEGER PRIMARY KEY, "
                "first_name VARCHAR(50) NOT NULL, "
                "last_name VARCHAR(50) NOT NULL, "
                "created_at DATETIME, updated_at DATETIME)"
            )
            connection.exec_driver_sql(
                "CREATE TABLE assessment_records ("
                "assessment_id INTEGER PRIMARY KEY, "
                "patient_id INTEGER NOT NULL, "
                "exercise VARCHAR(100) NOT NULL, "
                "score FLOAT, notes TEXT, created_at DATETIME)"
            )
            connection.execute(text(
                "INSERT INTO patients (patient_id, first_name, last_name) "
                "VALUES (1, 'Legacy', 'Patient')"
            ))
            connection.execute(text(
                "INSERT INTO assessment_records "
                "(assessment_id, patient_id, exercise, score, notes) "
                "VALUES (10, 1, 'Bicep Curl', 82.5, 'Preserve this note')"
            ))

            with Operations.context(MigrationContext.configure(connection)):
                LEGACY_MIGRATION.upgrade()

            columns = {
                column["name"]
                for column in inspect(connection).get_columns("assessment_records")
            }
            self.assertNotIn("score", columns)
            row = connection.execute(text(
                "SELECT repetitions, average_score, best_score, worst_score, notes "
                "FROM assessment_records WHERE assessment_id=10"
            )).mappings().one()
            self.assertIsNone(row["repetitions"])
            self.assertEqual(row["average_score"], 82.5)
            self.assertIsNone(row["best_score"])
            self.assertIsNone(row["worst_score"])
            self.assertEqual(row["notes"], "Preserve this note")

    def test_followup_migration_allows_unknown_metrics_in_existing_databases(self):
        engine = create_engine("sqlite://")
        with engine.begin() as connection:
            connection.exec_driver_sql(
                "CREATE TABLE assessment_records ("
                "assessment_id INTEGER PRIMARY KEY, "
                "patient_id INTEGER NOT NULL, "
                "exercise VARCHAR(100) NOT NULL, "
                "repetitions INTEGER NOT NULL, "
                "average_score FLOAT NOT NULL, "
                "best_score FLOAT NOT NULL, "
                "worst_score FLOAT NOT NULL, "
                "trend VARCHAR(50), feedback TEXT, notes TEXT, created_at DATETIME)"
            )
            connection.execute(text(
                "INSERT INTO assessment_records "
                "(assessment_id, patient_id, exercise, repetitions, average_score, "
                "best_score, worst_score) VALUES (1, 1, 'Bicep Curl', 3, 80, 90, 70)"
            ))

            with Operations.context(MigrationContext.configure(connection)):
                NULLABLE_METRICS_MIGRATION.upgrade()

            columns = {
                column["name"]: column
                for column in inspect(connection).get_columns("assessment_records")
            }
            for name in ("repetitions", "average_score", "best_score", "worst_score"):
                with self.subTest(column=name):
                    self.assertTrue(columns[name]["nullable"])
            row = connection.execute(text(
                "SELECT repetitions, average_score, best_score, worst_score "
                "FROM assessment_records WHERE assessment_id=1"
            )).one()
            self.assertEqual(tuple(row), (3, 80, 90, 70))

    def test_nullable_metrics_downgrade_refuses_to_invent_unknown_values(self):
        engine = create_engine("sqlite://")
        with engine.begin() as connection:
            connection.exec_driver_sql(
                "CREATE TABLE assessment_records ("
                "assessment_id INTEGER PRIMARY KEY, "
                "patient_id INTEGER NOT NULL, "
                "exercise VARCHAR(100) NOT NULL, "
                "repetitions INTEGER, average_score FLOAT, best_score FLOAT, "
                "worst_score FLOAT, trend VARCHAR(50), feedback TEXT, notes TEXT, "
                "created_at DATETIME)"
            )
            connection.execute(text(
                "INSERT INTO assessment_records "
                "(assessment_id, patient_id, exercise, repetitions) "
                "VALUES (1, 1, 'Legacy Curl', NULL)"
            ))
            with Operations.context(MigrationContext.configure(connection)):
                with self.assertRaisesRegex(RuntimeError, "unknown legacy values remain"):
                    NULLABLE_METRICS_MIGRATION.downgrade()


if __name__ == "__main__":
    unittest.main()
