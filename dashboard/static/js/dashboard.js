function dashboardPollingState() {
    if (!window.__revalivDashboardPollingState) {
        window.__revalivDashboardPollingState = {
            active: false,
            generation: 0,
            timer: null,
            controller: null,
        };
    }
    return window.__revalivDashboardPollingState;
}

async function updateDashboard(signal) {

    try {

        const sessionContainer = document.querySelector(
            ".session-container[data-workout-mode]",
        );
        const workoutMode = sessionContainer?.dataset.workoutMode === "true";
        const response = await fetch(
            workoutMode ? "/workout/session" : "/session",
            {
            cache: "no-store",
            signal,
            },
        );
        if (!response.ok) {
            throw new Error(
                `${workoutMode ? "/workout/session" : "/session"} request failed (${response.status})`,
            );
        }
        const data = await response.json();
        if (workoutMode) {
            updateWorkoutDashboard(data);
            return;
        }

        // ==========================================
        // Assessment Session
        // ==========================================

        document.getElementById("exercise-name").textContent =
            data.exercise;
        const readinessOutput =
            document.getElementById("perception-readiness");
        const readiness = data.perception_readiness || {};
        if (readinessOutput) {
            readinessOutput.textContent = readiness.message || "Checking pose.";
            readinessOutput.dataset.state = readiness.state || "poor_quality";
            readinessOutput.setAttribute("aria-label", readiness.label || "Pose status");
        }

        const calibrationOutput =
            document.getElementById("perception-calibration");
        if (calibrationOutput && data.perception_calibration) {
            calibrationOutput.textContent =
                data.perception_calibration.message;
            calibrationOutput.dataset.stage =
                data.perception_calibration.stage;
        }

        const trackingStatus =
            document.getElementById("tracking-status");
        const isTracking = Boolean(readiness.tracking);
        trackingStatus.textContent = isTracking
            ? "Active"
            : readiness.state === "calibration_required"
                ? "Calibrating"
                : readiness.state === "identity_ambiguous"
                    ? "Checking identity"
                    : "Waiting";

        trackingStatus.classList.remove(
            "status-success",
            "status-warning",
            "status-danger",
        );

        trackingStatus.classList.add(
            isTracking ? "status-success"
                : readiness.state === "no_person" || readiness.state === "identity_ambiguous"
                    ? "status-warning"
                    : "status-danger",
        );

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

        if (error.name !== "AbortError") {
            console.error("Failed to update dashboard:", error);
        }

    }

}

function workoutExerciseLabel(exercise) {
    if (!exercise) return "No active exercise";
    return `${exercise.side} ${exercise.name}`.toUpperCase();
}

function renderWorkoutResultList(container, results) {
    container.replaceChildren();
    for (const result of results) {
        const item = document.createElement("li");
        const title = document.createElement("strong");
        title.textContent = `${result.side} ${result.exercise} — `
            + `${result.completed_repetitions} / ${result.target_repetitions}`;
        item.appendChild(title);
        if (result.average_score !== null) {
            const score = document.createElement("span");
            score.textContent = `Average score ${Number(result.average_score).toFixed(1)}%`;
            item.appendChild(score);
        }
        container.appendChild(item);
    }
}

