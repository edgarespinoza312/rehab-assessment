import os
import sys
import unittest
from unittest.mock import patch

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.models import (
    Joint, JointType, Skeleton, ExerciseState, ExercisePhase, MovementMetrics,
)
from core.perception.base import PerceptionResult, PoseStatus, ReadinessState
from core.perception.presentation import readiness_presentation
from ui.overlay import OverlayRenderer, PoseDisplayContinuity


class ReadinessPresentationTests(unittest.TestCase):
    def _result(self, state, *, diagnostics=None, quality=None, valid=False):
        skeleton = Skeleton() if valid else None
        return PerceptionResult(
            skeleton=skeleton,
            status=PoseStatus.VALID if valid else PoseStatus.INVALID,
            backend="test",
            timestamp=1.0,
            frame_number=4,
            state=state,
            tracking=valid,
            diagnostics=diagnostics or {},
            quality=quality or {},
        )

    def test_each_readiness_state_has_specific_user_facing_label(self):
        expected = {
            ReadinessState.NO_PERSON: "No person detected",
            ReadinessState.LOW_CONFIDENCE: "Pose confidence is low",
            ReadinessState.POOR_QUALITY: "Pose needs adjustment",
            ReadinessState.CALIBRATION_REQUIRED: "Calibration in progress",
            ReadinessState.IDENTITY_AMBIGUOUS: "Checking arm identity",
            ReadinessState.READY: "Ready",
        }
        for state, label in expected.items():
            with self.subTest(state=state):
                result = self._result(state, valid=state is ReadinessState.READY)
                presentation = readiness_presentation(
                    result, calibration={"stage": "baseline"},
                    active_side="left", assessment_active=True,
                )
                self.assertEqual(presentation["state"], state.value)
                self.assertEqual(presentation["label"], label)
                self.assertTrue(presentation["message"])

    def test_readiness_state_transitions_change_guidance_and_validity(self):
        no_person = readiness_presentation(
            self._result(ReadinessState.NO_PERSON), assessment_active=True
        )
        ready = readiness_presentation(
            self._result(ReadinessState.READY, valid=True),
            active_side="left", assessment_active=True,
        )
        self.assertNotEqual(no_person["message"], ready["message"])
        self.assertFalse(no_person["tracking"])
        self.assertTrue(ready["tracking"])
        self.assertTrue(ready["valid"])

    def test_low_confidence_guidance_names_measured_weak_landmark(self):
        result = self._result(
            ReadinessState.LOW_CONFIDENCE,
            diagnostics={"raw_semantic_landmarks": {
                "left_elbow": {"confidence": 0.42},
                "left_shoulder": {"confidence": 0.9},
            }},
        )
        presentation = readiness_presentation(
            result, active_side="left", assessment_active=True
        )
        self.assertIn("left elbow", presentation["message"])
        self.assertNotIn("wrist", presentation["message"])

    def test_calibration_progress_success_and_failure_messages(self):
        expected = (
            ("baseline", "Hold still"),
            ("movement", "Bend only your left arm"),
            ("confirming", "4/10"),
            ("return", "Return your left arm"),
            ("ready", "complete"),
        )
        for stage, phrase in expected:
            with self.subTest(stage=stage):
                presentation = readiness_presentation(
                    None,
                    calibration={"stage": stage, "matching_frames": 4,
                                 "required_frames": 10},
                    active_side="left", assessment_active=True,
                )
                self.assertIn(phrase.lower(), presentation["message"].lower())
        mismatch = readiness_presentation(
            self._result(ReadinessState.IDENTITY_AMBIGUOUS,
                         diagnostics={"reason": "calibration_side_mismatch"}),
            active_side="left", assessment_active=True,
        )
        self.assertIn("Restart the assessment", mismatch["message"])

    def test_missing_landmark_guidance_is_general_and_never_claims_detection(self):
        result = self._result(
            ReadinessState.POOR_QUALITY,
            quality={"reasons": ["missing_identity_joints:left_wrist"]},
        )
        presentation = readiness_presentation(
            result, active_side="left", assessment_active=True
        )
        self.assertIn("active arm", presentation["message"])
        self.assertFalse(presentation["valid"])

    def test_stale_ready_result_is_not_shown_as_ready_during_new_calibration(self):
        result = self._result(ReadinessState.READY, valid=True)
        presentation = readiness_presentation(
            result, calibration={"stage": "baseline", "calibrated": False},
            active_side="left", assessment_active=True,
        )
        self.assertEqual(presentation["state"], "calibration_required")
        self.assertFalse(presentation["valid"])
        self.assertFalse(presentation["tracking"])

    def test_inactive_assessment_does_not_report_pose_as_ready(self):
        result = self._result(ReadinessState.READY, valid=True)
        presentation = readiness_presentation(
            result, assessment_active=False
        )
        self.assertEqual(presentation["state"], "calibration_required")
        self.assertFalse(presentation["valid"])
        self.assertFalse(presentation["tracking"])


