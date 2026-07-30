import cv2
import time

cap = cv2.VideoCapture(0)

if not cap.isOpened():
    raise RuntimeError("Couldn't open camera")

start = time.time()

for i in range(30):
    ret, frame = cap.read()
    if not ret:
        print("Failed")
        break

end = time.time()

print(f"Captured 30 frames in {end - start:.2f} seconds")

cv2.imwrite("test.jpg", frame)

cap.release()