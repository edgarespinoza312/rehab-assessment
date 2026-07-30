from flask import (
    Flask,
    Response,
    jsonify,
    redirect,
    render_template,
    request,
    url_for,
)
from datetime import datetime
from dashboard.database import db
from dashboard.config import Config
from dashboard.database import db, migrate

# Import models so SQLAlchemy knows they exist
from dashboard.models import Patient, AssessmentRecord
import json
import cv2
import os
import sys

# ==========================================================
# Allow imports from project root
# ==========================================================

sys.path.append(
    os.path.dirname(
        os.path.dirname(
            os.path.abspath(__file__)
        )
    )
)

# ==========================================================
# Core Modules
# ==========================================================

from dashboard.anatomy.registry import anatomy_profile_for

from core.session_manager import SessionManager
from core.vision import VisionEngine
from core.pose import PoseEngine
from core.biomechanics import BiomechanicsEngine
from core.exercise import ExerciseEngine
from core.assessment import AssessmentEngine

from core.exercise_registry import get_profiles
from core.exercise_catalog import get_exercise_profile
from flask import request
from core.models import (
    AssessmentSession,
    ExerciseState,
    ExerciseType,
)

from ui.overlay import OverlayRenderer

# ==========================================================
# Flask Application
# ==========================================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

app = Flask(
    __name__,
    template_folder=os.path.join(
        BASE_DIR,
        "templates",
    ),
)

app.config.from_object(Config)

db.init_app(app)
migrate.init_app(app, db)

# ==========================================================
# Engine Initialization
# ==========================================================

vision = VisionEngine(
    camera_index=0,
)

pose = PoseEngine()

biomechanics = BiomechanicsEngine()

exercise = ExerciseEngine()

assessment = AssessmentEngine()

session_manager = SessionManager()

overlay = OverlayRenderer()

# Start the webcam
vision.start()


# ==========================================================
# Global Application State
# ==========================================================

# Active assessment session.


# Most recently completed assessment.
completed_session = None

# ==========================================================
# Helper Functions
# ==========================================================

def fmt(value, decimals=2):
    """
    Safely format numeric values for debugging.
    """

    if value is None:
        return "N/A"

    return f"{value:.{decimals}f}"

# ==========================================================
# Routes
# ==========================================================



@app.route(
    "/assessment/<int:assessment_id>/notes",
    methods=["POST"]
)
def update_assessment_notes(assessment_id):

    assessment = AssessmentRecord.query.get_or_404(
        assessment_id
    )

    assessment.notes = request.form["notes"]

    db.session.commit()

    return redirect(
        url_for(
            "view_assessment",
            assessment_id=assessment_id
        )
    )

@app.route("/assessment/<int:assessment_id>")
def view_assessment(assessment_id):

    import json

    assessment = AssessmentRecord.query.get_or_404(
        assessment_id
    )

    report = {

        "exercise": assessment.exercise,
        "repetitions": assessment.repetitions,
        "average_score": assessment.average_score,
        "best_score": assessment.best_score,
        "worst_score": assessment.worst_score,
        "trend": assessment.trend,
        "feedback": json.loads(
            assessment.feedback or "[]"
        )

    }

    return render_template(
        "report.html",
        report=report,
        patient=assessment.patient,
        assessment=assessment,
        historical=True

    )


@app.route("/patients/new", methods=["GET", "POST"])
def new_patient():

    if request.method == "POST":

        patient = Patient(
            first_name=request.form["first_name"],
            last_name=request.form["last_name"],
            date_of_birth=datetime.strptime(
                request.form["date_of_birth"],
                "%Y-%m-%d"
            ).date(),
            sex=request.form["sex"],
            diagnosis=request.form["diagnosis"],
            affected_side=request.form["affected_side"],
            therapist_notes=request.form.get(
                "therapist_notes",
                ""
            ),
        )

        db.session.add(patient)
        db.session.commit()

        return redirect(
            url_for("patient_registry")
        )

    return render_template(
        "new_patient.html"
    )

@app.route("/")
def home():

    patients = Patient.query.order_by(
        Patient.last_name
    ).all()

    return render_template(
        "patients.html",
        patients=patients,
    )

@app.route("/selection")
def selection():

    patient_id = request.args.get(
        "patient_id",
        type=int
    )

    print("Selection page patient_id =", patient_id)

    return render_template(
        "selection.html",
        profiles=get_profiles(),
        patient_id=patient_id,
    )

@app.route("/patients")
def patient_registry():

    patients = Patient.query.order_by(
        Patient.last_name
    ).all()

    return render_template(
        "patients.html",
        patients=patients,
    )
    