function updateWorkoutDashboard(data) {
    const current = data.current_exercise;
    const completed = data.completed_exercises || [];
    const state = data.status || "unknown";
    const stateLabels = {
        calibrating: "Calibrating",
        ready: "Ready",
        exercising: "Exercising",
        session_complete: "Workout Complete",
        cancelled: "Cancelled",
    };
    const name = workoutExerciseLabel(current);
    document.getElementById("exercise-name").textContent =
        current ? `${current.side} ${current.name}` : "Workout";
    document.getElementById("workout-current-name").textContent = name;
    document.getElementById("workout-exercise-position").textContent =
        current
            ? `Exercise ${data.current_exercise_index + 1} of ${data.total_exercises}`
            : `${data.total_exercises} exercises completed`;
    document.getElementById("workout-rep-progress").textContent =
        current
            ? `${data.completed_repetitions} / ${current.target_repetitions}`
            : `${completed.length} / ${data.total_exercises} exercises`;
    document.getElementById("workout-exercise-phase").textContent =
        data.exercise_phase || "—";
    const stateBadge = document.getElementById("workout-session-state");
    stateBadge.textContent = stateLabels[state] || state.replaceAll("_", " ");
    stateBadge.dataset.state = state;

    const calibration = data.calibration || {};
    const calibrationMessage = document.getElementById("workout-calibration-message");
    calibrationMessage.textContent = state === "calibrating"
        ? calibration.message || "Calibration required before exercise."
        : state === "cancelled"
            ? "Workout cancelled."
            : state === "session_complete"
                ? "All prescribed exercises are complete."
                : state === "exercising"
                    ? "Calibration complete."
                    : state === "ready"
                        ? "Ready to begin movement."
                        : "Preparing workout.";

    const progress = document.getElementById("workout-calibration-progress");
    const progressFill = document.getElementById("workout-calibration-progress-fill");
    const calibrationStage = calibration.stage;
    const matching = Number(calibration.matching_frames || 0);
    const required = Math.max(1, Number(calibration.required_frames || 1));
    const showProgress = state === "calibrating"
        && calibrationStage === "confirming";
    progress.hidden = !showProgress;
    const percent = Math.min(100, Math.round((matching / required) * 100));
    progress.setAttribute("aria-valuenow", String(percent));
    progressFill.style.width = `${percent}%`;

    const transition = document.getElementById("workout-transition");
    const justCompleted = state === "calibrating" && completed.length > 0 && current;
    transition.hidden = !justCompleted;
    if (justCompleted) {
        const previous = completed[completed.length - 1];
        document.getElementById("workout-transition-title").textContent =
            `✓ ${workoutExerciseLabel({ name: previous.exercise, side: previous.side })} COMPLETE`;
        document.getElementById("workout-transition-next").textContent =
            `Next: ${name} · Calibration required`;
    }

    const completePanel = document.getElementById("workout-completion");
    completePanel.hidden = state !== "session_complete";
    if (state === "session_complete") {
        renderWorkoutResultList(
            document.getElementById("workout-completion-list"),
            completed,
        );
    }

    const resultSection = document.getElementById("workout-results");
    resultSection.hidden = completed.length === 0;
    if (completed.length > 0) {
        renderWorkoutResultList(
            document.getElementById("workout-results-list"),
            completed,
        );
    }

    document.getElementById("workout-cancel").hidden =
        state === "session_complete" || state === "cancelled";
    document.getElementById("workout-return-setup").hidden =
        state !== "session_complete" && state !== "cancelled";
    const returnHome = document.getElementById("workout-return-home");
    if (returnHome) {
        returnHome.hidden = state !== "session_complete" && state !== "cancelled";
    }

    const actionMessage = document.getElementById("workout-action-message");
    if (state !== "cancelled") actionMessage.textContent = "";
    document.getElementById("rep-count").textContent =
        current
            ? `${data.completed_repetitions} / ${current.target_repetitions}`
            : `${completed.length} / ${data.total_exercises}`;

    const latestResult = completed.at(-1)?.repetition_results?.at(-1);
    if (latestResult) {
        document.getElementById("current-score").textContent =
            `${Number(latestResult.overall_score).toFixed(1)}%`;
        document.getElementById("average-score").textContent =
            `${Number(completed.at(-1).average_score).toFixed(1)}%`;
        document.getElementById("best-score").textContent =
            `${Number(completed.at(-1).best_score).toFixed(1)}%`;
        document.getElementById("feedback-list").replaceChildren(
            ...latestResult.feedback.map(feedback => {
                const item = document.createElement("li");
                item.textContent = feedback;
                return item;
            }),
        );
    }
    document.getElementById("trend").textContent = stateLabels[state] || state;

    const readinessOutput = document.getElementById("perception-readiness");
    readinessOutput.textContent = calibrationMessage.textContent;
    readinessOutput.dataset.state = state === "exercising" || state === "ready"
        ? "ready"
        : state === "calibrating"
            ? "calibration_required"
            : "poor_quality";
    const calibrationOutput = document.getElementById("perception-calibration");
    calibrationOutput.textContent = calibration.message || calibrationMessage.textContent;
    calibrationOutput.dataset.stage = calibrationStage || state;

    const trackingStatus = document.getElementById("tracking-status");
    trackingStatus.textContent = stateLabels[state] || "Waiting";
    trackingStatus.classList.remove("status-success", "status-warning", "status-danger");
    trackingStatus.classList.add(
        state === "exercising" || state === "ready"
            ? "status-success"
            : state === "calibrating"
                ? "status-warning"
                : "status-danger",
    );
}

