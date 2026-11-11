// ==========================================================
// Exercise Information
// ==========================================================

async function updateExerciseInformation(exercise) {

    try {

        const response = await fetch(
            `/exercise_info/${exercise}`
        );

        if (!response.ok) {
            throw new Error(
                "Failed to fetch exercise information."
            );
        }

        const data = await response.json();

        // --------------------------------------------------
        // Exercise Information
        // --------------------------------------------------

        document.getElementById("exercise-name").textContent =
            data.display_name ?? "--";

        document.getElementById("exercise-description").textContent =
            data.description ?? "--";

        document.getElementById("primary-joint").textContent =
            data.primary_joint ?? "--";

        document.getElementById("movement-plane").textContent =
            data.movement_plane ?? "--";

        document.getElementById("target-side").textContent =
            data.target_side ?? "--";

        // --------------------------------------------------
        // Anatomy Image
        // --------------------------------------------------

        const muscleImage =
            document.getElementById("muscle-model");

        if (muscleImage) {

            if (data.anatomy?.image) {

                muscleImage.src =
                    `/static/images/anatomy/${data.anatomy.image}`;

                muscleImage.alt =
                    `${data.display_name} Anatomy`;

            }

            else {

                muscleImage.src =
                    "/static/images/anatomy/default.png";

                muscleImage.alt =
                    "No anatomy available";

            }

        }

        // --------------------------------------------------
        // Primary Muscle List
        // --------------------------------------------------

        const primaryList =
            document.getElementById("primary-muscles");

        if (primaryList) {

            primaryList.innerHTML = "";

            for (const muscle of data.anatomy?.primary ?? []) {

                const item =
                    document.createElement("li");

                item.textContent =
                    muscle
                        .replaceAll("_", " ")
                        .toLowerCase()
                        .replace(/\b\w/g, c => c.toUpperCase());

                primaryList.appendChild(item);

            }

        }

        // --------------------------------------------------
        // Secondary Muscle List
        // --------------------------------------------------

        const secondaryList =
            document.getElementById("secondary-muscles");

        if (secondaryList) {

            secondaryList.innerHTML = "";

            for (const muscle of data.anatomy?.secondary ?? []) {

                const item =
                    document.createElement("li");

                item.textContent =
                    muscle
                        .replaceAll("_", " ")
                        .toLowerCase()
                        .replace(/\b\w/g, c => c.toUpperCase());

                secondaryList.appendChild(item);

            }

        }

    }

    catch (error) {

        console.error(
            "Exercise information update failed:",
            error,
        );

    }

}

// ==========================================================
// Initialize
// ==========================================================

const exerciseButtons =
    document.querySelectorAll(
        'input[name="exercise"]'
    );

if (exerciseButtons.length > 0) {

    const patientSelector = document.getElementById("workout-patient-selector");
    if (patientSelector?.tagName === "SELECT") {
        patientSelector.addEventListener("change", () => {
            if (!patientSelector.value) return;
            window.location.assign(
                `/selection?patient_id=${encodeURIComponent(patientSelector.value)}`,
            );
        });
    }

    exerciseButtons.forEach(button => {

        button.addEventListener("change", () => {

            updateExerciseInformation(
                button.value
            );

        });

    });

    const selected =
        document.querySelector(
            'input[name="exercise"]:checked'
        );

    if (selected) {

        updateExerciseInformation(
            selected.value
        );

    }

    document.querySelectorAll(".workout-start-button").forEach(button => {
        button.addEventListener("click", async () => {
            const preset = button.closest(".workout-preset");
            const message = document.getElementById("workout-start-message");
            if (!preset || !message) return;

            button.disabled = true;
            message.textContent = "Starting workout and preparing calibration…";
            const patientId = document.getElementById(
                "workout-patient-selector",
            )?.value || preset.dataset.patientId;
            const payload = {
                preset_id: preset.dataset.presetId,
                patient_id: patientId ? Number(patientId) : null,
            };

            try {
                const response = await fetch("/workout/start", {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json",
                        "X-CSRF-Token": document.querySelector(
                            'meta[name="csrf-token"]',
                        )?.content || "",
                    },
                    body: JSON.stringify(payload),
                });
                const result = await response.json();
                if (!response.ok) {
                    throw new Error(result.error || `Workout start failed (${response.status})`);
                }

                const query = patientId
                    ? `?patient_id=${encodeURIComponent(patientId)}`
                    : "";
                window.location.assign(`/assessment${query}`);
            } catch (error) {
                message.textContent = error.message;
                button.disabled = false;
            }
        });
    });

    document.querySelectorAll(".workout-plan-start-button").forEach(button => {
        button.addEventListener("click", async () => {
            const plan = button.closest(".workout-saved-plan");
            const message = document.getElementById("workout-start-message");
            if (!plan || !message) return;

            const patientId = document.getElementById(
                "workout-patient-selector",
            )?.value || plan.dataset.patientId;
            if (!patientId) {
                message.textContent = "Select a patient before starting a workout.";
                return;
            }

            button.disabled = true;
            message.textContent = "Starting saved workout and preparing calibration…";
            try {
                const response = await fetch("/workout/start", {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json",
                        "X-CSRF-Token": document.querySelector(
                            'meta[name="csrf-token"]',
                        )?.content || "",
                    },
                    body: JSON.stringify({
                        plan_id: Number(plan.dataset.planId),
                        patient_id: Number(patientId),
                    }),
                });
                const result = await response.json();
                if (!response.ok) {
                    throw new Error(result.error || `Workout start failed (${response.status})`);
                }
                window.location.assign(
                    `/assessment?patient_id=${encodeURIComponent(patientId)}`,
                );
            } catch (error) {
                message.textContent = error.message;
                button.disabled = false;
            }
        });
    });



    document.querySelectorAll(".workout-plan-review-button").forEach(button => {
        button.addEventListener("click", async () => {
            const plan = button.closest(".workout-saved-plan");
            const rationaleInput = plan?.querySelector(".workout-plan-review-rationale");
            const message = document.getElementById("workout-start-message");
            if (!plan || !rationaleInput || !message) return;

            const rationale = rationaleInput.value.trim();
            if (!rationale) {
                rationaleInput.reportValidity();
                message.textContent = "A review rationale is required.";
                return;
            }

            const decision = button.dataset.decision;
            button.disabled = true;
            message.textContent = "Recording clinician review…";
            try {
                const response = await fetch(
                    `/workout/plans/${encodeURIComponent(plan.dataset.planId)}/review`,
                    {
                        method: "POST",
                        headers: {
                            "Content-Type": "application/json",
                            "X-CSRF-Token": document.querySelector(
                                'meta[name="csrf-token"]',
                            )?.content || "",
                        },
                        body: JSON.stringify({ decision, rationale }),
                    },
                );
                const result = await response.json();
                if (!response.ok) {
                    throw new Error(result.error || `Plan review failed (${response.status})`);
                }
                message.textContent = `Plan review recorded: ${result.approval_status}.`;
                window.location.reload();
            } catch (error) {
                message.textContent = error.message;
                button.disabled = false;
            }
        });
    });

}
