import cv2

from core.models import (
    JointType,
    ExerciseState,
)


class OverlayRenderer:
    """
    Draws rehabilitation information onto the annotated video frame.
    """

    # ==========================================================
    # Public API
    # ==========================================================

    def draw(
        self,
        frame,
        skeleton,
        metrics,
        exercise_state: ExerciseState,
        tracking=True,
    ):
        """
        Draws all overlay components.
        """

        if skeleton is None:
            return frame

        self._draw_landmarks(
            frame,
            skeleton,
        )

        self._draw_measurements(
            frame,
            skeleton,
            metrics,
            exercise_state,
        )

        self._draw_exercise(
            frame,
            exercise_state,
        )

        self._draw_status(
            frame,
            tracking,
        )

        return frame

    # ==========================================================
    # Landmark Rendering
    # ==========================================================

    def _draw_landmarks(
        self,
        frame,
        skeleton,
    ):
        """
        Draws key ESPZ anatomical landmarks.
        """

        height, width = frame.shape[:2]

        landmark_colors = {
            JointType.SHOULDER_CENTER: ((0, 255, 0), "SC"),
            JointType.PELVIS_CENTER: ((255, 255, 0), "PC"),
            JointType.BODY_CENTER: ((255, 0, 255), "BC"),
            JointType.NECK: ((0, 200, 255), "N"),
            JointType.HEAD_CENTER: ((255, 0, 0), "HC"),
        }

        for joint_type, (color, label) in landmark_colors.items():

            joint = skeleton.get_joint(joint_type)

            if joint is None:
                continue

            x = int(joint.x * width)
            y = int(joint.y * height)

            x = max(0, min(width - 1, x))
            y = max(0, min(height - 1, y))

            cv2.circle(
                frame,
                (x, y),
                7,
                color,
                -1,
            )

            cv2.putText(
                frame,
                label,
                (x + 8, y - 8),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.45,
                color,
                2,
            )

    # ==========================================================
    # Measurement Rendering
    # ==========================================================

    def _draw_measurements(
        self,
        frame,
        skeleton,
        metrics,
        exercise_state,
    ):
        """
        Draws biomechanical measurements.
        """

        if metrics is None or exercise_state is None:
            return

        exercise = exercise_state.exercise_name

        print(f"\nExercise: {exercise}")

     # ------------------------------------------------------
        # Select which elbow to annotate based on the exercise
     # ------------------------------------------------------

        if exercise == "RIGHT_BICEP_CURL":
            print(">>> USING RIGHT ELBOW <<<")

            angle = metrics.elbow_angle_right
            elbow = skeleton.get_joint(JointType.RIGHT_ELBOW)

        else:
            print(">>> USING LEFT ELBOW <<<")

            angle = metrics.elbow_angle_left
            elbow = skeleton.get_joint(JointType.LEFT_ELBOW)

        print(f"Angle = {angle}")
        print(f"Joint = {elbow}")

        if angle is None or elbow is None:
            print("Missing angle or joint.")
            return

        height, width = frame.shape[:2]

        x = int(elbow.x * width)
        y = int(elbow.y * height)

        x = max(0, min(width - 1, x))
        y = max(0, min(height - 1, y))

        label = f"{angle:.0f}°"

        (text_width, text_height), _ = cv2.getTextSize(
            label,
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            2,
        )

        padding = 5

        cv2.rectangle(
            frame,
            (x + 10, y - text_height - 15),
            (x + text_width + padding * 2 + 10, y - 5),
            (30, 30, 30),
            -1,
        )

        cv2.putText(
            frame,
            label,
            (x + padding + 10, y - 10),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (0, 255, 255),
            2,
        )

        cv2.line(
            frame,
            (x, y),
            (x + 10, y - 10),
            (0, 255, 255),
            2,
        )

    # ==========================================================
    # Exercise Rendering
    # ==========================================================

    def _draw_exercise(
        self,
        frame,
        exercise_state: ExerciseState,
    ):
        """
        Draws the current exercise information.
        """

        if exercise_state is None:
            return

        x = 20
        y = 70
        spacing = 30

        cv2.putText(
            frame,
            f"Exercise: {exercise_state.exercise_name or 'None'}",
            (x, y),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.65,
            (255, 255, 255),
            2,
        )

        cv2.putText(
            frame,
            f"Phase: {exercise_state.phase.name}",
            (x, y + spacing),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.65,
            (255, 255, 255),
            2,
        )

        cv2.putText(
            frame,
            f"Reps: {exercise_state.repetitions}",
            (x, y + spacing * 2),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.65,
            (0, 255, 255),
            2,
        )

    # ==========================================================
    # Status Rendering
    # ==========================================================

    def _draw_status(
        self,
        frame,
        tracking,
    ):
        """
        Draws system tracking status.
        """

        status = "TRACKING" if tracking else "NO TRACKING"

        color = (
            (0, 255, 0)
            if tracking
            else (0, 0, 255)
        )

        cv2.putText(
            frame,
            status,
            (20, 30),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            color,
            2,
        )