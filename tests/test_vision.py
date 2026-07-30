import os
import sys

sys.path.append(
    os.path.dirname(
        os.path.dirname(os.path.abspath(__file__))
    )
)

import cv2

from core.vision import VisionEngine

print("Creating VisionEngine...")
vision = VisionEngine()

vision.start()

frame = vision.get_frame()

cv2.imwrite("test_frame.jpg", frame)

vision.stop()

print("Saved test_frame.jpg")