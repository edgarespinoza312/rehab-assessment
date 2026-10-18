"""Measurement-usability diagnostics used only by the pose benchmark."""

from collections import Counter

from core.models import JointType


SIDE_JOINTS = {
    "left": (
        JointType.LEFT_SHOULDER,
        JointType.LEFT_ELBOW,
        JointType.LEFT_WRIST,
    ),
    "right": (
        JointType.RIGHT_SHOULDER,
        JointType.RIGHT_ELBOW,
        JointType.RIGHT_WRIST,
    ),
}


class BicepCurlDiagnostics:
    """Summarize required-joint availability and frame-to-frame angle change."""

    def __init__(self, side, minimum_visibility):
        if side not in SIDE_JOINTS:
            raise ValueError("side must be 'left' or 'right'")

        self.side = side
        self.required_joints = SIDE_JOINTS[side]
        self.minimum_visibility = minimum_visibility
        self.processed_frames = 0
        self.landmarks_available_frames = 0
        self.sufficient_visibility_frames = 0
        self.usable_measurement_frames = 0
        self.missing_landmark_frames = 0
        self.low_visibility_frames = 0
        self.angle_calculation_failures = 0
        self.missing_landmarks = Counter()
        self.valid_angle_samples = 0
        self.angle_changes = []
        self.previous_valid_angle = None

    def update(self, skeleton, elbow_angle):
        self.processed_frames += 1
        joints = {
            joint_type: skeleton.get_joint(joint_type)
            for joint_type in self.required_joints
        }
        missing = [
            joint_type
            for joint_type, joint in joints.items()
            if joint is None
        ]

        if missing:
            self.missing_landmark_frames += 1
            for joint_type in missing:
                self.missing_landmarks[joint_type.name] += 1
            self.previous_valid_angle = None
            return

        self.landmarks_available_frames += 1
        sufficiently_visible = all(
            joint.visibility >= self.minimum_visibility
            for joint in joints.values()
        )
        if not sufficiently_visible:
            self.low_visibility_frames += 1
            self.previous_valid_angle = None
            return

        self.sufficient_visibility_frames += 1
        if elbow_angle is None:
            self.angle_calculation_failures += 1
            self.previous_valid_angle = None
            return

        self.usable_measurement_frames += 1
        self.valid_angle_samples += 1
        if self.previous_valid_angle is not None:
            self.angle_changes.append(
                abs(elbow_angle - self.previous_valid_angle)
            )
        self.previous_valid_angle = elbow_angle

    def break_consecutive_sequence(self):
        self.previous_valid_angle = None

    def snapshot(self):
        frames = self.processed_frames
        angle_pairs = len(self.angle_changes)
        return {
            "side": self.side,
            "processed_frames": frames,
            "required_landmarks_available_frames": (
                self.landmarks_available_frames
            ),
            "required_landmarks_available_percent": self._percent(
                self.landmarks_available_frames,
                frames,
            ),
            "sufficient_visibility_frames": self.sufficient_visibility_frames,
            "sufficient_visibility_percent": self._percent(
                self.sufficient_visibility_frames,
                frames,
            ),
            "usable_measurement_frames": self.usable_measurement_frames,
            "usable_measurement_percent": self._percent(
                self.usable_measurement_frames,
                frames,
            ),
            "missing_landmark_frames": self.missing_landmark_frames,
            "low_visibility_frames": self.low_visibility_frames,
            "angle_calculation_failures": self.angle_calculation_failures,
            "missing_landmarks": dict(self.missing_landmarks),
            "valid_angle_samples": self.valid_angle_samples,
            "consecutive_valid_pairs": angle_pairs,
            "consecutive_valid_percent": self._percent(
                angle_pairs,
                max(0, frames - 1),
            ),
            "mean_absolute_angle_change_degrees": (
                sum(self.angle_changes) / angle_pairs
                if angle_pairs
                else None
            ),
            "maximum_absolute_angle_change_degrees": (
                max(self.angle_changes)
                if angle_pairs
                else None
            ),
        }

    @staticmethod
    def _percent(count, total):
        return 100.0 * count / total if total else 0.0
