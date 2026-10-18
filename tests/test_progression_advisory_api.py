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
)
from tests.support.auth import login_client, seed_clinician


class ProgressionAdvisoryApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = app
        cls.client = app.test_client()

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

    def _add_session(self, session_id, patient_id, started_at, side, completed, score):
        with self.app.app_context():
            db.session.add(CompletedWorkoutSession(
                runtime_session_id=session_id,
                patient_id=patient_id,
                preset_id="advisory-api-test",
                workout_name="Advisory API Test",
                status="completed",
                started_at=started_at,
                completed_at=started_at,
                exercise_results=[WorkoutExerciseResult(
                    position=0,
                    exercise_id="bicep_curl",
                    display_name="Bicep Curl",
                    side=side,
                    target_repetitions=3,
                    completed_repetitions=completed,
                    status="complete",
                    resistance_value=5,
                    resistance_unit="lb",
                    resistance_type="dumbbell",
                    average_score=score,
                    started_at=started_at,
                    completed_at=started_at,
                )],
            ))
            db.session.commit()

    def test_valid_request_serializes_classification_evidence_and_provenance(self):
        self._add_session("advisory-1", 1, datetime(2026, 1, 1), "right", 2, 70)
        self._add_session("advisory-2", 1, datetime(2026, 1, 2), "right", 3, 80)
        response = self.client.get(
            "/api/patients/1/progression/advisory"
            "?exercise_id=bicep_curl&side=right"
        )
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["classification"], "POSSIBLE_PROGRESSION")
        self.assertEqual(payload["side"], "right")
        self.assertEqual(payload["evidence_summary"]["observation_count"], 2)
        self.assertEqual(len(payload["evidence_records"]), 2)
        self.assertEqual(payload["evidence_records"][0]["source_type"], "workout")
        self.assertEqual(payload["evidence_records"][0]["source_id"], 1)
        self.assertIn("not been clinically validated", payload["limitations"][0])

    def test_unknown_patient_invalid_side_and_invalid_exercise(self):
        self.assertEqual(
            self.client.get("/api/patients/999/progression/advisory").status_code,
            404,
        )
        self.assertEqual(
            self.client.get("/api/patients/1/progression/advisory?side=middle").status_code,
            400,
        )
        self.assertEqual(
            self.client.get(
                "/api/patients/1/progression/advisory?exercise_id=unknown"
            ).status_code,
            400,
        )

    def test_repeated_request_patient_and_side_isolation(self):
        self._add_session("advisory-left", 1, datetime(2026, 1, 1), "left", 3, 80)
        self._add_session("advisory-other", 2, datetime(2026, 1, 1), "left", 1, 50)
        url = "/api/patients/1/progression/advisory?exercise_id=bicep_curl&side=left"
        first = self.client.get(url)
        second = self.client.get(url)
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.get_json(), second.get_json())
        payload = first.get_json()
        self.assertEqual(payload["patient_id"], 1)
        self.assertEqual(payload["evidence_summary"]["side"], "left")
        self.assertEqual(
            {record["patient_id"] for record in payload["evidence_records"]},
            {1},
        )

    def test_legacy_side_unspecified_is_preserved(self):
        with self.app.app_context():
            db.session.add(AssessmentRecord(
                patient_id=1,
                exercise="Left Bicep Curl",
                repetitions=3,
                average_score=78,
                best_score=80,
                worst_score=75,
                created_at=datetime(2026, 1, 1),
            ))
            db.session.commit()
        payload = self.client.get(
            "/api/patients/1/progression/advisory?exercise_id=bicep_curl"
        ).get_json()
        self.assertEqual(payload["classification"], "INSUFFICIENT_DATA")
        self.assertIsNone(payload["side"])
        self.assertIsNone(payload["evidence_records"][0]["side"])


if __name__ == "__main__":
    unittest.main()
