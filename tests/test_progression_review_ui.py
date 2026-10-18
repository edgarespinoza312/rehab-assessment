from pathlib import Path
import unittest


class ProgressionReviewUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.template = Path("dashboard/templates/patient_profile.html").read_text()
        cls.script = Path("dashboard/static/js/patient_progress.js").read_text()

    def test_review_layer_is_separate_from_advisory_evidence(self):
        for value in (
            "Software Classification",
            "Observed Evidence",
            "Limitations",
            "Human Review",
            "Review History",
            'id="review-current-status"',
            'id="reviewer-reference"',
            'id="review-note"',
            'id="advisory-review-form"',
        ):
            self.assertIn(value, self.template)

    def test_script_uses_review_api_and_renders_history_safely(self):
        self.assertIn(
            "/progression/advisory/reviews",
            self.script,
        )
        self.assertIn("payload.reviews", self.script)
        self.assertIn("payload.current_disposition", self.script)
        self.assertIn("textContent = value", self.script)
        self.assertIn("Review recorded.", self.script)
        self.assertIn("No review events recorded.", self.script)

    def test_review_ui_has_no_clinical_or_prescription_language(self):
        lower = self.script.lower() + self.template.lower()
        for forbidden in (
            "approved_for_progression",
            "approved_for_regression",
            "safe to progress",
            "recommended_resistance",
            "recommended_repetitions",
            "prescribe",
        ):
            self.assertNotIn(forbidden, lower)


if __name__ == "__main__":
    unittest.main()
