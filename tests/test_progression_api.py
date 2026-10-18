from datetime import datetime
import unittest

from dashboard.app import app
from dashboard.database import db
from dashboard.models import (
    AssessmentRecord,
    CompletedWorkoutSession,
    ExerciseIdentity,
    Patient,
    WorkoutExerciseResult,
    Role,
    User,
)
from tests.support.auth import login_client, seed_clinician


class ProgressionApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = app
        cls.client = cls.app.test_client()

    def setUp(self):
        with self.app.app_context():
            db.session.rollback()
            db.drop_all()
            db.create_all()
            db.session.add_all([
                Patient(patient_id=1, first_name="A", last_name="Patient"),
                Patient(patient_id=2, first_name="B", last_name="Patient"),
                ExerciseIdentity(exercise_id="bicep_curl"),
            ])
            seed_clinician(self.app)
            db.session.commit()
        login_client(self.app, self.client)

    def tearDown(self):
        with self.app.app_context():
            db.session.rollback()
            db.drop_all()

    def _add_session(self, session_id, patient_id, started_at, status, results):
        with self.app.app_context():
            session = CompletedWorkoutSession(
                runtime_session_id=session_id,
                patient_id=patient_id,
                preset_id="api-test",
                workout_name="API Test",
                status=status,
                started_at=started_at,
                completed_at=started_at,
                exercise_results=[
                    WorkoutExerciseResult(
                        position=position,
                        exercise_id="bicep_curl",
                        display_name="Bicep Curl",
                        side=side,
                        target_repetitions=target,
                        completed_repetitions=completed,
                        status="complete",
                        resistance_value=resistance,
                        resistance_unit=unit,
                        resistance_type="dumbbell" if resistance is not None else None,
                        average_score=score,
                        started_at=started_at,
                        completed_at=started_at,
                    )
                    for position, (side, target, completed, resistance, unit, score)
                    in enumerate(results)
                ],
            )
            db.session.add(session)
            db.session.commit()

    def test_basic_retrieval_serializes_public_projection(self):
        self._add_session(
            "api-basic",
            1,
            datetime(2026, 1, 2, 10),
            "completed",
            [("right", 3, 3, 5, "lb", 87)],
        )
        response = self.client.get("/api/patients/1/progression")
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["patient_id"], 1)
        self.assertEqual(payload["count"], 1)
        result = payload["results"][0]
        self.assertEqual(result["occurred_at"], "2026-01-02T10:00:00")
        self.assertEqual(result["side"], "right")
        self.assertEqual(result["resistance_value"], 5.0)
        self.assertEqual(result["resistance_unit"], "lb")
        self.assertEqual(result["completion_percentage"], 100.0)
        self.assertNotIn("exercise_position", result)
        self.assertNotIn("source_id", result)

    def test_empty_and_patient_isolated_results(self):
        self.assertEqual(
            self.client.get("/api/patients/1/progression").get_json(),
            {"count": 0, "patient_id": 1, "results": []},
        )
        self._add_session(
            "api-other",
            2,
            datetime(2026, 1, 1),
            "completed",
            [("left", 2, 2, None, None, 80)],
        )
        self.assertEqual(
            self.client.get("/api/patients/1/progression").get_json()["count"],
            0,
        )

    def test_filters_order_cancelled_results_and_null_metrics(self):
        self._add_session(
            "api-later",
            1,
            datetime(2026, 1, 3),
            "cancelled",
            [("left", 4, 3, 7.5, "lb", 91)],
        )
        self._add_session(
            "api-earlier",
            1,
            datetime(2026, 1, 2),
            "completed",
            [("right", 3, 3, None, None, 82)],
        )
        response = self.client.get(
            "/api/patients/1/progression"
            "?exercise_id=bicep_curl&side=left&start=2026-01-01&end=2026-01-31"
        )
        self.assertEqual(response.status_code, 200)
        result = response.get_json()["results"][0]
        self.assertEqual(result["session_status"], "cancelled")
        self.assertEqual(result["completion_percentage"], 75.0)
        self.assertEqual(result["resistance_value"], 7.5)
        self.assertIsNone(result["rom_score"])
        all_results = self.client.get("/api/patients/1/progression").get_json()["results"]
        self.assertEqual([item["occurred_at"] for item in all_results], [
            "2026-01-02T00:00:00",
            "2026-01-03T00:00:00",
        ])

    def test_legacy_records_are_exposed_with_unknown_side(self):
        with self.app.app_context():
            db.session.add(AssessmentRecord(
                patient_id=1,
                exercise="Left Bicep Curl",
                repetitions=2,
                average_score=79,
                best_score=85,
                worst_score=70,
                created_at=datetime(2026, 1, 4),
            ))
            db.session.commit()
        result = self.client.get(
            "/api/patients/1/progression?exercise_id=bicep_curl"
        ).get_json()["results"][0]
        self.assertEqual(result["source_type"], "legacy_assessment")
        self.assertIsNone(result["side"])
        self.assertIsNone(result["resistance_value"])
        self.assertIsNone(result["completion_percentage"])

    def test_invalid_parameters_and_missing_patient(self):
        self.assertEqual(
            self.client.get("/api/patients/999/progression").status_code,
            404,
        )
        self.assertEqual(
            self.client.get("/api/patients/1/progression?side=middle").status_code,
            400,
        )
        self.assertEqual(
            self.client.get(
                "/api/patients/1/progression?exercise_id=unknown"
            ).status_code,
            400,
        )
        self.assertEqual(
            self.client.get(
                "/api/patients/1/progression?start=not-a-date"
            ).status_code,
            400,
        )
        self.assertEqual(
            self.client.get(
                "/api/patients/1/progression"
                "?start=2026-02-02&end=2026-02-01"
            ).status_code,
            400,
        )

    def test_timezone_aware_filters_are_normalized_to_utc(self):
        self._add_session(
            "api-timezone-filter",
            1,
            datetime(2026, 1, 2, 10),
            "completed",
            [("right", 3, 3, 5, "lb", 87)],
        )

        aware_range = self.client.get(
            "/api/patients/1/progression"
            "?start=2026-01-02T09:00:00-01:00&end=2026-01-02T11:00:00Z"
        )
        self.assertEqual(aware_range.status_code, 200)
        self.assertEqual(aware_range.get_json()["count"], 1)

        mixed_range = self.client.get(
            "/api/patients/1/progression"
            "?start=2026-01-02T09:00:00-01:00&end=2026-01-02"
        )
        self.assertEqual(mixed_range.status_code, 200)
        self.assertEqual(mixed_range.get_json()["count"], 1)

    def test_date_only_end_includes_the_entire_calendar_day(self):
        self._add_session(
            "api-date-only-end",
            1,
            datetime(2026, 1, 2, 10),
            "completed",
            [("right", 3, 3, 5, "lb", 87)],
        )
        response = self.client.get(
            "/api/patients/1/progression"
            "?start=2026-01-02&end=2026-01-02"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["count"], 1)


if __name__ == "__main__":
    unittest.main()
