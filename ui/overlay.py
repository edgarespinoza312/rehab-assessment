"""Clinical, data-grounded drawing for the live assessment stream."""

from copy import deepcopy
import math

import cv2

from core.models import ExerciseState, JointType


class OverlayRenderer:
    """Render only accepted Skeletons and current authoritative measurements."""

    COLORS = {
        "anatomy": (118, 134, 148),       # subdued cool gray, BGR
        "secondary": (82, 101, 118),
        "active": (255, 188, 42),          # electric cyan, BGR
        "active_core": (232, 250, 255),
        "active_glow": (93, 92, 42),
        "ready": (255, 188, 42),
        "calibration": (0, 190, 255),      # gold/amber, BGR
        "quality": (0, 130, 255),          # saturated orange, BGR
        "ambiguous": (76, 72, 235),        # coral/red, BGR
        "held": (110, 130, 150),
        "panel": (18, 28, 39),
        "text": (237, 243, 248),
        "muted_text": (165, 183, 199),
        "green_accent": (90, 208, 150),
    }

    STATE_COLORS = {
        "ready": COLORS["ready"],
        "calibration_required": COLORS["calibration"],
        "identity_ambiguous": COLORS["ambiguous"],
        "low_confidence": COLORS["quality"],
        "poor_quality": COLORS["quality"],
        "no_person": COLORS["secondary"],
    }

    GENERAL_EDGES = (
        (JointType.NOSE, JointType.NECK),
        (JointType.NECK, JointType.SHOULDER_CENTER),
        (JointType.LEFT_SHOULDER, JointType.RIGHT_SHOULDER),
        (JointType.SHOULDER_CENTER, JointType.PELVIS_CENTER),
        (JointType.LEFT_SHOULDER, JointType.LEFT_HIP),
        (JointType.RIGHT_SHOULDER, JointType.RIGHT_HIP),
        (JointType.PELVIS_CENTER, JointType.LEFT_HIP),
        (JointType.PELVIS_CENTER, JointType.RIGHT_HIP),
        (JointType.LEFT_HIP, JointType.RIGHT_HIP),
        (JointType.LEFT_HIP, JointType.LEFT_KNEE),
        (JointType.LEFT_KNEE, JointType.LEFT_ANKLE),
        (JointType.RIGHT_HIP, JointType.RIGHT_KNEE),
        (JointType.RIGHT_KNEE, JointType.RIGHT_ANKLE),
        (JointType.LEFT_SHOULDER, JointType.LEFT_ELBOW),
        (JointType.LEFT_ELBOW, JointType.LEFT_WRIST),
        (JointType.RIGHT_SHOULDER, JointType.RIGHT_ELBOW),
        (JointType.RIGHT_ELBOW, JointType.RIGHT_WRIST),
    )

    ARM_JOINTS = {
        "left": (JointType.LEFT_SHOULDER, JointType.LEFT_ELBOW, JointType.LEFT_WRIST),
        "right": (JointType.RIGHT_SHOULDER, JointType.RIGHT_ELBOW, JointType.RIGHT_WRIST),
    }

    def draw(
        self,
        frame,
        skeleton,
        metrics,
        exercise_state: ExerciseState | None,
        tracking=True,
        active_side=None,
        readiness=None,
        display_only_stale=False,
    ):
        readiness = readiness or {}
        state = readiness.get("state")
        active_side = self._normalize_side(active_side or readiness.get("active_side"))
        if state == "identity_ambiguous":
            active_side = None

        can_show_pose = state != "no_person"
        if skeleton is not None and can_show_pose:
            self._draw_skeleton(
                frame,
                skeleton,
                active_side,
                stale=display_only_stale,
                readiness_state=state,
                exercise_state=exercise_state,
            )
            if not display_only_stale and readiness.get("valid", True):
                self._draw_measurements(
                    frame, skeleton, metrics, active_side, readiness_state=state
                )
                self._draw_exercise_hud(
                    frame, exercise_state, active_side, metrics,
                    readiness_state=state,
                )
        self._draw_readiness(frame, readiness, tracking, display_only_stale)
        return frame

    @staticmethod
    def _normalize_side(side):
        side = side.lower().strip() if isinstance(side, str) else None
        return side if side in {"left", "right"} else None

    @staticmethod
    def _pixel_joint(skeleton, joint_type, width, height):
        joint = skeleton.get_joint(joint_type)
        if joint is None:
            return None
        if not all(math.isfinite(value) for value in (joint.x, joint.y)):
            return None
        if not 0.0 <= joint.x <= 1.0 or not 0.0 <= joint.y <= 1.0:
            return None
        return (round(joint.x * (width - 1)), round(joint.y * (height - 1))), joint

    def _draw_skeleton(
        self, frame, skeleton, active_side, *, stale, readiness_state, exercise_state
    ):
        height, width = frame.shape[:2]
        state = readiness_state
        if stale:
            active_color = self.COLORS["held"]
            general_color = self.COLORS["held"]
        elif state == "calibration_required":
            active_color = self.COLORS["calibration"]
            general_color = self.COLORS["secondary"]
        else:
            active_color = self.COLORS["active"]
            general_color = self.COLORS["anatomy"]

        elbow_joint = self._relevant_joint(exercise_state)
        if state == "identity_ambiguous":
            active_side = None

        for first_type, second_type in self.GENERAL_EDGES:
            first = self._pixel_joint(skeleton, first_type, width, height)
            second = self._pixel_joint(skeleton, second_type, width, height)
            if first is None or second is None:
                continue
            first_point, first_joint = first
            second_point, second_joint = second
            if min(first_joint.visibility, second_joint.visibility) < 0.5:
                continue

            first_side = self._joint_side(first_type)
            second_side = self._joint_side(second_type)
            is_active_segment = (
                active_side is not None
                and first_side == active_side
                and second_side == active_side
                and first_type in self.ARM_JOINTS[active_side]
                and second_type in self.ARM_JOINTS[active_side]
            )
            if stale:
                self._draw_dashed_line(
                    frame, first_point, second_point, self.COLORS["held"], 2
                )
            elif is_active_segment:
                # A restrained darker under-stroke gives the active segment
                # contrast without adding an animated or large glow effect.
                cv2.line(
                    frame, first_point, second_point,
                    self.COLORS["active_glow"], 7, cv2.LINE_AA,
                )
                cv2.line(
                    frame, first_point, second_point, active_color, 4, cv2.LINE_AA
                )
                cv2.line(
                    frame, first_point, second_point,
                    self.COLORS["active_core"], 1, cv2.LINE_AA,
                )
            else:
                cv2.line(frame, first_point, second_point, general_color, 2, cv2.LINE_AA)

        joint_types = (
            JointType.NOSE,
            JointType.NECK,
            JointType.SHOULDER_CENTER,
            JointType.PELVIS_CENTER,
            JointType.LEFT_SHOULDER,
            JointType.RIGHT_SHOULDER,
            JointType.LEFT_ELBOW,
            JointType.RIGHT_ELBOW,
            JointType.LEFT_WRIST,
            JointType.RIGHT_WRIST,
            JointType.LEFT_HIP,
            JointType.RIGHT_HIP,
            JointType.LEFT_KNEE,
            JointType.RIGHT_KNEE,
            JointType.LEFT_ANKLE,
            JointType.RIGHT_ANKLE,
        )
        for joint_type in joint_types:
            located = self._pixel_joint(skeleton, joint_type, width, height)
            if located is None:
                continue
            point, joint = located
            side = self._joint_side(joint_type)
            active = active_side is not None and side == active_side
            if stale:
                cv2.circle(frame, point, 4, self.COLORS["held"], 1, cv2.LINE_AA)
                continue

            confidence_ok = joint.visibility >= (0.65 if active else 0.50)
            if not confidence_ok:
                cv2.circle(frame, point, 3, self.COLORS["secondary"], 1, cv2.LINE_AA)
                continue

            if active:
                radius = 8 if joint_type == elbow_joint else 6
                cv2.circle(frame, point, radius, self.COLORS["active_glow"], -1, cv2.LINE_AA)
                cv2.circle(frame, point, radius - 2, active_color, -1, cv2.LINE_AA)
                cv2.circle(frame, point, 2, self.COLORS["active_core"], -1, cv2.LINE_AA)
            else:
                cv2.circle(frame, point, 4, general_color, -1, cv2.LINE_AA)

    @staticmethod
    def _joint_side(joint_type):
        name = joint_type.name
        if name.startswith("LEFT_"):
            return "left"
        if name.startswith("RIGHT_"):
            return "right"
        return None

    @staticmethod
    def _relevant_joint(exercise_state):
        name = getattr(exercise_state, "exercise_name", "") or ""
        if "BICEP_CURL" in name.upper():
            return JointType.LEFT_ELBOW if "LEFT" in name.upper() else JointType.RIGHT_ELBOW
        return None

    def _draw_measurements(self, frame, skeleton, metrics, active_side, *, readiness_state):
        if metrics is None or readiness_state == "identity_ambiguous":
            return
        side = active_side
        if side is None:
            return
        angle = getattr(metrics, f"elbow_angle_{side}", None)
        if angle is None or not math.isfinite(float(angle)):
            return

        height, width = frame.shape[:2]
        elbow_type = self.ARM_JOINTS[side][1]
        elbow_data = self._pixel_joint(skeleton, elbow_type, width, height)
        if elbow_data is None:
            return
        elbow, elbow_joint = elbow_data
        if elbow_joint.visibility < 0.65:
            return

        shoulder_data = self._pixel_joint(skeleton, self.ARM_JOINTS[side][0], width, height)
        wrist_data = self._pixel_joint(skeleton, self.ARM_JOINTS[side][2], width, height)
        if shoulder_data is not None and wrist_data is not None:
            self._draw_measured_angle_arc(
                frame, elbow, shoulder_data[0], wrist_data[0],
                self.COLORS["active"],
            )

        label = f"{float(angle):.0f}°"
        (text_width, text_height), _ = cv2.getTextSize(
            label, cv2.FONT_HERSHEY_SIMPLEX, 0.62, 2
        )
        box_width = text_width + 18
        box_height = text_height + 14
        x = elbow[0] + 16
        if x + box_width > width - 8:
            x = elbow[0] - box_width - 16
        x = max(8, x)
        y = max(box_height + 8, elbow[1] - 17)
        cv2.line(frame, elbow, (x if x > elbow[0] else x + box_width, y - 5),
                 self.COLORS["active"], 1, cv2.LINE_AA)
        cv2.rectangle(
            frame, (x, y - box_height), (x + box_width, y),
            self.COLORS["panel"], -1,
        )
        cv2.rectangle(
            frame, (x, y - box_height), (x + box_width, y),
            self.COLORS["active"], 1,
        )
        cv2.putText(
            frame, label, (x + 9, y - 7), cv2.FONT_HERSHEY_SIMPLEX,
            0.62, self.COLORS["text"], 2, cv2.LINE_AA,
        )

    @staticmethod
    def _draw_measured_angle_arc(frame, elbow, shoulder, wrist, color):
        """Mark the measured joint angle using only the observed limb rays."""
        shoulder_ray = math.degrees(math.atan2(shoulder[1] - elbow[1], shoulder[0] - elbow[0])) % 360
        wrist_ray = math.degrees(math.atan2(wrist[1] - elbow[1], wrist[0] - elbow[0])) % 360
        difference = (wrist_ray - shoulder_ray + 180) % 360 - 180
        if difference >= 0:
            start_angle, end_angle = shoulder_ray, shoulder_ray + difference
        else:
            start_angle, end_angle = wrist_ray, wrist_ray - difference
        cv2.ellipse(
            frame, elbow, (19, 19), 0,
            round(start_angle), round(end_angle), color, 2, cv2.LINE_AA,
        )

    def _draw_exercise_hud(self, frame, exercise_state, active_side, metrics, *, readiness_state):
        if exercise_state is None or readiness_state == "identity_ambiguous":
            return
        height, width = frame.shape[:2]
        name = (getattr(exercise_state, "exercise_name", None) or "EXERCISE").upper()
        if "BICEP_CURL" in name:
            side = active_side or ("left" if "LEFT" in name else "right")
            title = f"{side.upper()} ARM CURL"
        else:
            title = name.replace("_", " ")[:24]

        phase_name = getattr(getattr(exercise_state, "phase", None), "name", "IDLE")
        phases = {
            "IDLE": "POSITIONING",
            "LOWERED": "READY",
            "LIFTING": "RAISING  ↑",
            "TOP": "HOLD  •",
            "LOWERING": "LOWERING  ↓",
        }
        phase = "REP COMPLETE" if getattr(exercise_state, "rep_completed", False) else phases.get(phase_name, phase_name.replace("_", " "))
        accent = self.STATE_COLORS.get(readiness_state, self.COLORS["active"])

        panel_x, panel_y = 12, 78
        panel_w, panel_h = min(198, width - 24), 108
        if height < panel_y + panel_h + 8:
            panel_y = max(8, height - panel_h - 8)
        cv2.rectangle(frame, (panel_x, panel_y), (panel_x + panel_w, panel_y + panel_h), self.COLORS["panel"], -1)
        cv2.rectangle(frame, (panel_x, panel_y), (panel_x + 3, panel_y + panel_h), accent, -1)
        cv2.putText(frame, title[:26], (panel_x + 12, panel_y + 20),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.46, self.COLORS["muted_text"], 1, cv2.LINE_AA)
        cv2.putText(frame, "REPS", (panel_x + 12, panel_y + 47),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.40, self.COLORS["muted_text"], 1, cv2.LINE_AA)
        cv2.putText(frame, str(max(0, int(getattr(exercise_state, "repetitions", 0)))),
                    (panel_x + 65, panel_y + 49), cv2.FONT_HERSHEY_SIMPLEX,
                    0.78, self.COLORS["text"], 2, cv2.LINE_AA)
        cv2.putText(frame, phase, (panel_x + 12, panel_y + 73),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.52, accent, 1, cv2.LINE_AA)

        rom = getattr(metrics, "range_of_motion", None) if metrics is not None else None
        if rom is not None and math.isfinite(float(rom)):
            cv2.putText(frame, f"OBSERVED ROM  {float(rom):.0f}°",
                        (panel_x + 12, panel_y + 95), cv2.FONT_HERSHEY_SIMPLEX,
                        0.38, self.COLORS["muted_text"], 1, cv2.LINE_AA)

    def _draw_readiness(self, frame, readiness, tracking, stale):
        height, width = frame.shape[:2]
        readiness = readiness or {
            "label": "Checking pose", "message": "Keep your upper body in view.",
            "state": "poor_quality",
        }
        state = readiness.get("state", "poor_quality")
        accent = self.STATE_COLORS.get(state, self.COLORS["secondary"])
        label = readiness.get("label", "Pose status")
        message = readiness.get("message", "")
        if stale:
            label = "Pose temporarily unavailable"
            message = "Last accepted pose shown for display only; measurements paused."
        elif state == "ready" and tracking:
            label = "READY · TRACKING"
            accent = self.COLORS["green_accent"]

        calibration = readiness.get("calibration_progress") or {}
        is_progress = state == "calibration_required" and calibration.get("stage") == "confirming"
        panel_height = 72 if is_progress else (62 if message else 38)
        right = max(12, width - 12)
        cv2.rectangle(frame, (8, 8), (right, panel_height), self.COLORS["panel"], -1)
        cv2.rectangle(frame, (8, 8), (12, panel_height), accent, -1)
        cv2.putText(
            frame, label[:62], (20, 29), cv2.FONT_HERSHEY_SIMPLEX,
            0.50, accent, 1, cv2.LINE_AA,
        )
        side = readiness.get("active_side")
        if side and state != "identity_ambiguous" and not stale:
            side_label = f"{side.upper()} ARM"
            (side_w, _), _ = cv2.getTextSize(side_label, cv2.FONT_HERSHEY_SIMPLEX, 0.42, 1)
            cv2.putText(frame, side_label, (right - side_w - 10, 28),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.42, self.COLORS["muted_text"], 1, cv2.LINE_AA)
        if message:
            cv2.putText(
                frame, message[:82], (20, 51), cv2.FONT_HERSHEY_SIMPLEX,
                0.41, self.COLORS["text"], 1, cv2.LINE_AA,
            )
        if is_progress:
            matching = max(0, int(calibration.get("matching_frames", 0)))
            required = max(1, int(calibration.get("required_frames", 10)))
            progress = min(1.0, matching / required)
            bar_left, bar_right = 20, max(21, right - 10)
            bar_y = 63
            cv2.line(frame, (bar_left, bar_y), (bar_right, bar_y), (61, 71, 82), 3, cv2.LINE_AA)
            cv2.line(frame, (bar_left, bar_y),
                     (bar_left + round((bar_right - bar_left) * progress), bar_y),
                     accent, 3, cv2.LINE_AA)

    @staticmethod
    def _draw_dashed_line(frame, start, end, color, thickness=2):
        dx, dy = end[0] - start[0], end[1] - start[1]
        length = math.hypot(dx, dy)
        if length <= 0:
            return
        ux, uy = dx / length, dy / length
        for offset in range(0, int(length), 10):
            stop = min(offset + 5, length)
            cv2.line(
                frame,
                (round(start[0] + ux * offset), round(start[1] + uy * offset)),
                (round(start[0] + ux * stop), round(start[1] + uy * stop)),
                color,
                thickness,
                cv2.LINE_AA,
            )


class PoseDisplayContinuity:
    """Briefly retain an accepted pose for muted display only."""

    def __init__(self, max_age_seconds=0.2):
        self.max_age_seconds = max(0.0, float(max_age_seconds))
        self._skeleton = None
        self._side = None
        self._timestamp = None

    def remember(self, skeleton, active_side, timestamp):
        self._skeleton = deepcopy(skeleton) if skeleton is not None else None
        self._side = OverlayRenderer._normalize_side(active_side)
        self._timestamp = timestamp if skeleton is not None else None

    def for_display(self, now, active_side, allowed):
        if (
            not allowed
            or self._skeleton is None
            or self._side != OverlayRenderer._normalize_side(active_side)
        ):
            self.clear()
            return None, False
        age = now - self._timestamp
        if age < 0 or age > self.max_age_seconds:
            self.clear()
            return None, False
        return deepcopy(self._skeleton), True

    def clear(self):
        self._skeleton = None
        self._side = None
        self._timestamp = None
