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

}