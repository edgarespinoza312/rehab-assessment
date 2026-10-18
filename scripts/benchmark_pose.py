"""Compare existing MediaPipe Pose configurations using the live camera."""

import argparse
from dataclasses import dataclass
import time

from core.performance import PerformanceMonitor
from core.pose import PoseEngine
from core.vision import VisionEngine
from core.analyzers.joint_analyzer import JointAnalyzer
from core.exercise_catalog import get_exercise_profile
from core.models import ExerciseType, MovementMetrics
from scripts.pose_benchmark_metrics import BicepCurlDiagnostics


@dataclass(frozen=True)
class PoseConfiguration:
    name: str
    complexity: int
    smoothing: bool


CONFIGURATIONS = {
    "baseline": PoseConfiguration("baseline", 1, True),
    "complexity-0": PoseConfiguration("complexity-0", 0, True),
    "complexity-2": PoseConfiguration("complexity-2", 2, True),
    "no-smoothing": PoseConfiguration("no-smoothing", 1, False),
}


def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "Benchmark current MediaPipe Pose variants on the configured "
            "camera. Keep the camera, subject, and scene unchanged between "
            "configurations."
        )
    )
    parser.add_argument("--camera", type=int, default=0)
    parser.add_argument("--samples", type=int, default=120)
    parser.add_argument("--warmup", type=int, default=15)
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument(
        "--side",
        choices=("left", "right"),
        default="left",
        help="Bicep-curl side used for usability/angle diagnostics",
    )
    parser.add_argument(
        "--configs",
        default="baseline,complexity-0,complexity-2,no-smoothing",
        help="Comma-separated names: " + ", ".join(CONFIGURATIONS),
    )
    args = parser.parse_args()
    if args.samples < 1:
        parser.error("--samples must be at least 1")
    if args.warmup < 0:
        parser.error("--warmup cannot be negative")
    if args.repeats < 1:
        parser.error("--repeats must be at least 1")

    names = [name.strip() for name in args.configs.split(",") if name.strip()]
    if not names:
        parser.error("--configs must include at least one configuration")
    unknown = sorted(set(names) - CONFIGURATIONS.keys())
    if unknown:
        parser.error(f"unknown configuration(s): {', '.join(unknown)}")
    return args, [CONFIGURATIONS[name] for name in names]


def benchmark_configuration(
    vision,
    configuration,
    sample_count,
    warmup_count,
    side,
    repeat_number,
):
    monitor = PerformanceMonitor(enabled=True, history_size=sample_count)
    diagnostics = BicepCurlDiagnostics(
        side,
        JointAnalyzer.MIN_VISIBILITY,
    )
    profile = get_exercise_profile(
        ExerciseType.LEFT_BICEP_CURL
        if side == "left"
        else ExerciseType.RIGHT_BICEP_CURL
    )
    joint_analyzer = JointAnalyzer()
    counters = {
        "frames_captured": 0,
        "frames_processed": 0,
        "capture_failures": 0,
        "inference_failures": 0,
    }
    frame_number = 0
    errors = []
    pose_engine = None
    result = None

    try:
        pose_engine = PoseEngine(
            model_complexity=configuration.complexity,
            smooth_landmarks=configuration.smoothing,
        )

        for _ in range(warmup_count):
            try:
                frame = vision.get_frame()
                frame_number += 1
                pose_engine.process(
                    frame,
                    timestamp=time.monotonic(),
                    frame_number=frame_number,
                )
            except Exception as error:
                errors.append(f"warm-up: {error}")

        run_started = time.monotonic()
        for _ in range(sample_count):
            frame_started = time.monotonic()
            try:
                frame = vision.get_frame()
            except Exception as error:
                counters["capture_failures"] += 1
                errors.append(f"capture: {error}")
                diagnostics.break_consecutive_sequence()
                continue

            frame_number += 1
            counters["frames_captured"] += 1
            monitor.increment("frames_captured")
            monitor.record_stage(
                "camera_capture",
                time.monotonic() - frame_started,
            )
            captured_at = time.monotonic()

            try:
                _, skeleton = pose_engine.process(
                    frame,
                    timestamp=captured_at,
                    frame_number=frame_number,
                    performance=monitor,
                )
            except Exception as error:
                counters["inference_failures"] += 1
                errors.append(f"inference: {error}")
                diagnostics.break_consecutive_sequence()
                continue

            processed_at = time.monotonic()
            counters["frames_processed"] += 1
            monitor.increment("frames_processed")
            monitor.record_stage(
                "total_frame_processing",
                processed_at - frame_started,
            )
            monitor.record_rate_event("processed", processed_at)
            metrics = MovementMetrics()
            joint_analyzer.analyze(skeleton, metrics, profile)
            diagnostics.update(
                skeleton,
                (
                    metrics.elbow_angle_left
                    if side == "left"
                    else metrics.elbow_angle_right
                ),
            )

        run_finished = time.monotonic()
        timings = monitor.snapshot()["stages"]
        successful_samples = counters["frames_processed"]
        elapsed = run_finished - run_started
        fps = successful_samples / elapsed if elapsed > 0 else 0.0
        counters["dropped_frames"] = (
            counters["capture_failures"] + counters["inference_failures"]
        )
        stable = counters["dropped_frames"] == 0 and not errors

        result = {
            "configuration": configuration,
            "samples": successful_samples,
            "requested_samples": sample_count,
            "repeat": repeat_number,
            "fps": fps,
            "stable": stable,
            "errors": errors,
            "counters": counters,
            "pose_inference": timings.get("pose_inference"),
            "total_frame_processing": timings.get("total_frame_processing"),
            "measurement_diagnostics": diagnostics.snapshot(),
        }
    except Exception as error:
        errors.append(f"initialization: {error}")
        result = {
            "configuration": configuration,
            "samples": 0,
            "requested_samples": sample_count,
            "repeat": repeat_number,
            "fps": 0.0,
            "stable": False,
            "errors": errors,
            "counters": counters,
            "pose_inference": None,
            "total_frame_processing": None,
            "measurement_diagnostics": diagnostics.snapshot(),
        }
    finally:
        if pose_engine is not None:
            try:
                pose_engine.close()
            except Exception as error:
                errors.append(f"shutdown: {error}")

    if result is not None:
        result["errors"] = errors
        if any(error.startswith("shutdown:") for error in errors):
            result["stable"] = False
    return result