async function cancelWorkout() {
    const button = document.getElementById("workout-cancel");
    const message = document.getElementById("workout-action-message");
    button.disabled = true;
    message.textContent = "Cancelling workout…";
    try {
        const response = await fetch("/workout/cancel", {
            method: "POST",
            headers: {
                "X-CSRF-Token": document.querySelector(
                    'meta[name="csrf-token"]',
                )?.content || "",
            },
        });
        const data = await response.json();
        if (!response.ok) {
            throw new Error(data.error || `Workout cancellation failed (${response.status})`);
        }
        updateWorkoutDashboard(data);
        message.textContent = "Workout cancelled. Completed exercise results are preserved.";
    } catch (error) {
        message.textContent = error.message;
    } finally {
        button.disabled = false;
    }
}

function stopDashboardPolling() {
    const state = dashboardPollingState();
    state.active = false;
    state.generation += 1;
    if (state.timer !== null) {
        clearTimeout(state.timer);
        state.timer = null;
    }
    state.controller?.abort();
    state.controller = null;
}

function startDashboardPolling() {
    const state = dashboardPollingState();
    if (state.active || !document.getElementById("video-feed")) return;

    state.active = true;
    const generation = ++state.generation;
    const poll = async () => {
        if (
            !state.active
            || state.generation !== generation
            || state.controller !== null
        ) return;
        const startedAt = performance.now();
        const controller = new AbortController();
        state.controller = controller;
        await updateDashboard(controller.signal);
        if (state.controller === controller) state.controller = null;

        if (state.active && state.generation === generation) {
            const delay = Math.max(0, 200 - (performance.now() - startedAt));
            state.timer = setTimeout(() => {
                state.timer = null;
                void poll();
            }, delay);
        }
    };
    void poll();
}

function findBytes(haystack, needle, start = 0) {
    for (let i = start; i <= haystack.length - needle.length; i += 1) {
        let matched = true;
        for (let j = 0; j < needle.length; j += 1) {
            if (haystack[i + j] !== needle[j]) {
                matched = false;
                break;
            }
        }
        if (matched) return i;
    }
    return -1;
}

function joinBytes(first, second) {
    const joined = new Uint8Array(first.length + second.length);
    joined.set(first);
    joined.set(second, first.length);
    return joined;
}

async function consumeMjpeg(response, onFrame) {
    const reader = response.body.getReader();
    const boundary = new TextEncoder().encode("--frame\r\n");
    const headerSeparator = new TextEncoder().encode("\r\n\r\n");
    let buffer = new Uint8Array(0);

    while (true) {
        const { value, done } = await reader.read();
        if (done) return;
        buffer = joinBytes(buffer, value);

        while (true) {
            const boundaryIndex = findBytes(buffer, boundary);
            if (boundaryIndex < 0) {
                buffer = buffer.slice(Math.max(0, buffer.length - boundary.length + 1));
                break;
            }
            if (boundaryIndex > 0) buffer = buffer.slice(boundaryIndex);

            const headersStart = boundary.length;
            const headersEnd = findBytes(buffer, headerSeparator, headersStart);
            if (headersEnd < 0) break;

            const headers = new TextDecoder().decode(
                buffer.slice(headersStart, headersEnd),
            );
            const contentLength = Number(
                headers.match(/^Content-Length:\s*(\d+)\s*$/im)?.[1],
            );
            if (!Number.isSafeInteger(contentLength) || contentLength < 0) {
                throw new Error("MJPEG frame is missing a valid Content-Length");
            }

            const frameStart = headersEnd + headerSeparator.length;
            const frameEnd = frameStart + contentLength;
            if (buffer.length < frameEnd + 2) break;

            const metadata = Object.fromEntries(
                headers.split("\r\n").map((line) => {
                    const separator = line.indexOf(":");
                    return separator < 0
                        ? ["", ""]
                        : [
                            line.slice(0, separator).trim().toLowerCase(),
                            line.slice(separator + 1).trim(),
                        ];
                }),
            );
            onFrame(
                buffer.slice(frameStart, frameEnd),
                metadata,
                performance.now(),
            );
            buffer = buffer.slice(frameEnd + 2);
        }
    }
}

