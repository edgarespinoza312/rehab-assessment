from pathlib import Path
import unittest


class ProgressionAdvisoryUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.template = Path("dashboard/templates/patient_profile.html").read_text()
        cls.script = Path("dashboard/static/js/patient_progress.js").read_text()

    def test_review_surface_has_observed_classification_and_limitations_sections(self):
        for value in (
            "Progression Advisory Review",
            "Software Classification",
            "Observed Evidence",
            "Limitations",
            'id="advisory-classification-value"',
            'id="advisory-evidence"',
            'id="advisory-limitations"',
        ):
            self.assertIn(value, self.template)

    def test_script_consumes_advisory_endpoint_without_decision_heuristics(self):
        self.assertIn(
            "/api/patients/${encodeURIComponent(config.patient_id)}/progression/advisory",
            self.script,
        )
        self.assertIn("payload.classification", self.script)
        self.assertIn("payload.evidence_records", self.script)
        self.assertIn("payload.limitations", self.script)
        self.assertIn("requestSequence !== advisoryRequestSequence", self.script)
        self.assertNotIn("POSSIBLE_PROGRESSION &&", self.script)
        self.assertNotIn("target_repetitions +", self.script)

    def test_script_renders_all_classification_categories_and_safe_states(self):
        for category in (
            "REVIEW_REQUIRED",
            "POSSIBLE_PROGRESSION",
            "POSSIBLE_REGRESSION",
            "INSUFFICIENT_DATA",
        ):
            self.assertIn(category, self.script)
        self.assertIn("Unable to load advisory review.", self.script)
        self.assertIn("No previous history is available for advisory review.", self.script)
        self.assertIn("Unspecified", self.script)
        self.assertIn("Not recorded", self.script)
        self.assertIn("Not available", self.script)

    def test_no_prescription_or_workout_mutation_language_in_review_script(self):
        for forbidden in (
            "recommended_resistance",
            "recommended_repetitions",
            "workout_mutations",
            "increase weight",
            "decrease weight",
            "prescribe",
        ):
            self.assertNotIn(forbidden, self.script.lower())


if __name__ == "__main__":
    unittest.main()
