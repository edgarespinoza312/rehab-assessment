from pathlib import Path
import unittest


class ProgressionContextUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.template = Path(
            "dashboard/templates/workout_builder.html"
        ).read_text()
        cls.script = Path(
            "dashboard/static/js/workout_builder.js"
        ).read_text()
        cls.styles = Path("dashboard/static/css/pages.css").read_text()

    def test_builder_mounts_contained_history_section(self):
        self.assertIn("builder-history-help", self.template)
        self.assertIn("Recent history is descriptive only", self.template)
        self.assertIn("workout-plan-patient", self.template)
        self.assertIn("workout_builder.js", self.template)
        self.assertIn("builder-history", self.script)
        self.assertIn("Recent History", self.script)
        self.assertIn("builder-history-table", self.script)

    def test_script_consumes_context_api_with_stable_filters(self):
        self.assertIn(
            "/progression/context?${params}",
            self.script,
        )
        self.assertIn('exercise_id: exerciseId', self.script)
        self.assertIn('params.set("side", sideSelector.value)', self.script)
        self.assertIn('recent_limit: "5"', self.script)
        self.assertNotIn("fetch(\"/api/patients/1", self.script)
        self.assertNotIn("recommend", self.script.lower())
        self.assertNotIn("increase weight", self.script.lower())

    def test_script_handles_loading_empty_error_and_race_states(self):
        self.assertIn("Loading progression history...", self.script)
        self.assertIn("No previous history for this exercise.", self.script)
        self.assertIn("Unable to load progression history.", self.script)
        self.assertIn("historyRequestSequence", self.script)
        self.assertIn("if (requestId !== historyRequestSequence) return;", self.script)
        self.assertIn("Select a patient to load history.", self.script)
        self.assertIn("Resistance:", self.script)
        self.assertIn("recent_observation_dates", self.script)
        self.assertIn("escapeHtml", self.script)

    def test_history_styles_are_contained_and_accessible(self):
        self.assertIn(".builder-history", self.styles)
        self.assertIn(".builder-history-table th", self.styles)
        self.assertIn("caption class=\"sr-only\"", self.script)
