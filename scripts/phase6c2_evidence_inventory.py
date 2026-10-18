"""Read-only Phase 6C.2 evidence inventory for the configured SQLite database."""

from __future__ import annotations

import argparse
import json
import sqlite3
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from statistics import mean, median, stdev


WORKOUT_METRICS = (
    "average_score",
    "rom_score",
    "tempo_score",
    "completion_score",
    "stability_score",
    "compensation_score",
    "symmetry_score",
    "target_repetitions",
    "completed_repetitions",
    "resistance_value",
    "resistance_unit",
    "resistance_type",
    "side",
    "started_at",
)
LEGACY_METRICS = (
    "average_score",
    "repetitions",
    "created_at",
)


def _values(rows, key):
    return [row[key] for row in rows if row[key] is not None]


def _stats(values):
    numeric = [float(value) for value in values]
    if not numeric:
        return {"count": 0}
    ordered = sorted(numeric)
    midpoint = len(ordered) // 2
    if len(ordered) % 2:
        quartiles = ordered[midpoint]
    else:
        quartiles = (ordered[midpoint - 1] + ordered[midpoint]) / 2
    lower = ordered[: len(ordered) // 2]
    upper = ordered[(len(ordered) + 1) // 2 :]
    return {
        "count": len(numeric),
        "min": min(numeric),
        "max": max(numeric),
        "mean": mean(numeric),
        "median": median(numeric),
        "stddev": stdev(numeric) if len(numeric) > 1 else 0.0,
        "iqr": (
            median(upper) - median(lower)
            if lower and upper
            else 0.0
        ),
    }


def _parse_time(value):
    if not value:
        return None
    return datetime.fromisoformat(value.replace(" ", "T"))


def _sequence_summary(rows):
    grouped = defaultdict(list)
    for row in rows:
        grouped[(row["patient_id"], row["exercise_id"], row["side"])].append(row)
    sequences = []
    for key, observations in grouped.items():
        observations.sort(key=lambda item: (item["occurred_at"], item["source_id"]))
        gaps = [
            (
                _parse_time(current["occurred_at"])
                - _parse_time(previous["occurred_at"])
            ).total_seconds()
            / 86400
            for previous, current in zip(observations, observations[1:])
        ]
        sequences.append({
            "patient_id": key[0],
            "exercise_id": key[1],
            "side": key[2],
            "length": len(observations),
            "earliest": observations[0]["occurred_at"],
            "latest": observations[-1]["occurred_at"],
            "gaps_days": gaps,
        })
    return {
        "sequence_count": len(sequences),
        "repeated_sequence_count": sum(
            sequence["length"] > 1 for sequence in sequences
        ),
        "sequence_lengths": Counter(
            sequence["length"] for sequence in sequences
        ),
        "sequences": sequences,
    }


def analyze(path):
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    patients = connection.execute("select patient_id from patients").fetchall()
    legacy = connection.execute(
        "select assessment_id, patient_id, exercise, repetitions, "
        "average_score, created_at from assessment_records"
    ).fetchall()
    sessions = connection.execute(
        "select workout_session_id, patient_id, status, started_at "
        "from workout_sessions"
    ).fetchall()
    workout = connection.execute(
        "select r.workout_exercise_result_id as source_id, "
        "s.workout_session_id, s.patient_id, r.exercise_id, r.side, s.status, "
        "s.started_at as occurred_at, r.average_score, r.rom_score, "
        "r.tempo_score, r.completion_score, r.stability_score, "
        "r.compensation_score, r.symmetry_score, r.target_repetitions, "
        "r.completed_repetitions, r.resistance_value, r.resistance_unit, "
        "r.resistance_type "
        "from workout_exercise_results r "
        "join workout_sessions s on s.workout_session_id = r.workout_session_id"
    ).fetchall()
    connection.close()

    workout_rows = [dict(row) for row in workout]
    legacy_rows = [dict(row) for row in legacy]
    all_observations = workout_rows + [
        {
            "source_id": row["assessment_id"],
            "patient_id": row["patient_id"],
            "exercise_id": None,
            "side": None,
            "status": "completed",
            "occurred_at": row["created_at"],
            "average_score": row["average_score"],
            "completed_repetitions": row["repetitions"],
        }
        for row in legacy_rows
    ]
    exercise_coverage = {}
    for exercise_id in sorted({row["exercise_id"] for row in workout_rows}):
        selected = [row for row in workout_rows if row["exercise_id"] == exercise_id]
        exercise_coverage[exercise_id] = {
            "total_observations": len(selected),
            "by_side": dict(Counter(row["side"] for row in selected)),
            "by_status": dict(Counter(row["status"] for row in selected)),
            "with_resistance": sum(
                row["resistance_value"] is not None for row in selected
            ),
            "without_resistance": sum(
                row["resistance_value"] is None for row in selected
            ),
            "resistance_units": dict(
                Counter(row["resistance_unit"] for row in selected
                        if row["resistance_unit"] is not None)
            ),
            "resistance_types": dict(
                Counter(row["resistance_type"] for row in selected
                        if row["resistance_type"] is not None)
            ),
        }
    metric_rows = workout_rows + legacy_rows
    metric_fields = {
        field: {
            "present": sum(row.get(field) is not None for row in metric_rows),
            "missing": sum(row.get(field) is None for row in metric_rows),
        }
        for field in set(WORKOUT_METRICS + LEGACY_METRICS)
    }
    distributions = {
        field: _stats(_values(workout_rows, field))
        for field in (
            "average_score",
            "rom_score",
            "tempo_score",
            "stability_score",
            "compensation_score",
            "symmetry_score",
            "completed_repetitions",
            "target_repetitions",
        )
    }
    distributions["completion_percentage"] = _stats(
        [
            row["completed_repetitions"] / row["target_repetitions"] * 100
            for row in workout_rows
            if row["completed_repetitions"] is not None
            and row["target_repetitions"]
        ]
    )
    cancelled = [row for row in sessions if row["status"] == "cancelled"]
    cancelled_result_count = sum(
        row["status"] == "cancelled" for row in workout_rows
    )
    completed_result_count = sum(
        row["status"] == "completed" for row in workout_rows
    )
    sequence = _sequence_summary(all_observations) if all_observations else {
        "sequence_count": 0,
        "repeated_sequence_count": 0,
        "sequence_lengths": {},
        "sequences": [],
    }
    return {
        "database": str(Path(path)),
        "provenance": {
            "patients": len(patients),
            "legacy_assessments": len(legacy_rows),
            "workout_sessions": len(sessions),
            "workout_results": len(workout_rows),
            "dataset_is_empty": not all_observations,
            "synthetic_or_clinical_status": (
                "no observations available"
                if not all_observations
                else "not determinable from stored rows"
            ),
        },
        "inventory": {
            "patients": len(patients),
            "legacy_assessments": len(legacy_rows),
            "workout_sessions": len(sessions),
            "completed_workout_sessions": sum(
                row["status"] == "completed" for row in sessions
            ),
            "cancelled_workout_sessions": len(cancelled),
            "workout_exercise_results": len(workout_rows),
            "stable_exercise_ids": len(
                {row["exercise_id"] for row in workout_rows}
            ),
            "sides": sorted({row["side"] for row in workout_rows}),
            "side_unspecified_legacy_records": len(legacy_rows),
            "resistance_units": sorted(
                {row["resistance_unit"] for row in workout_rows
                 if row["resistance_unit"] is not None}
            ),
            "resistance_types": sorted(
                {row["resistance_type"] for row in workout_rows
                 if row["resistance_type"] is not None}
            ),
        },
        "exercise_coverage": exercise_coverage,
        "metric_completeness": metric_fields,
        "distributions": distributions,
        "temporal_repetition": sequence,
        "resistance": {
            "observations_with_resistance": sum(
                row["resistance_value"] is not None for row in workout_rows
            ),
            "observations_without_resistance": sum(
                row["resistance_value"] is None for row in workout_rows
            ),
            "units": dict(Counter(
                row["resistance_unit"] for row in workout_rows
                if row["resistance_unit"] is not None
            )),
            "types": dict(Counter(
                row["resistance_type"] for row in workout_rows
                if row["resistance_type"] is not None
            )),
        },
        "cancelled_sessions": {
            "session_count": len(cancelled),
            "with_completed_results": sum(
                any(row["workout_session_id"] == session["workout_session_id"]
                    for row in workout_rows)
                for session in cancelled
            ) if cancelled else 0,
            "completed_result_count": cancelled_result_count,
            "completed_session_result_count": completed_result_count,
            "unfinished_exercises_fabricated": 0,
        },
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "database",
        nargs="?",
        default="dashboard/neuromotion.db",
    )
    args = parser.parse_args()
    print(json.dumps(analyze(args.database), indent=2, sort_keys=True,
                     default=lambda value: (
                         value.isoformat() if hasattr(value, "isoformat")
                         else str(value)
                     )))


if __name__ == "__main__":
    main()