def print_result(result):
    configuration = result["configuration"]
    print("\nPOSE BENCHMARK — PERFORMANCE")
    print(
        "Configuration: "
        f"complexity={configuration.complexity}, "
        f"smoothing={configuration.smoothing}, "
        f"run={result['repeat']}"
    )
    print(
        f"Samples: {result['samples']} successful / "
        f"{result['requested_samples']} requested"
    )

    pose = result["pose_inference"]
    if pose is None:
        print("Pose inference mean/min/max: unavailable")
    else:
        print(
            "Pose inference mean/min/max: "
            f"{pose['mean_ms']:.2f} / {pose['min_ms']:.2f} / "
            f"{pose['max_ms']:.2f} ms"
        )

    total = result["total_frame_processing"]
    if total is None:
        print("Total benchmark frame mean: unavailable")
    else:
        print(
            "Total benchmark frame mean: "
            f"{total['mean_ms']:.2f} ms "
            "(camera capture + PoseEngine.process; excludes "
            "biomechanics, overlay, resize, JPEG encoding)"
        )

    counters = result["counters"]
    print(f"Measured FPS: {result['fps']:.2f}")
    print(
        "Frames captured/processed/dropped: "
        f"{counters['frames_captured']}/"
        f"{counters['frames_processed']}/"
        f"{counters['dropped_frames']}"
    )
    print(
        "Benchmark stability (camera/PoseEngine only): "
        f"{'YES' if result['stable'] else 'NO'}"
    )
    for error in result["errors"]:
        print(f"Failure: {error}")

    diagnostics = result["measurement_diagnostics"]
    print("POSE BENCHMARK — MEASUREMENT QUALITY DIAGNOSTICS")
    print(
        f"Bicep-curl side: {diagnostics['side']} "
        f"(visibility threshold: {JointAnalyzer.MIN_VISIBILITY:.2f})"
    )
    print(
        "Required landmarks available: "
        f"{diagnostics['required_landmarks_available_frames']}/"
        f"{diagnostics['processed_frames']} "
        f"({diagnostics['required_landmarks_available_percent']:.1f}%)"
    )
    print(
        "Required landmarks sufficiently visible: "
        f"{diagnostics['sufficient_visibility_frames']}/"
        f"{diagnostics['processed_frames']} "
        f"({diagnostics['sufficient_visibility_percent']:.1f}%)"
    )
    print(
        "Selected elbow angle computed / usable measurement: "
        f"{diagnostics['valid_angle_samples']}/"
        f"{diagnostics['processed_frames']} "
        f"({diagnostics['usable_measurement_percent']:.1f}%)"
    )
    print(
        "Frames with missing required landmarks / low visibility: "
        f"{diagnostics['missing_landmark_frames']}/"
        f"{diagnostics['low_visibility_frames']}"
    )
    print(
        "Angle calculation failures despite sufficient visibility: "
        f"{diagnostics['angle_calculation_failures']}"
    )
    print(
        "Missing landmark counts: "
        f"{diagnostics['missing_landmarks'] or 'none'}"
    )
    print(
        "Consecutive valid angle pairs: "
        f"{diagnostics['consecutive_valid_pairs']} "
        f"({diagnostics['consecutive_valid_percent']:.1f}% of adjacent "
        "processed frames)"
    )
    mean_change = diagnostics["mean_absolute_angle_change_degrees"]
    maximum_change = diagnostics["maximum_absolute_angle_change_degrees"]
    if mean_change is None:
        print("Absolute frame-to-frame elbow-angle change: unavailable")
    else:
        print(
            "Absolute frame-to-frame elbow-angle change "
            "(valid consecutive frames): "
            f"mean={mean_change:.2f}°, max={maximum_change:.2f}°"
        )