async function startVideoDiagnostics() {
    const image = document.getElementById("video-feed");
    if (!image) return;

    if (window.__revalivVideoStreamController) return;
    const controller = new AbortController();
    window.__revalivVideoStreamController = controller;

    const diagnosticOutput = document.getElementById("video-diagnostics");
    let currentObjectUrl = null;
    let pendingFrame = null;
    let displayLoopRunning = false;
    let latestReceivedSequence = null;
    let lastDisplayedSequence = null;
    let lastArrivalAt = null;
    let arrivalIntervals = [];
    let receivedSequenceGaps = 0;
    let outOfOrderFrames = 0;
    let replacedBeforeDisplay = 0;
    let latestServerSequence = null;
    let activeStreamConsumers = null;
    let latestServerFrameAgeMs = null;
    let latestProcessingAgeMs = null;
    let latestReceiveToDisplayMs = null;
    let latestArrivalFps = 0;
    let lastDiagnosticUpdate = 0;
    let serverPollingTimer = null;
    let diagnosticsEnabled = false;

    const showDiagnostics = (text) => {
        if (!diagnosticOutput) return;
        diagnosticOutput.hidden = false;
        diagnosticOutput.textContent = text;
    };

    const renderDiagnosticText = () => {
        if (!diagnosticOutput) return;
        const serverLag = latestServerSequence === null || lastDisplayedSequence === null
            ? "--"
            : Math.max(0, latestServerSequence - lastDisplayedSequence);
        showDiagnostics(
            `Frame ${lastDisplayedSequence ?? "--"} · server latest ${latestServerSequence ?? "--"} `
            + `· lag ${serverLag} frames · receive→display ${latestReceiveToDisplayMs?.toFixed(0) ?? "--"} ms `
            + `· server processing age ${latestProcessingAgeMs?.toFixed(0) ?? "--"} ms `
            + `· latest capture age ${latestServerFrameAgeMs?.toFixed(0) ?? "--"} ms `
            + `· receive ${latestArrivalFps.toFixed(1)} FPS · gaps ${receivedSequenceGaps} `
            + `· reordered ${outOfOrderFrames} · coalesced ${replacedBeforeDisplay} `
            + `· streams ${activeStreamConsumers ?? "--"}`,
        );
    };

    const updateDiagnosticText = (frameMetadata, receivedAt, displayedAt) => {
        latestProcessingAgeMs = Number(
            frameMetadata["x-revaliv-processing-age-ms"],
        );
        latestReceiveToDisplayMs = displayedAt - receivedAt;
        latestArrivalFps = arrivalIntervals.length
            ? 1000 / (
                arrivalIntervals.reduce((total, interval) => total + interval, 0)
                / arrivalIntervals.length
            )
            : 0;
        renderDiagnosticText();
    };

    const pollLatestServerFrame = async () => {
        if (controller.signal.aborted) return;
        try {
            const response = await fetch("/video_status", {
                cache: "no-store",
                signal: controller.signal,
            });
            if (response.ok) {
                const state = await response.json();
                latestServerSequence = state.sequence;
                activeStreamConsumers = state.active_consumers;
                latestServerFrameAgeMs = state.server_frame_age_ms;
                if (diagnosticOutput && !diagnosticOutput.hidden) {
                    renderDiagnosticText();
                }
            }
        } catch (error) {
            if (error.name !== "AbortError") {
                console.warn("Unable to read video diagnostics:", error);
            }
        } finally {
            if (!controller.signal.aborted) {
                serverPollingTimer = setTimeout(() => {
                    if (window.__revalivVideoStatusTimer === serverPollingTimer) {
                        window.__revalivVideoStatusTimer = null;
                    }
                    void pollLatestServerFrame();
                }, 1000);
                window.__revalivVideoStatusTimer = serverPollingTimer;
            }
        }
    };

    const drainPendingFrames = async () => {
        if (displayLoopRunning) return;
        displayLoopRunning = true;
        try {
            while (pendingFrame !== null) {
                const frame = pendingFrame;
                pendingFrame = null;
                const objectUrl = URL.createObjectURL(
                    new Blob([frame.jpegBytes], { type: "image/jpeg" }),
                );
                const loaded = new Promise((resolve, reject) => {
                    image.onload = resolve;
                    image.onerror = () => reject(new Error("MJPEG frame decode failed"));
                });
                image.src = objectUrl;
                await loaded;
                await new Promise((resolve) => {
                    requestAnimationFrame(() => requestAnimationFrame(resolve));
                });
                if (currentObjectUrl !== null) {
                    URL.revokeObjectURL(currentObjectUrl);
                }
                currentObjectUrl = objectUrl;
                lastDisplayedSequence = frame.sequence;

                if (diagnosticsEnabled && performance.now() - lastDiagnosticUpdate >= 500) {
                    updateDiagnosticText(frame.metadata, frame.receivedAt, performance.now());
                    lastDiagnosticUpdate = performance.now();
                }
            }
        } catch (error) {
            if (!controller.signal.aborted) {
                console.error("Video frame display failed:", error);
            }
        } finally {
            displayLoopRunning = false;
            if (pendingFrame !== null && !controller.signal.aborted) {
                void drainPendingFrames();
            }
        }
    };

    try {
        const response = await fetch("/video_feed", {
            cache: "no-store",
            signal: controller.signal,
        });
        if (!response.ok || !response.body) {
            throw new Error(`Video stream request failed (${response.status})`);
        }

        diagnosticsEnabled =
            response.headers.get("X-Revaliv-Perf-Diagnostics") === "1";
        if (diagnosticsEnabled) {
            if (diagnosticOutput) diagnosticOutput.hidden = false;
            void pollLatestServerFrame();
        }

        await consumeMjpeg(response, (jpegBytes, metadata, receivedAt) => {
            const sequence = Number(metadata["x-revaliv-frame-sequence"]);
            if (!Number.isSafeInteger(sequence)) return;
            if (latestReceivedSequence !== null) {
                if (sequence <= latestReceivedSequence) outOfOrderFrames += 1;
                if (sequence > latestReceivedSequence + 1) {
                    receivedSequenceGaps += sequence - latestReceivedSequence - 1;
                }
            }
            latestReceivedSequence = latestReceivedSequence === null
                ? sequence
                : Math.max(latestReceivedSequence, sequence);
            if (lastArrivalAt !== null) {
                arrivalIntervals.push(receivedAt - lastArrivalAt);
                arrivalIntervals = arrivalIntervals.slice(-30);
            }
            lastArrivalAt = receivedAt;

            if (pendingFrame !== null) replacedBeforeDisplay += 1;
            pendingFrame = { jpegBytes, metadata, receivedAt, sequence };
            void drainPendingFrames();
        });
    } catch (error) {
        if (!controller.signal.aborted) {
            showDiagnostics(`Video stream error: ${error.message}`);
            console.error("Video stream failed:", error);
        }
    } finally {
        if (serverPollingTimer !== null) clearTimeout(serverPollingTimer);
        if (window.__revalivVideoStatusTimer === serverPollingTimer) {
            window.__revalivVideoStatusTimer = null;
        }
        if (currentObjectUrl !== null) URL.revokeObjectURL(currentObjectUrl);
        if (window.__revalivVideoStreamController === controller) {
            window.__revalivVideoStreamController = null;
        }
    }
}