@app.route("/patients/<int:patient_id>")
def patient_profile(patient_id):

    patient = Patient.query.get_or_404(patient_id)

    assessments = sorted(
        patient.assessments,
        key=lambda assessment: assessment.created_at,
        reverse=True
    )

    assessment_count = len(assessments)

    if assessment_count > 0:

        average_score = round(
            sum(
                assessment.average_score
                for assessment in assessments
            ) / assessment_count,
            1
        )

        best_score = round(
            max(
                assessment.best_score
                for assessment in assessments
            ),
            1
        )

        latest_assessment = assessments[0]

        latest_date = latest_assessment.created_at.strftime(
            "%B %d, %Y"
        )

        recovery_trend = latest_assessment.trend

    else:

        average_score = None
        best_score = None
        latest_date = "No assessments yet"
        recovery_trend = "N/A"

    return render_template(
        "patient_profile.html",
        patient=patient,
        assessments=assessments,
        assessment_count=assessment_count,
        average_score=average_score,
        best_score=best_score,
        latest_date=latest_date,
        recovery_trend=recovery_trend
    )

# ----------------------------------------------------------
# Start Assessment
# ----------------------------------------------------------

@app.route("/assessment/<int:assessment_id>/delete", methods=["POST"])
def delete_assessment(assessment_id):

    assessment = AssessmentRecord.query.get_or_404(assessment_id)

    patient_id = assessment.patient_id

    db.session.delete(assessment)
    db.session.commit()

    return redirect(
        url_for(
            "patient_profile",
            patient_id=patient_id
        )
    )

@app.route("/patients/<int:patient_id>/delete", methods=["POST"])
def delete_patient(patient_id):

    patient = Patient.query.get_or_404(patient_id)

    db.session.delete(patient)
    db.session.commit()

    return redirect(
        url_for("patient_registry")
    )
    

@app.route("/assessment", methods=["POST"])
def start_assessment():

    global session
    global completed_session

    exercise_name = request.form["exercise"]
    patient_id = request.form.get("patient_id", type=int)

    print("Start assessment patient_id =", patient_id)

    exercise_type = ExerciseType[exercise_name]

    # Create the session
    session = AssessmentSession(
        exercise=exercise_type,
        profile=get_exercise_profile(exercise_type),
        exercise_state=ExerciseState(),
        patient_id=patient_id,
    )

    # <-- ADD THESE LINES RIGHT HERE
    print("START:", id(session), session.__dict__)

    # Reset runtime state
    session_manager.clear()
    biomechanics.reset_rep_metrics()

    completed_session = None

    return redirect(
        url_for(
            "assessment_session",
            patient_id=patient_id
        )
    )

# ----------------------------------------------------------
# Live Assessment Page
# ----------------------------------------------------------

@app.route("/assessment")
def assessment_session():
    """
    Displays the live assessment interface.
    """

    patient_id = request.args.get("patient_id", type=int)

    print(f"Patient ID: {patient_id}")

    return render_template(
        "session.html",
        patient_id=patient_id,
        session=session,
    )


# ----------------------------------------------------------
# Finish Assessment
# ----------------------------------------------------------

@app.route("/finish", methods=["POST"])
def finish_assessment():

    global session
    global completed_session

    if session is None:
        return redirect(url_for("selection"))

    latest = session_manager.latest_result

    completed_session = {

        # Preserve the patient so subsequent actions
        # (Save or Discard) still know who this
        # assessment belongs to.
        "patient_id":
            session.patient_id,

        "exercise":
            session.profile.display_name,

        "repetitions":
            session_manager.repetition_count,

        "average_score":
            round(
                session_manager.average_score,
                1,
            ),

        "best_score":
            round(
                session_manager.best_score,
                1,
            ),

        "worst_score":
            round(
                session_manager.worst_score,
                1,
            ),

        "trend":
            session_manager.trend,

        "feedback":
            latest.feedback if latest else [],

    }

    # End the active assessment.
    return redirect(
        url_for("report")
    )

# ----------------------------------------------------------
# Assessment Report
# ----------------------------------------------------------

@app.route("/report")
def report():

    global completed_session
    global session

    if completed_session is None:
        return redirect(
            url_for("selection")
        )

    patient = None

    if (
        completed_session is not None
        and completed_session.get("patient_id") is not None
    ):
        patient = Patient.query.get(
            completed_session["patient_id"]
        )
    print("REPORT completed_session:", completed_session)
    print("REPORT patient:", patient)

    return render_template(
        "report.html",
        report=completed_session,
        patient=patient,
    )
