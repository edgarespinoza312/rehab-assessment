async function updateDashboard() {

    try {

        const response = await fetch("/session");
        const data = await response.json();

        // ==========================================
        // Assessment Session
        // ==========================================

        document.getElementById("exercise-name").textContent =
            data.exercise;

        document.getElementById("tracking-status").textContent =
            data.tracking ? "Active" : "Lost";

        document.getElementById("rep-count").textContent =
            data.repetitions;

        // ==========================================
        // Live Metrics
        // ==========================================

        const jointContainer =
            document.getElementById("joint-angles");

        jointContainer.innerHTML = "";

        if (Object.keys(data.joint_angles).length === 0) {

            const waiting = document.createElement("p");
            waiting.textContent = "Waiting for assessment...";
            jointContainer.appendChild(waiting);

        }

        else {

            for (const [joint, angle] of Object.entries(data.joint_angles)) {

                const label = document.createElement("p");
                label.textContent = joint;

                const value = document.createElement("p");
                value.textContent = `${angle}°`;

                jointContainer.appendChild(label);
                jointContainer.appendChild(value);

            }

        }

        document.getElementById("rom").textContent =
            `${data.range_of_motion}°`;

        // ==========================================
        // Session Summary
        // ==========================================

        document.getElementById("average-score").textContent =
            `${data.average_score}%`;

        document.getElementById("current-score").textContent =
            `${data.current_score}%`;

        document.getElementById("best-score").textContent =
            `${data.best_score}%`;

        document.getElementById("trend").textContent =
            data.trend;

        // ==========================================
        // Clinical Feedback
        // ==========================================

        const feedbackList =
            document.getElementById("feedback-list");

        feedbackList.innerHTML = "";

        if (data.feedback.length === 0) {

            const li = document.createElement("li");
            li.textContent = "Waiting for first repetition...";
            feedbackList.appendChild(li);

        }

        else {

            data.feedback.forEach(item => {

                const li = document.createElement("li");
                li.textContent = item;

                feedbackList.appendChild(li);

            });

        }

    }

    catch (error) {

        console.error(
            "Failed to update dashboard:",
            error,
        );

    }

}

setInterval(
    updateDashboard,
    200,
);

setInterval(
    updateDashboard,
    200,
);

updateDashboard();