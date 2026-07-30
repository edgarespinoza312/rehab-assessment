"""
test_pose.py

Standalone test for the Pose Layer.

This script:
1. Opens the webcam.
2. Captures one frame.
3. Runs MediaPipe Pose.
4. Draws the detected skeleton.
5. Saves the result as pose_test.jpg.
"""

import os
import sys

# Allow imports from the project root
sys.path.append(
    os.path.dirname(
        os.path.dirname(os.path.abspath(__file__))
    )
)

import cv2

from core.vision import VisionEngine
from core.pose import PoseEngine


def main():

    print("Initializing Vision Engine...")
    vision = VisionEngine()

    print("Initializing Pose Engine...")
    pose = PoseEngine()

    try:

        print("Starting camera...")
        vision.start()

        print("Capturing frame...")
        frame = vision.get_frame()

        print("Running pose estimation...")
        annotated_frame, results = pose.process(frame)

        print("Saving result...")
        cv2.imwrite("pose_test.jpg", annotated_frame)

        if results.pose_landmarks:
            print("✓ Pose detected successfully.")
        else:
            print("⚠ No pose detected.")

        print("Saved as pose_test.jpg")

    finally:

        vision.stop()
        pose.close()

        print("Resources released.")


if __name__ == "__main__":
    main()