@app.route("/save_assessment", methods=["POST"])
def save_assessment():

    global session
    global completed_session

    print("\n========== SAVE ASSESSMENT ==========")
    print("session:", session)
    print(
        "session.patient_id:",
        getattr(session, "patient_id", None)
    )
    print("completed_session:", completed_session)
    print("=====================================\n")

    if session is None or completed_session is None:
        return redirect(url_for("selection"))

    record = AssessmentRecord(
        patient_id=completed_session["patient_id"],
        exercise=completed_session["exercise"],
        repetitions=completed_session["repetitions"],
        average_score=completed_session["average_score"],
        best_score=completed_session["best_score"],
        worst_score=completed_session["worst_score"],
        trend=completed_session["trend"],
        feedback=json.dumps(
            completed_session.get("feedback", [])
        ),
        notes=""
    )

    db.session.add(record)
    db.session.commit()

    patient_id = completed_session["patient_id"]

    # Clear runtime state AFTER saving
    session = None
    completed_session = None

    return redirect(
        url_for(
            "patient_profile",
            patient_id=patient_id
        )
    )
# ----------------------------------------------------------
# Video Feed
# ----------------------------------------------------------

@app.route("/video_feed")
def video_feed():
    """
    Streams the live annotated camera feed.
    """

    return Response(
        generate_frames(),
        mimetype="multipart/x-mixed-replace; boundary=frame",
    )


# ----------------------------------------------------------
# Live Session Data
# ----------------------------------------------------------

@app.route("/session")
def session_data():
    """
    Returns the current rehabilitation assessment state.
    """

    # --------------------------------------------------
    # No Active Assessment
    # --------------------------------------------------

    if session is None:

        return jsonify({

            "exercise": "",
            "tracking": False,
            "repetitions": 0,

            "joint_angles": {},

            "range_of_motion": "--",

            "current_score": 0,
            "rom_score": 0,
            "feedback": [],

            "average_score": 0,
            "best_score": 0,
            "worst_score": 0,

            "trend": "No Assessment Started",

        })

    # --------------------------------------------------
    # Active Assessment
    # --------------------------------------------------

    latest = session_manager.latest_result
    metrics = getattr(
    session,
    "movement_metrics",
    None,
)

    if metrics is None:

        return jsonify({

            "exercise":
                session.profile.display_name,

            "tracking": False,

            "repetitions": 0,

            "joint_angles": {},

            "range_of_motion": "--",

            "current_score": 0,
         "rom_score": 0,

            "feedback": [],

            "average_score": 0,
            "best_score": 0,
         "worst_score": 0,

            "trend":
                "Initializing",

        })

    joint_lookup = {

        "Left Elbow":
            metrics.elbow_angle_left,

        "Right Elbow":
            getattr(
                metrics,
                "elbow_angle_right",
                None,
            ),

        "Left Shoulder":
            getattr(
                metrics,
                "shoulder_angle_left",
                None,
            ),

        "Right Shoulder":
            getattr(
                metrics,
                "shoulder_angle_right",
                None,
            ),

    }

    joint_angles = {}

    for joint in session.profile.tracked_joints:

        value = joint_lookup.get(joint)

        joint_angles[joint] = (
            round(value, 1)
            if value is not None
            else "--"
        )

    return jsonify({

        # ------------------------------------------
        # Session Information
        # ------------------------------------------

        "exercise":
            session.profile.display_name,

        "tracking":
            getattr(
                session.exercise_state,
                "active",
                False,
            ),

        "repetitions":
            session_manager.repetition_count,

        # ------------------------------------------
        # Live Metrics
        # ------------------------------------------

        "joint_angles":
            joint_angles,

        "range_of_motion":
            round(
                metrics.range_of_motion,
                1,
            ),

        # ------------------------------------------
        # Current Assessment
        # ------------------------------------------

        "current_score":
            round(
                latest.overall_score,
                1,
            )
            if latest else 0,

        "rom_score":
            round(
                latest.rom_score,
                1,
            )
            if latest else 0,

        "feedback":
            latest.feedback
            if latest
            else [],

        # ------------------------------------------
        # Aggregate Statistics
        # ------------------------------------------

        "average_score":
            round(
                session_manager.average_score,
                1,
            ),

        "best_score":
            round(
                session_manager.best_score,
                1,
            ),

        "worst_score":
            round(
                session_manager.worst_score,
                1,
            ),

        "trend":
            session_manager.trend,

    })


# ----------------------------------------------------------
# Exercise Information
# ----------------------------------------------------------

