"""Deterministic advisory classification of progression evidence.

This module is intentionally independent of Flask, SQLAlchemy, persistence,
and workout execution. Its classifications are software-validation heuristics,
not clinical conclusions or prescriptions.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Iterable


class ProgressionClassification(str, Enum):
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    NO_CHANGE = "NO_CHANGE"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    POSSIBLE_PROGRESSION = "POSSIBLE_PROGRESSION"
    POSSIBLE_REGRESSION = "POSSIBLE_REGRESSION"


@dataclass(frozen=True)
class AdvisoryEvidenceRecord:
    """The immutable evidence fields used by the advisory classifier."""

    patient_id: int | str
    exercise_id: str | None
    side: str | None
    occurred_at: datetime
    source_type: str
    session_status: str | None
    completed_repetitions: int | None
    target_repetitions: int | None
    overall_score: float | None
    resistance_value: float | None = None
    resistance_unit: str | None = None
    resistance_type: str | None = None
    source_id: int | str | None = None
    rom_score: float | None = None
    tempo_score: float | None = None
    stability_score: float | None = None
    compensation_score: float | None = None
    symmetry_score: float | None = None

    @property
    def completion_percentage(self) -> float | None:
        if self.completed_repetitions is None or not self.target_repetitions:
            return None
        return self.completed_repetitions / self.target_repetitions * 100


@dataclass(frozen=True)
class EvidenceSummary:
    """Machine-readable evidence explanation for one classification."""

    observation_count: int
    observation_dates: tuple[datetime, ...]
    source_types: tuple[str, ...]
    side: str | None
    overall_scores: tuple[float | None, ...]
    completion_percentages: tuple[float | None, ...]
    resistance_observations: tuple[tuple[
        datetime, float | None, str | None, str | None
    ], ...]
    reasons: tuple[str, ...]
    limitations: tuple[str, ...]


@dataclass(frozen=True)
class ProgressionDecision:
    """Advisory result with provenance and no prescription outputs."""

    patient_id: int | str
    exercise_id: str | None
    side: str | None
    classification: ProgressionClassification
    evidence_summary: EvidenceSummary
    evidence_records: tuple[AdvisoryEvidenceRecord, ...]
    limitations: tuple[str, ...]


MINIMUM_HISTORY_OBSERVATIONS = 2
SOFTWARE_VALIDATION_LIMITATION = (
    "This classification is based on software-validation heuristics "
    "and has not been clinically validated."
)


def _nondecreasing(values: tuple[float, ...]) -> bool:
    return all(left <= right for left, right in zip(values, values[1:]))


def _nonincreasing(values: tuple[float, ...]) -> bool:
    return all(left >= right for left, right in zip(values, values[1:]))


def _strict_change(values: tuple[float, ...], direction: str) -> bool:
    if direction == "up":
        return any(left < right for left, right in zip(values, values[1:]))
    return any(left > right for left, right in zip(values, values[1:]))


def _ordered_records(
    records: Iterable[AdvisoryEvidenceRecord],
    *,
    patient_id: int | str,
    exercise_id: str | None,
    side: str | None,
) -> tuple[AdvisoryEvidenceRecord, ...]:
    selected = [
        record for record in records
        if record.patient_id == patient_id
        and (exercise_id is None or record.exercise_id == exercise_id)
        and (side is None or record.side == side)
    ]
    return tuple(sorted(
        selected,
        key=lambda record: (record.occurred_at, str(record.source_id or "")),
    ))


def _summary(
    records: tuple[AdvisoryEvidenceRecord, ...],
    *,
    side: str | None,
    reasons: tuple[str, ...],
    limitations: tuple[str, ...],
) -> EvidenceSummary:
    return EvidenceSummary(
        observation_count=len(records),
        observation_dates=tuple(record.occurred_at for record in records),
        source_types=tuple(sorted({record.source_type for record in records})),
        side=side,
        overall_scores=tuple(record.overall_score for record in records),
        completion_percentages=tuple(
            record.completion_percentage for record in records
        ),
        resistance_observations=tuple(
            (
                record.occurred_at,
                record.resistance_value,
                record.resistance_unit,
                record.resistance_type,
            )
            for record in records
        ),
        reasons=reasons,
        limitations=limitations,
    )


def evaluate_progression(
    records: Iterable[AdvisoryEvidenceRecord],
    *,
    patient_id: int | str,
    exercise_id: str | None = None,
    side: str | None = None,
) -> ProgressionDecision:
    """Classify one patient/exercise/side history conservatively.

    The minimum history and directional rules below are software-validation
    heuristics. They are not clinical thresholds and do not prescribe anything.
    """

    selected = _ordered_records(
        records,
        patient_id=patient_id,
        exercise_id=exercise_id,
        side=side,
    )
    distinct_sides = {record.side for record in selected}
    resolved_side = side
    if side is None and len(distinct_sides) == 1:
        resolved_side = next(iter(distinct_sides))

    limitations = [SOFTWARE_VALIDATION_LIMITATION]
    if any(record.session_status == "cancelled" for record in selected):
        limitations.append(
            "Completed results from cancelled sessions are retained as "
            "evidence; their future clinical use remains TBD."
        )
    if any(record.resistance_value is None for record in selected):
        limitations.append("Some observations have no resistance metadata.")

    if not selected:
        reasons = ("No observations matched the requested patient, exercise, and side.",)
        classification = ProgressionClassification.INSUFFICIENT_DATA
    elif side is None and len(distinct_sides) > 1:
        reasons = (
            "Multiple explicit sides were present without a side-specific "
            "request; histories were not merged.",
        )
        classification = ProgressionClassification.REVIEW_REQUIRED
    elif len(selected) < MINIMUM_HISTORY_OBSERVATIONS:
        reasons = (
            f"Only {len(selected)} observation was available; at least "
            f"{MINIMUM_HISTORY_OBSERVATIONS} are required by this "
            "software-validation heuristic.",
        )
        classification = ProgressionClassification.INSUFFICIENT_DATA
    else:
        units = {
            record.resistance_unit
            for record in selected
            if record.resistance_value is not None
            and record.resistance_unit is not None
        }
        source_types = {record.source_type for record in selected}
        if len(units) > 1:
            reasons = (
                "Multiple resistance units were observed; numeric resistance "
                "comparison was not performed.",
            )
            classification = ProgressionClassification.REVIEW_REQUIRED
        elif len(source_types) > 1:
            reasons = (
                "Legacy and workout evidence were mixed; source semantics "
                "were preserved rather than treated as interchangeable.",
            )
            classification = ProgressionClassification.REVIEW_REQUIRED
        elif any(record.overall_score is None for record in selected):
            reasons = (
                "At least one observation lacks an overall score, so the "
                "performance pattern is incomplete.",
            )
            classification = ProgressionClassification.REVIEW_REQUIRED
        elif any(
            record.completion_percentage is None for record in selected
        ):
            reasons = (
                "At least one observation lacks a target/completion pair, so "
                "the repetition pattern is incomplete.",
            )
            classification = ProgressionClassification.INSUFFICIENT_DATA
        else:
            scores = tuple(record.overall_score for record in selected)
            completions = tuple(
                record.completion_percentage for record in selected
            )
            assert all(value is not None for value in scores)
            assert all(value is not None for value in completions)
            numeric_scores = tuple(value for value in scores if value is not None)
            numeric_completions = tuple(
                value for value in completions if value is not None
            )
            improving = (
                _nondecreasing(numeric_completions)
                and _nondecreasing(numeric_scores)
                and _strict_change(numeric_completions, "up")
            )
            declining = (
                _nonincreasing(numeric_completions)
                and _nonincreasing(numeric_scores)
                and _strict_change(numeric_completions, "down")
            )
            if improving:
                reasons = (
                    "Repeated observations show nondecreasing completion "
                    "with nondecreasing overall scores and a completion "
                    "increase. This matches the configured "
                    "software-validation progression pattern.",
                )
                classification = ProgressionClassification.POSSIBLE_PROGRESSION
            elif declining:
                reasons = (
                    "Repeated observations show nonincreasing completion "
                    "with nonincreasing overall scores and a completion "
                    "decrease. This matches the configured "
                    "software-validation regression pattern.",
                )
                classification = ProgressionClassification.POSSIBLE_REGRESSION
            elif (
                len(set(numeric_completions)) == 1
                and _nondecreasing(numeric_scores)
            ):
                reasons = (
                    "Repeated observations have stable completion and no "
                    "unfavorable directional pattern. This matches the "
                    "configured software-validation no-change pattern.",
                )
                classification = ProgressionClassification.NO_CHANGE
            else:
                reasons = (
                    "Repeated observations contain conflicting or "
                    "non-directional performance signals.",
                )
                classification = ProgressionClassification.REVIEW_REQUIRED

    summary = _summary(
        selected,
        side=resolved_side,
        reasons=reasons,
        limitations=tuple(limitations),
    )
    return ProgressionDecision(
        patient_id=patient_id,
        exercise_id=exercise_id,
        side=resolved_side,
        classification=classification,
        evidence_summary=summary,
        evidence_records=selected,
        limitations=tuple(limitations),
    )


def from_progression_result(result) -> AdvisoryEvidenceRecord:
    """Adapt an existing ``ProgressionResult`` without changing its meaning."""

    return AdvisoryEvidenceRecord(
        patient_id=result.patient_id,
        exercise_id=result.exercise_id,
        side=result.side,
        occurred_at=result.occurred_at,
        source_type=result.source_type,
        session_status=result.session_status,
        completed_repetitions=result.completed_repetitions,
        target_repetitions=result.target_repetitions,
        overall_score=result.overall_score,
        resistance_value=result.resistance_value,
        resistance_unit=result.resistance_unit,
        resistance_type=result.resistance_type,
        source_id=result.source_id,
        rom_score=result.rom_score,
        tempo_score=result.tempo_score,
        stability_score=result.stability_score,
        compensation_score=result.compensation_score,
        symmetry_score=result.symmetry_score,
    )
