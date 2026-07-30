"""
selection_screen.py

Main landing page for the rehabilitation assessment application.

Responsibilities
----------------
- Display available exercises
- Manage exercise selection
- Coordinate UI panels
- Launch assessment
"""

from core.exercise_registry import ExerciseRegistry

from ui.muscle_panel import MusclePanel
from ui.information_panel import InformationPanel


class SelectionScreen:

    def __init__(self):

        self.registry = ExerciseRegistry()

        self.profiles = self.registry.get_profiles()

        self.selected_profile = (
            self.profiles[0]
            if self.profiles
            else None
        )

        self.muscle_panel = MusclePanel()

        self.information_panel = InformationPanel()

    def select_profile(self, profile):

        self.selected_profile = profile

        self.muscle_panel.update(profile)

        self.information_panel.update(profile)

    def begin_assessment(self):

        return self.selected_profile

class MusclePanel:

    def __init__(self):

        self.highlighted_regions = []

    def update(self, profile):

        self.highlighted_regions = (
            profile.highlighted_regions
        )
class InformationPanel:

    def __init__(self):

        self.profile = None

    def update(self, profile):

        self.profile = profile