from datetime import datetime
from pathlib import Path
import unittest

from dashboard.app import app
from dashboard.database import db
from dashboard.models import AssessmentRecord, Patient
from tests.support.auth import login_client, seed_clinician


class PatientProgressionUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = app
        cls.client = app.test_client()
        cls.template = Path("dashboard/templates/patient_profile.html").read_text()
        cls.script = Path("dashboard/static/js/patient_progress.js").read_text()

    def setUp(self):
        with self.app.app_context():
            db.session.rollback()
            db.drop_all()
            db.create_all()
            db.session.add(Patient(
                patient_id=1,
                first_name="UI",
                last_name="Patient",
                diagnosis="Test",
                sex="Other",
                affected_side="left",
            ))
            db.session.add(AssessmentRecord(
                patient_id=1,
                exercise="Bicep Curl",
                repetitions=3,
                average_score=87,
                best_score=90,
                worst_score=84,
                created_at=datetime(2026, 1, 2),
            ))
            seed_clinician(self.app)
            db.session.commit()
        login_client(self.app, self.client)

    def tearDown(self):
        with self.app.app_context():
            db.session.rollback()
            db.drop_all()

    def test_profile_mounts_api_backed_progression_controls(self):
        response = self.client.get("/patients/1")
        self.assertEqual(response.status_code, 200)
        body = response.get_data(as_text=True)
        self.assertIn('id="patient-progress-config"', body)
        self.assertIn('"patient_id": 1', body)
        self.assertIn('id="progress-exercise"', body)
        self.assertIn('id="progress-side"', body)
        self.assertIn('id="progress-metric"', body)
        self.assertIn("patient_progress.js", body)
        self.assertNotIn("patient-progress-data", body)

    def test_script_uses_stable_filters_and_supported_metrics(self):
        self.assertIn("/api/patients/${encodeURIComponent(config.patient_id)}/progression", self.script)
        self.assertIn('params.set("exercise_id", exerciseSelector.value)', self.script)
        self.assertIn('params.set("side", sideSelector.value)', self.script)
        self.assertIn("overall_score", self.script)
        self.assertIn("completed_repetitions", self.script)
        self.assertIn("resistance_value", self.script)
        self.assertIn("result.source_type", self.script)

    def test_script_preserves_nulls_and_rejects_mixed_resistance_units(self):
        self.assertIn(
            'result[metric] !== null && result[metric] !== undefined',
            self.script,
        )
        self.assertIn("Resistance cannot be plotted together", self.script)
        self.assertIn("No data is available for this metric.", self.script)
        self.assertIn("No results are available for this side.", self.script)
        self.assertIn(
            "No progression data is available for this patient yet.",
            self.script,
        )


if __name__ == "__main__":
    unittest.main()
