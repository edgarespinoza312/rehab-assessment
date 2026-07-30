from dataclasses import dataclass

@dataclass
class MovementMetrics:

    # ======================================================
    # Joint Angles
    # ======================================================

    shoulder_angle_left: float = 0.0
    shoulder_angle_right: float = 0.0

    elbow_angle_left: float = 0.0
    elbow_angle_right: float = 0.0

    hip_angle_left: float = 0.0
    hip_angle_right: float = 0.0

    knee_angle_left: float = 0.0
    knee_angle_right: float = 0.0

    # ======================================================
    # Exercise Performance
    # ======================================================

    range_of_motion: float = 0.0

    peak_extension: float = 0.0
    peak_flexion: float = 0.0

    rep_duration: float = 0.0

    concentric_duration: float = 0.0
    eccentric_duration: float = 0.0

    peak_velocity: float = 0.0
    average_velocity: float = 0.0

    # ======================================================
    # Stability
    # ======================================================

    trunk_lean: float = 0.0

    trunk_rotation: float = 0.0

    shoulder_elevation: float = 0.0

    head_movement: float = 0.0

    # ======================================================
    # Compensation
    # ======================================================

    torso_sway: float = 0.0

    lateral_shift: float = 0.0

    # ======================================================
    # Quality
    # ======================================================

    #symmetry_score: float = 100.0

    #smoothness_score: float = 100.0

    # Stability Metrics

    shoulder_displacement: float = 0.0
    torso_displacement: float = 0.0
    stability_score: float = 100.0

    # ==========================================================
    # Compensation Metrics
    # ==========================================================

    shoulder_hike: float = 0.0
    trunk_lean: float = 0.0

    shoulder_hike_detected: bool = False
    trunk_lean_detected: bool = False

    # ==========================================================
    # Symmetry Metrics
    # ==========================================================

    shoulder_height_difference: float = 0.0

    elbow_angle_difference: float = 0.0

    wrist_height_difference: float = 0.0