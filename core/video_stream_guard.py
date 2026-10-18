"""Small in-process guards for the process-wide video assessment pipeline."""

from dataclasses import dataclass
import threading


@dataclass
class VideoConsumerLease:
    """A single-use ownership token for the shared video pipeline."""

    _guard: "VideoConsumerGuard"
    _token: object

    def release(self) -> bool:
        return self._guard.release(self)


class VideoConsumerGuard:
    """Admit at most one consumer of shared camera/assessment state."""

    def __init__(self):
        self._lock = threading.Lock()
        self._active_token = None

    def acquire(self) -> VideoConsumerLease | None:
        with self._lock:
            if self._active_token is not None:
                return None
            token = object()
            self._active_token = token
            return VideoConsumerLease(self, token)

    def release(self, lease: VideoConsumerLease) -> bool:
        with self._lock:
            if lease._guard is not self or lease._token is not self._active_token:
                return False
            self._active_token = None
            return True

    @property
    def active(self) -> bool:
        with self._lock:
            return self._active_token is not None


class CameraFailurePolicy:
    """Bounds consecutive camera read retries and defines their backoff."""

    def __init__(self, max_consecutive_failures=3, retry_delay_seconds=0.1):
        if max_consecutive_failures < 1:
            raise ValueError("max_consecutive_failures must be positive")
        if retry_delay_seconds < 0:
            raise ValueError("retry_delay_seconds cannot be negative")
        self.max_consecutive_failures = max_consecutive_failures
        self.retry_delay_seconds = retry_delay_seconds
        self.consecutive_failures = 0

    def record_failure(self) -> bool:
        self.consecutive_failures += 1
        return self.consecutive_failures >= self.max_consecutive_failures

    def record_success(self) -> None:
        self.consecutive_failures = 0


def release_on_close(lease: VideoConsumerLease, stream, on_release=None):
    """Yield a stream and release its lease on close, exhaustion, or error."""
    try:
        yield from stream
    finally:
        released = lease.release()
        if released and on_release is not None:
            on_release()
