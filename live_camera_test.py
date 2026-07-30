import cv2
import time

cap = cv2.VideoCapture(0)

if not cap.isOpened():
    raise RuntimeError("Couldn't open camera")

while True:
    ret, frame = cap.read()
    if not ret:
        break

    timestamp = time.strftime("%H:%M:%S")

    cv2.putText(
        frame,
        timestamp,
        (20, 40),
        cv2.FONT_HERSHEY_SIMPLEX,
        1,
        (0, 255, 0),
        2,
    )

    cv2.imshow("Live Camera", frame)

    if cv2.waitKey(1) & 0xFF == ord("q"):
        break

cap.release()
cv2.destroyAllWindows()