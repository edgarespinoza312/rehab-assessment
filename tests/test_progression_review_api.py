from datetime import datetime
import unittest

from dashboard.app import app
from dashboard.database import db
from dashboard.models import (
    CompletedWorkoutSession,
    ExerciseIdentity,
    Patient,
    WorkoutExerciseResult,
)
from tests.support.auth import login_client, seed_clinician


class ProgressionReviewApiTests(unittest.TestCase):
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

    def _post(self, url, **kwargs):
        with self.client.session_transaction() as session:
            kwargs.setdefault("headers", {})["X-CSRF-Token"] = session[
                "revaliv_csrf_token"
            ]
        return self.client.post(url, **kwargs)

    def _add(self, patient_id=1, side="right", day=1):
        with self.app.app_context():
            when = datetime(2026, 1, day)
            db.session.add(CompletedWorkoutSession(
                runtime_session_id=f"review-api-{patient_id}-{side}-{day}",
                patient_id=patient_id,
                preset_id="review-api",
                workout_name="Review API",
                status="completed",
                started_at=when,
                completed_at=when,
                exercise_results=[WorkoutExerciseResult(
                    position=0,
                    exercise_id="bicep_curl",
                    display_name="Bicep Curl",
                    side=side,
                    target_repetitions=3,
                    completed_repetitions=3,
                    status="complete",
                    average_score=80 + day,
                    started_at=when,
                    completed_at=when,
                )],
            ))
            db.session.commit()

    def test_get_and_post_reviews_are_append_only(self):
        self._add(day=1)
        self._add(day=2)
        url = (
            "/api/patients/1/progression/advisory/reviews"
            "?exercise_id=bicep_curl&side=right"
        )
        self.assertEqual(self.client.get(url).get_json()["current_disposition"], "UNREVIEWED")
        first = self._post(url, json={
            "disposition": "REVIEWED",
            "reviewer_reference": "reviewer_demo_01",
            "note": "First <review>",
        })
        self.assertEqual(first.status_code, 201)
        second = self._post(url, json={
            "disposition": "DISMISSED",
            "reviewer_reference": "reviewer_demo_02",
            "note": "Second review",
        })
        self.assertEqual(second.status_code, 201)
        payload = self.client.get(url).get_json()
        self.assertEqual(payload["current_disposition"], "DISMISSED")
        self.assertEqual(len(payload["reviews"]), 2)
        self.assertEqual(payload["reviews"][0]["disposition"], "REVIEWED")
        self.assertEqual(payload["reviews"][0]["note"], "First <review>")

    def test_invalid_requests_and_no_orphan_review(self):
        base = "/api/patients/1/progression/advisory/reviews"
        self.assertEqual(self.client.get(base).status_code, 400)
        self.assertEqual(
            self.client.get(base + "?exercise_id=unknown").status_code,
            400,
        )
        self.assertEqual(
            self.client.get(base + "?exercise_id=bicep_curl&side=middle").status_code,
            400,
        )
        self._add(day=1)
        url = base + "?exercise_id=bicep_curl&side=right"
        self.assertEqual(
            self._post(url, json={
                "disposition": "INVALID",
                "reviewer_reference": "reviewer",
            }).status_code,
            400,
        )
        authenticated_review = self._post(url, json={
            "disposition": "REVIEWED",
            "reviewer_reference": "",
        })
        self.assertEqual(authenticated_review.status_code, 201)
        self.assertEqual(
            authenticated_review.get_json()["review"]["reviewer_reference"],
            "user:1",
        )
        self.assertEqual(
            self._post(url, json={
                "disposition": "REVIEWED",
                "reviewer_reference": "reviewer",
                "note": "x" * 2001,
            }).status_code,
            400,
        )
        no_history = base + "?exercise_id=bicep_curl&side=left"
        self.assertEqual(
            self._post(no_history, json={
                "disposition": "REVIEWED",
                "reviewer_reference": "reviewer",
            }).status_code,
            400,
        )

    def test_unknown_patient_and_patient_isolation(self):
        self.assertEqual(
            self.client.get(
                "/api/patients/999/progression/advisory/reviews"
                "?exercise_id=bicep_curl"
            ).status_code,
            404,
        )
        self._add(patient_id=2, day=1)
        url = (
            "/api/patients/1/progression/advisory/reviews"
            "?exercise_id=bicep_curl&side=right"
        )
        self.assertEqual(self.client.get(url).get_json()["reviews"], [])


if __name__ == "__main__":
    unittest.main()
