import os
import sys
import unittest
from unittest.mock import Mock, patch

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.video_stream_guard import (
    CameraFailurePolicy,
    VideoConsumerGuard,
    release_on_close,
)
from core.vision import VisionEngine


class VideoConsumerGuardTests(unittest.TestCase):
    def test_first_consumer_is_admitted_and_second_is_rejected_without_pipeline_work(self):
        guard = VideoConsumerGuard()
        assessment_state = {"frames": 0, "reps": 0}
        first = guard.acquire()
        self.assertIsNotNone(first)
        self.assertTrue(guard.active)

        def drive_pipeline():
            assessment_state["frames"] += 1

        second = guard.acquire()
        self.assertIsNone(second)
        if second is not None:
            drive_pipeline()
        self.assertEqual(assessment_state, {"frames": 0, "reps": 0})

        # Admission does not interfere with the first consumer's stream work.
        drive_pipeline()
        self.assertEqual(assessment_state["frames"], 1)
        self.assertTrue(first.release())
        self.assertFalse(guard.active)

    def test_lease_releases_after_normal_stream_exhaustion(self):
        guard = VideoConsumerGuard()
        lease = guard.acquire()
        stream = release_on_close(lease, iter((b"frame-1", b"frame-2")))
        self.assertEqual(list(stream), [b"frame-1", b"frame-2"])
        self.assertFalse(guard.active)

    def test_lease_releases_when_client_closes_stream(self):
        guard = VideoConsumerGuard()
        lease = guard.acquire()

        def frames():
            yield b"frame"
            yield b"next-frame"

        stream = release_on_close(lease, frames())
        self.assertEqual(next(stream), b"frame")
        stream.close()
        self.assertFalse(guard.active)

    def test_lease_releases_after_stream_exception(self):
        guard = VideoConsumerGuard()
        lease = guard.acquire()

        def broken_stream():
            yield b"frame"
            raise RuntimeError("stream failed")

        stream = release_on_close(lease, broken_stream())
        self.assertEqual(next(stream), b"frame")
        with self.assertRaisesRegex(RuntimeError, "stream failed"):
            next(stream)
        self.assertFalse(guard.active)

    def test_release_is_idempotent_and_does_not_release_a_new_owner(self):
        guard = VideoConsumerGuard()
        first = guard.acquire()
        self.assertTrue(first.release())
        self.assertFalse(first.release())
        second = guard.acquire()
        self.assertIsNotNone(second)
        self.assertFalse(first.release())
        self.assertTrue(guard.active)
        second.release()


class CameraResourceCleanupTests(unittest.TestCase):
    def test_successful_read_without_frame_is_reported_as_capture_failure(self):
        vision = VisionEngine()
        camera = Mock()
        camera.read.return_value = (True, None)
        vision.camera = camera
        with self.assertRaisesRegex(RuntimeError, "Failed to capture frame"):
            vision.get_frame()

    def test_failed_start_releases_unopened_camera_handle(self):
        vision = VisionEngine()
        camera = Mock()
        camera.isOpened.return_value = False
        with patch("core.vision.cv2.VideoCapture", return_value=camera):
            with self.assertRaisesRegex(RuntimeError, "Unable to open webcam"):
                vision.start()
        camera.release.assert_called_once_with()
        self.assertIsNone(vision.camera)

    def test_stop_releases_camera_and_is_safe_when_repeated(self):
        vision = VisionEngine()
        camera = Mock()
        vision.camera = camera
        with patch("core.vision.cv2.destroyAllWindows") as destroy:
            vision.stop()
            vision.stop()
        camera.release.assert_called_once_with()
        destroy.assert_called_once_with()
        self.assertIsNone(vision.camera)


class CameraFailurePolicyTests(unittest.TestCase):
    def test_repeated_capture_failures_are_bounded_and_backed_off(self):
        policy = CameraFailurePolicy(max_consecutive_failures=3, retry_delay_seconds=0.1)
        self.assertFalse(policy.record_failure())
        self.assertFalse(policy.record_failure())
        self.assertTrue(policy.record_failure())
        self.assertEqual(policy.consecutive_failures, 3)
        self.assertGreater(policy.retry_delay_seconds, 0)

    def test_success_resets_consecutive_failure_count(self):
        policy = CameraFailurePolicy(max_consecutive_failures=3)
        policy.record_failure()
        policy.record_failure()
        policy.record_success()
        self.assertEqual(policy.consecutive_failures, 0)
        self.assertFalse(policy.record_failure())


if __name__ == "__main__":
    unittest.main()
