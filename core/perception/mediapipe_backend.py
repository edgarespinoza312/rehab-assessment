"""Compatibility wrapper around Revaliv's unchanged MediaPipe PoseEngine."""

import time

from core.pose import PoseEngine
from core.perception.identity import IdentityState
from core.perception.readiness import AdaptedPose, ExerciseReadiness


class MediaPipeBackend:
    name = "mediapipe"

    def __init__(self, pose_engine=None, identity_state=None):
        self.pose_engine = pose_engine or PoseEngine()
        self.readiness = ExerciseReadiness(identity_state or IdentityState())
        self.last_result = None

    @property
    def identity_state(self):
        return self.readiness.identity_state

    @property
    def calibration_status(self):
        return self.readiness.calibration_status

    def begin_calibration(self, side: str):
        self.readiness.begin_calibration(side)
        self.last_result = None

    def reset_calibration(self):
        self.readiness.reset_calibration()
        self.last_result = None

    @property
    def runtime_diagnostics(self):
        return {
            "backend": self.name,
            "delegate": "CPU",
            "gpu_initialized": False,
            "gpu_inference_completed": False,
        }

    def process(
        self,
        frame,
        timestamp: float = 0.0,
        frame_number: int = 0,
        performance=None,
        exercise_side: str | None = None,
    ):
        started = time.perf_counter()
        annotated_frame, skeleton = self.pose_engine.process(
            frame,
            timestamp=timestamp,
            frame_number=frame_number,
            performance=performance,
        )
        height, width = frame.shape[:2]
        stage_started = performance.start_timer() if performance is not None else None
        candidate = AdaptedPose.from_skeleton(
            skeleton, width, height, native_source="mediapipe_visibility"
        )
        if performance is not None:
            performance.stop_timer("perception_decoding_adaptation", stage_started)
        stage_started = performance.start_timer() if performance is not None else None
        self.last_result = self.readiness.evaluate(
            candidate,
            backend=self.name,
            timestamp=timestamp,
            frame_number=frame_number,
            width=width,
            height=height,
            exercise_side=exercise_side,
            diagnostics={
                "total_perception_ms": (time.perf_counter() - started) * 1000,
                "source": "existing_mediapipe_pose_engine",
            },
            performance=performance,
        )
        if performance is not None:
            performance.stop_timer("exercise_readiness", stage_started)
        return annotated_frame, self.last_result.skeleton

    def close(self):
        self.pose_engine.close()