def print_aggregate(configuration, runs):
    def mean(values):
        return sum(values) / len(values) if values else 0.0

    fps = [run["fps"] for run in runs]
    inference = [
        run["pose_inference"]["mean_ms"]
        for run in runs
        if run["pose_inference"] is not None
    ]
    usable = [
        run["measurement_diagnostics"]["usable_measurement_percent"]
        for run in runs
    ]
    angle_means = [
        run["measurement_diagnostics"][
            "mean_absolute_angle_change_degrees"
        ]
        for run in runs
        if run["measurement_diagnostics"][
            "mean_absolute_angle_change_degrees"
        ] is not None
    ]
    angle_maxima = [
        run["measurement_diagnostics"][
            "maximum_absolute_angle_change_degrees"
        ]
        for run in runs
        if run["measurement_diagnostics"][
            "maximum_absolute_angle_change_degrees"
        ] is not None
    ]

    print(
        "\nPOSE BENCHMARK — REPEAT SUMMARY "
        f"(complexity={configuration.complexity}, "
        f"smoothing={configuration.smoothing})"
    )
    for index, run in enumerate(runs, start=1):
        run_inference = run["pose_inference"]
        inference_text = (
            f"{run_inference['mean_ms']:.2f} ms"
            if run_inference is not None
            else "unavailable"
        )
        diagnostics = run["measurement_diagnostics"]
        run_angle_mean = diagnostics["mean_absolute_angle_change_degrees"]
        angle_text = (
            f"{run_angle_mean:.2f}°"
            if run_angle_mean is not None
            else "unavailable"
        )
        print(
            f"Run {index}: FPS={run['fps']:.2f}, "
            f"inference mean={inference_text}, "
            f"usable={diagnostics['usable_measurement_percent']:.1f}%, "
            f"mean angle change={angle_text}"
        )

    print(
        f"Mean FPS={mean(fps):.2f}; "
        f"mean inference={mean(inference):.2f} ms; "
        f"mean usable measurement={mean(usable):.1f}%; "
        f"mean angle change={mean(angle_means):.2f}°; "
        f"maximum angle change={max(angle_maxima):.2f}°"
        if angle_maxima
        else f"Mean FPS={mean(fps):.2f}; "
        f"mean inference={mean(inference):.2f} ms; "
        f"mean usable measurement={mean(usable):.1f}%; "
        "angle-change statistics unavailable"
    )

def main():
    args, configurations = parse_args()
    vision = VisionEngine(camera_index=args.camera)
    results = []
    try:
        vision.start()
        print(
            "Controlled-session guidance: keep the camera, resolution, "
            "same subject and framing, and lighting as consistent as "
            "practical. For the selected side, repeat the same bicep curl "
            "at a steady, comfortable pace through the same range. Each "
            "configuration/run has its own warm-up. "
            "Separate runs are not perfectly identical."
        )
        results_by_configuration = {
            configuration.name: []
            for configuration in configurations
        }
        for repeat in range(args.repeats):
            ordered_configs = configurations[repeat:] + configurations[:repeat]
            for configuration in ordered_configs:
                result = benchmark_configuration(
                    vision,
                    configuration,
                    args.samples,
                    args.warmup,
                    args.side,
                    repeat + 1,
                )
                results_by_configuration[configuration.name].append(result)
                results.append(result)
                print_result(result)
        if args.repeats > 1:
            for configuration in configurations:
                print_aggregate(
                    configuration,
                    results_by_configuration[configuration.name],
                )
    except Exception as error:
        print(f"Camera benchmark could not run: {error}")
        return 2
    finally:
        vision.stop()

    return 0 if all(result["stable"] for result in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