if (!window.__revalivVideoStreamInitialized) {
    window.__revalivVideoStreamInitialized = true;
    document.getElementById("workout-cancel")?.addEventListener(
        "click",
        () => void cancelWorkout(),
    );
    document.getElementById("workout-view-results")?.addEventListener(
        "click",
        () => {
            const results = document.getElementById("workout-results");
            results?.scrollIntoView({ behavior: "smooth", block: "start" });
            document.getElementById("workout-return-home")?.focus();
        },
    );
    window.addEventListener("beforeunload", (event) => {
        const container = document.querySelector(".session-container[data-workout-mode]");
        if (!container) return;
        if (window.__revalivAssessmentExitConfirmed) return;
        const complete = document.getElementById("workout-session-state")?.dataset.state
            === "session_complete";
        const workoutMode = container.dataset.workoutMode === "true";
        if (!complete && (workoutMode || document.querySelector(".finish-assessment-button"))) {
            event.preventDefault();
            event.returnValue = "";
        }
    });
    document.querySelectorAll(
        'form[action$="/finish"], form[action$="/discard"]',
    ).forEach((form) => {
        form.addEventListener("submit", () => {
            window.__revalivAssessmentExitConfirmed = true;
        });
    });
    window.addEventListener("pagehide", () => {
        stopDashboardPolling();
        if (window.__revalivVideoStatusTimer !== null) {
            clearTimeout(window.__revalivVideoStatusTimer);
            window.__revalivVideoStatusTimer = null;
        }
        window.__revalivVideoStreamController?.abort();
        window.__revalivVideoStreamController = null;
    });
    window.addEventListener("pageshow", () => {
        startDashboardPolling();
        void startVideoDiagnostics();
    });
    startDashboardPolling();
    void startVideoDiagnostics();
}