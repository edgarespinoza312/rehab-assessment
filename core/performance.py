"""Opt-in, in-process statistics enabled with ``REVALIV_PERF=1``."""

from collections import Counter, defaultdict, deque
import math
import os
import threading
import time


class PerformanceMonitor:
    """Keeps bounded rolling timings and rates without emitting per-frame logs."""

    def __init__(self, enabled=None, history_size=600):
        if enabled is None:
            enabled = os.environ.get("REVALIV_PERF", "").strip().lower() in {
                "1",
                "true",
                "yes",
                "on",
            }

        self.enabled = bool(enabled)
        self._lock = threading.Lock()
        self._stage_samples = defaultdict(
            lambda: deque(maxlen=history_size)
        )
        self._rate_events = defaultdict(
            lambda: deque(maxlen=history_size)
        )
        self._frame_age_samples = deque(maxlen=history_size)
        self._counters = Counter()
        self._last_report = 0.0

    def record_stage(self, name, duration_seconds):
        if not self.enabled:
            return
        with self._lock:
            self._stage_samples[name].append(
                max(0.0, duration_seconds)
            )

    def start_timer(self):
        return time.monotonic() if self.enabled else None

    def stop_timer(self, name, started_at):
        if started_at is not None:
            self.record_stage(
                name,
                time.monotonic() - started_at,
            )

    def increment(self, counter, amount=1):
        if not self.enabled:
            return
        with self._lock:
            self._counters[counter] += amount

    def record_rate_event(self, name, timestamp=None):
        if not self.enabled:
            return
        event_time = time.monotonic() if timestamp is None else timestamp
        with self._lock:
            self._rate_events[name].append(event_time)

    def record_post_capture_age(self, read_return_at, observed_at):
        if not self.enabled:
            return
        with self._lock:
            self._frame_age_samples.append(
                max(0.0, observed_at - read_return_at)
            )

    def should_log(self, interval_seconds=30.0, now=None):
        if not self.enabled:
            return False
        current_time = time.monotonic() if now is None else now
        with self._lock:
            if current_time - self._last_report < interval_seconds:
                return False
            self._last_report = current_time
            return True

    def snapshot(self):
        if not self.enabled:
            return {"enabled": False}

        with self._lock:
            stages = {
                name: {
                    "samples": len(samples),
                    "mean_ms": sum(samples) * 1000.0 / len(samples),
                    "p50_ms": self._percentile_ms(samples, 0.50),
                    "p95_ms": self._percentile_ms(samples, 0.95),
                    "min_ms": min(samples) * 1000.0,
                    "max_ms": max(samples) * 1000.0,
                }
                for name, samples in self._stage_samples.items()
                if samples
            }
            rates = {
                name: self._rate(events)
                for name, events in self._rate_events.items()
            }
            post_capture_age = self._summary_ms(self._frame_age_samples)
            counters = dict(self._counters)

        return {
            "enabled": True,
            "stages": stages,
            "rates_fps": rates,
            "post_capture_age": post_capture_age,
            "counters": counters,
        }

    @staticmethod
    def _rate(events):
        if len(events) < 2:
            return 0.0
        elapsed = events[-1] - events[0]
        return (len(events) - 1) / elapsed if elapsed > 0 else 0.0

    @staticmethod
    def _summary_ms(samples):
        if not samples:
            return {"samples": 0}
        return {
            "samples": len(samples),
            "mean_ms": sum(samples) * 1000.0 / len(samples),
            "p50_ms": PerformanceMonitor._percentile_ms(samples, 0.50),
            "p95_ms": PerformanceMonitor._percentile_ms(samples, 0.95),
            "max_ms": max(samples) * 1000.0,
        }

    @staticmethod
    def _percentile_ms(samples, percentile):
        ordered = sorted(samples)
        if not ordered:
            return 0.0
        rank = (len(ordered) - 1) * percentile
        lower = math.floor(rank)
        upper = math.ceil(rank)
        value = ordered[lower] + (ordered[upper] - ordered[lower]) * (rank - lower)
        return value * 1000.0