class PoseDisplayContinuityTests(unittest.TestCase):
    def setUp(self):
        self.pose = Skeleton(timestamp=1.0, frame_number=1)
        self.pose.add_joint(Joint(JointType.LEFT_SHOULDER, 0.2, 0.2, visibility=0.9))
        self.pose.add_joint(Joint(JointType.LEFT_ELBOW, 0.3, 0.4, visibility=0.9))
        self.continuity = PoseDisplayContinuity(max_age_seconds=0.2)
        self.continuity.remember(self.pose, "left", 10.0)

    def test_brief_loss_returns_deep_copied_display_pose_then_expires(self):
        shown, stale = self.continuity.for_display(10.1, "left", allowed=True)
        self.assertTrue(stale)
        self.assertIsNot(shown, self.pose)
        shown.clear()
        self.assertTrue(self.continuity.for_display(10.15, "left", True)[1])
        self.assertEqual(self.continuity.for_display(10.21, "left", True), (None, False))

    def test_calibration_ambiguity_and_side_change_clear_stale_pose(self):
        for allowed, side in ((False, "left"), (True, "right")):
            with self.subTest(allowed=allowed, side=side):
                self.continuity.remember(self.pose, "left", 10.0)
                self.assertEqual(
                    self.continuity.for_display(10.05, side, allowed),
                    (None, False),
                )

    def test_active_side_is_highlighted_on_current_valid_pose(self):
        frame = __import__("numpy").zeros((480, 640, 3), dtype="uint8")
        with patch("ui.overlay.cv2.line") as draw_line:
            OverlayRenderer().draw(
                frame, self.pose, None, ExerciseState(), active_side="left",
                readiness={"label": "Ready", "message": "Ready for left arm.",
                           "state": "ready", "valid": True},
            )
        self.assertEqual(draw_line.call_count, 3)
        self.assertEqual(draw_line.call_args_list[0].args[3], OverlayRenderer.COLORS["active_glow"])
        self.assertEqual(draw_line.call_args_list[1].args[3], OverlayRenderer.COLORS["active"])
        self.assertEqual(draw_line.call_args_list[1].args[4], 4)
        self.assertEqual(draw_line.call_args_list[2].args[3], OverlayRenderer.COLORS["active_core"])

    def test_overlay_draws_only_present_skeleton_joints_and_status(self):
        frame = __import__("numpy").zeros((480, 640, 3), dtype="uint8")
        renderer = OverlayRenderer()
        with patch("ui.overlay.cv2.line") as draw_line, patch(
            "ui.overlay.cv2.putText"
        ) as draw_text:
            renderer.draw(
                frame, self.pose, None, ExerciseState(), active_side="left",
                readiness={"label": "Pose needs adjustment", "message": "Keep arm in view.",
                           "state": "poor_quality", "valid": False},
                display_only_stale=True,
            )
        # Only the existing shoulder-elbow edge is drawn as dashed display segments.
        self.assertGreater(draw_line.call_count, 0)
        self.assertTrue(all(call.args[3] == OverlayRenderer.COLORS["held"] for call in draw_line.call_args_list))
        self.assertTrue(any("display only" in str(call).lower() for call in draw_text.call_args_list))

    def _full_arm_pose(self):
        pose = Skeleton(timestamp=2.0, frame_number=2)
        for joint_type, x, y in (
            (JointType.LEFT_SHOULDER, 0.30, 0.25),
            (JointType.LEFT_ELBOW, 0.40, 0.43),
            (JointType.LEFT_WRIST, 0.48, 0.62),
            (JointType.RIGHT_SHOULDER, 0.70, 0.25),
            (JointType.RIGHT_ELBOW, 0.62, 0.42),
            (JointType.RIGHT_WRIST, 0.55, 0.60),
        ):
            pose.add_joint(Joint(joint_type, x, y, visibility=0.9))
        return pose

    def _draw(self, pose, *, state="ready", side="left", metrics=None, exercise=None):
        import numpy as np
        frame = np.zeros((480, 640, 3), dtype="uint8")
        readiness = {
            "label": state.replace("_", " ").upper(),
            "message": "Test guidance",
            "state": state,
            "active_side": side,
            "valid": state == "ready",
            "calibration_progress": None,
        }
        return OverlayRenderer().draw(
            frame, pose, metrics, exercise, active_side=side,
            readiness=readiness,
        )

    def test_active_and_inactive_side_hierarchy_uses_clinical_palette(self):
        pose = self._full_arm_pose()
        with patch("ui.overlay.cv2.line") as lines:
            self._draw(pose, exercise=ExerciseState(exercise_name="LEFT_BICEP_CURL"))
        colors = [call.args[3] for call in lines.call_args_list]
        self.assertIn(OverlayRenderer.COLORS["active"], colors)
        self.assertIn(OverlayRenderer.COLORS["active_glow"], colors)
        self.assertIn(OverlayRenderer.COLORS["anatomy"], colors)

    def test_right_active_side_mirrors_the_left_side_hierarchy(self):
        pose = self._full_arm_pose()
        with patch("ui.overlay.cv2.line") as lines:
            self._draw(
                pose, side="right",
                exercise=ExerciseState(exercise_name="RIGHT_BICEP_CURL"),
            )
        active_calls = [
            call for call in lines.call_args_list
            if call.args[3] in {
                OverlayRenderer.COLORS["active_glow"],
                OverlayRenderer.COLORS["active"],
                OverlayRenderer.COLORS["active_core"],
            }
        ]
        self.assertEqual(len(active_calls), 6)
        right_shoulder = (round(0.70 * 639), round(0.25 * 479))
        right_elbow = (round(0.62 * 639), round(0.42 * 479))
        self.assertTrue(any(
            call.args[1] == right_shoulder and call.args[2] == right_elbow
            for call in active_calls
        ))

    def test_identity_ambiguity_removes_side_specific_emphasis(self):
        with patch("ui.overlay.cv2.line") as lines:
            self._draw(
                self._full_arm_pose(), state="identity_ambiguous",
                exercise=ExerciseState(exercise_name="LEFT_BICEP_CURL"),
            )
        colors = [call.args[3] for call in lines.call_args_list]
        self.assertNotIn(OverlayRenderer.COLORS["active"], colors)
        self.assertNotIn(OverlayRenderer.COLORS["active_glow"], colors)

    def test_calibration_draws_relevant_segments_in_amber(self):
        import numpy as np
        frame = np.zeros((480, 640, 3), dtype="uint8")
        pose = self._full_arm_pose()
        with patch("ui.overlay.cv2.line") as lines:
            OverlayRenderer().draw(
                frame, pose, None, ExerciseState(exercise_name="LEFT_BICEP_CURL"),
                active_side="left",
                readiness={"state": "calibration_required", "valid": False,
                           "active_side": "left", "message": "Hold still.",
                           "calibration_progress": {"stage": "baseline"}},
            )
        self.assertIn(OverlayRenderer.COLORS["calibration"],
                      [call.args[3] for call in lines.call_args_list])

    def test_warning_palette_separates_neutral_gray_calibration_gold_and_quality_orange(self):
        colors = OverlayRenderer.COLORS
        neutral = colors["anatomy"]
        calibration = colors["calibration"]
        quality = colors["quality"]
        self.assertEqual(len(set((neutral, calibration, quality))), 3)
        # OpenCV colors are BGR. Both warnings are warm and more luminous than anatomy.
        def luminance(bgr):
            blue, green, red = bgr
            return 0.114 * blue + 0.587 * green + 0.299 * red
        self.assertGreater(calibration[2], calibration[1])
        self.assertGreater(quality[2], quality[1])
        self.assertGreater(luminance(calibration), luminance(neutral))
        self.assertGreater(luminance(quality), luminance(neutral))
        self.assertGreater(calibration[1], quality[1])  # gold is more yellow than orange
        self.assertEqual(colors["active"], (255, 188, 42))
        self.assertEqual(colors["green_accent"], (90, 208, 150))

    def test_readiness_state_colors_cover_ready_calibration_quality_identity_and_absence(self):
        import numpy as np
        for state, expected in (
            ("ready", OverlayRenderer.COLORS["green_accent"]),
            ("calibration_required", OverlayRenderer.COLORS["calibration"]),
            ("low_confidence", OverlayRenderer.COLORS["quality"]),
            ("poor_quality", OverlayRenderer.COLORS["quality"]),
            ("identity_ambiguous", OverlayRenderer.COLORS["ambiguous"]),
            ("no_person", OverlayRenderer.COLORS["secondary"]),
        ):
            with self.subTest(state=state):
                frame = np.zeros((480, 640, 3), dtype="uint8")
                with patch("ui.overlay.cv2.putText") as texts:
                    OverlayRenderer().draw(
                        frame, None, None, None, tracking=state == "ready",
                        readiness={"state": state, "label": state,
                                    "message": "State guidance", "valid": state == "ready"},
                    )
                self.assertTrue(any(call.args[5] == expected for call in texts.call_args_list))

    def test_no_person_suppresses_any_supplied_skeleton(self):
        import numpy as np
        frame = np.zeros((480, 640, 3), dtype="uint8")
        with patch("ui.overlay.cv2.circle") as circles, patch("ui.overlay.cv2.line") as lines:
            OverlayRenderer().draw(
                frame, self._full_arm_pose(), None, None, active_side="left",
                readiness={"state": "no_person", "valid": False,
                           "label": "No person", "message": "Stand in view."},
            )
        circles.assert_not_called()
        lines.assert_not_called()

    def test_missing_wrist_never_creates_a_connection(self):
        import numpy as np
        frame = np.zeros((480, 640, 3), dtype="uint8")
        with patch("ui.overlay.cv2.line") as lines:
            OverlayRenderer().draw(
                frame, self.pose, None, None, active_side="left",
                readiness={"state": "ready", "valid": True, "active_side": "left"},
            )
        self.assertEqual(lines.call_count, 3)
        self.assertTrue(all(call.args[3] in {
            OverlayRenderer.COLORS["active_glow"],
            OverlayRenderer.COLORS["active"],
            OverlayRenderer.COLORS["active_core"],
        } for call in lines.call_args_list))

    def test_angle_callout_and_arc_require_current_authoritative_measurement(self):
        import numpy as np
        pose = self._full_arm_pose()
        metrics = MovementMetrics(elbow_angle_left=137.4, elbow_angle_right=101.0)
        frame = np.zeros((480, 640, 3), dtype="uint8")
        with patch("ui.overlay.cv2.putText") as texts, patch("ui.overlay.cv2.ellipse") as arc:
            OverlayRenderer().draw(
                frame, pose, metrics, ExerciseState(exercise_name="LEFT_BICEP_CURL"),
                active_side="left", readiness={"state": "ready", "valid": True,
                                                "active_side": "left"},
            )
        self.assertTrue(any(call.args[1] == "137°" for call in texts.call_args_list))
        self.assertEqual(arc.call_count, 1)

        frame = np.zeros((480, 640, 3), dtype="uint8")
        with patch("ui.overlay.cv2.putText") as texts, patch("ui.overlay.cv2.ellipse") as arc:
            OverlayRenderer().draw(
                frame, pose, metrics, ExerciseState(exercise_name="LEFT_BICEP_CURL"),
                active_side="left", readiness={"state": "low_confidence",
                                                "valid": False, "active_side": "left"},
                display_only_stale=True,
            )
        self.assertFalse(any(call.args[1] == "137°" for call in texts.call_args_list))
        arc.assert_not_called()

    def test_hud_uses_existing_phase_rep_count_and_observed_rom_only(self):
        import numpy as np
        frame = np.zeros((480, 640, 3), dtype="uint8")
        metrics = MovementMetrics(elbow_angle_left=132, range_of_motion=38.5)
        state = ExerciseState(
            exercise_name="LEFT_BICEP_CURL", repetitions=3, phase=ExercisePhase.LIFTING
        )
        with patch("ui.overlay.cv2.putText") as texts:
            OverlayRenderer().draw(
                frame, self._full_arm_pose(), metrics, state, active_side="left",
                readiness={"state": "ready", "valid": True, "active_side": "left"},
            )
        labels = [call.args[1] for call in texts.call_args_list]
        self.assertIn("LEFT ARM CURL", labels)
        self.assertIn("3", labels)
        self.assertIn("RAISING  ↑", labels)
        self.assertIn("OBSERVED ROM  38°", labels)
        self.assertFalse(any("TARGET" in label or "OPTIMAL" in label for label in labels))

        state.phase = ExercisePhase.LOWERING
        with patch("ui.overlay.cv2.putText") as texts:
            OverlayRenderer().draw(
                np.zeros((480, 640, 3), dtype="uint8"), self._full_arm_pose(),
                metrics, state, active_side="left",
                readiness={"state": "ready", "valid": True, "active_side": "left"},
            )
        self.assertIn("LOWERING  ↓", [call.args[1] for call in texts.call_args_list])

    def test_hud_maps_top_and_rep_completed_to_existing_display_labels(self):
        import numpy as np
        state = ExerciseState(
            exercise_name="LEFT_BICEP_CURL", repetitions=4, phase=ExercisePhase.TOP
        )
        for completed, expected in ((False, "HOLD  •"), (True, "REP COMPLETE")):
            state.rep_completed = completed
            with self.subTest(expected=expected), patch("ui.overlay.cv2.putText") as texts:
                OverlayRenderer().draw(
                    np.zeros((480, 640, 3), dtype="uint8"), self._full_arm_pose(),
                    MovementMetrics(elbow_angle_left=111), state, active_side="left",
                    readiness={"state": "ready", "valid": True, "active_side": "left"},
                )
            self.assertIn(expected, [call.args[1] for call in texts.call_args_list])

    def test_calibration_progress_bar_uses_existing_matching_frame_count(self):
        import numpy as np
        frame = np.zeros((480, 640, 3), dtype="uint8")
        with patch("ui.overlay.cv2.line") as lines:
            OverlayRenderer().draw(
                frame, None, None, None, readiness={
                    "state": "calibration_required", "label": "Calibration",
                    "message": "Hold bend steady (4/10).", "active_side": "left",
                    "calibration_progress": {"stage": "confirming",
                                              "matching_frames": 4, "required_frames": 10},
                },
            )
        colors = [call.args[3] for call in lines.call_args_list]
        self.assertEqual(colors[-2:], [(61, 71, 82), OverlayRenderer.COLORS["calibration"]])


if __name__ == "__main__":
    unittest.main()