@app.route("/exercise_info/<exercise_name>")
def exercise_info(exercise_name):
    """
    Returns metadata describing a rehabilitation exercise.
    """

    exercise_type = ExerciseType[exercise_name]

    profile = get_exercise_profile(
        exercise_type,
    )
    
    anatomy = anatomy_profile_for(
    exercise_type,
    )

    return jsonify({

        "display_name":
            profile.display_name,

        "description":
            profile.description,

        "primary_joint":
            profile.primary_joint,

        "movement_plane":
            profile.movement_plane,

        "target_side":
            profile.target_side,
        
        "anatomy": {
            "image":
                anatomy.image,
                
            "primary":
                [m.value for m in anatomy.muscles.primary],
                
            "secondary":
                [m.value for m in anatomy.muscles.secondary],
            
            
        }

    })

# ==========================================================
# Video Processing
# ==========================================================

def generate_frames():

    while True:

        try:

            # --------------------------------------------------
            # Capture Frame
            # --------------------------------------------------

            frame = vision.get_frame()

            if frame is None:
                continue

            # --------------------------------------------------
            # Pose Estimation
            # --------------------------------------------------

            annotated_frame, skeleton = pose.process(
                frame
            )

            # --------------------------------------------------
            # Biomechanics
            # --------------------------------------------------

            metrics = biomechanics.calculate_metrics(
                skeleton
            )

            # --------------------------------------------------
            # Idle Mode
            # --------------------------------------------------

            if session is None:

                exercise_state = None

            # --------------------------------------------------
            # Active Assessment
            # --------------------------------------------------

            else:

                session.movement_metrics = metrics

                exercise_state = exercise.analyze(
                    session.profile,
                    metrics,
                )

                session.exercise_state = exercise_state

                # ----------------------------------------------
                # Rep Completed
                # ----------------------------------------------

                if exercise_state.rep_completed:

                    session.assessment_result = assessment.analyze(
                        session.profile,
                        metrics,
                        exercise_state,
                    )

                    print("\n========== REP COMPLETE ==========")

                    print("Measured Metrics")
                    print(f"ROM: {fmt(metrics.range_of_motion)}")
                    print(f"Peak Flexion: {fmt(metrics.peak_flexion)}")
                    print(f"Peak Extension: {fmt(metrics.peak_extension)}")
                    print(f"Rep Duration: {fmt(metrics.rep_duration)}")
                    print(f"Trunk Lean: {fmt(metrics.trunk_lean)}")

                    print("\nScores")
                    print(f"ROM Score: {fmt(session.assessment_result.rom_score,1)}")
                    print(f"Tempo Score: {fmt(session.assessment_result.tempo_score,1)}")
                    print(f"Completion Score: {fmt(session.assessment_result.completion_score,1)}")
                    print(f"Overall Score: {fmt(session.assessment_result.overall_score,1)}")

                    print("==================================\n")

                    session_manager.add_result(
                        session.assessment_result
                    )

                    biomechanics.reset_rep_metrics()

            # --------------------------------------------------
            # Overlay Rendering
            # --------------------------------------------------

            annotated_frame = overlay.draw(
                annotated_frame,
                skeleton,
                metrics,
                exercise_state,
                tracking=skeleton is not None,
            )

            # --------------------------------------------------
            # Resize Frame
            # --------------------------------------------------

            annotated_frame = cv2.resize(
                annotated_frame,
                (
                    640,
                    480,
                ),
            )

            # --------------------------------------------------
            # JPEG Encoding
            # --------------------------------------------------

            success, buffer = cv2.imencode(
                ".jpg",
                annotated_frame,
                [
                    int(cv2.IMWRITE_JPEG_QUALITY),
                    80,
                ],
            )

            if not success:
                continue

            # --------------------------------------------------
            # Stream Frame
            # --------------------------------------------------

            yield (
                b"--frame\r\n"
                b"Content-Type: image/jpeg\r\n\r\n"
                + buffer.tobytes()
                + b"\r\n"
            )

        # ------------------------------------------------------
        # Stream Error Recovery
        # ------------------------------------------------------

        except Exception:

            import traceback

            print("\n========== STREAM ERROR ==========")
            traceback.print_exc()
            print("==================================\n")

            continue

@app.route("/discard", methods=["POST"])
def discard_assessment():

    global session
    global completed_session

    session = None
    completed_session = None

    return redirect(url_for("home"))

# ==========================================================
# Application Entry
# ==========================================================

if __name__ == "__main__":

    try:

        app.run(
            host="0.0.0.0",
            port=5000,
            debug=False,
        )

    finally:

        vision.stop()
        pose.close()

with app.app_context():
    db.create_all()