(() => {
    const configElement = document.getElementById("patient-progress-config");
    const chart = document.getElementById("patient-progress-chart");
    const tooltip = document.getElementById("progress-tooltip");
    const emptyMessage = document.getElementById("progress-empty");
    const status = document.getElementById("progress-status");
    const summary = document.getElementById("progress-summary");
    const latestValue = document.getElementById("progress-latest");
    const previousValue = document.getElementById("progress-previous");
    const changeValue = document.getElementById("progress-change");
    const exerciseSelector = document.getElementById("progress-exercise");
    const sideSelector = document.getElementById("progress-side");
    const metricSelector = document.getElementById("progress-metric");
    const advisoryStatus = document.getElementById("advisory-status");
    const advisoryContent = document.getElementById("advisory-content");
    const advisoryEmpty = document.getElementById("advisory-empty");
    const advisoryExercise = document.getElementById("advisory-exercise");
    const advisorySide = document.getElementById("advisory-side");
    const advisoryCount = document.getElementById("advisory-count");
    const advisoryClassification = document.getElementById("advisory-classification");
    const advisoryClassificationValue = document.getElementById("advisory-classification-value");
    const advisoryReasons = document.getElementById("advisory-reasons");
    const advisoryEvidence = document.getElementById("advisory-evidence");
    const advisoryLimitations = document.getElementById("advisory-limitations");
    const reviewForm = document.getElementById("advisory-review-form");
    const reviewDisposition = document.getElementById("review-disposition");
    const reviewerReference = document.getElementById("reviewer-reference");
    const reviewNote = document.getElementById("review-note");
    const reviewStatus = document.getElementById("review-status");
    const reviewCurrentStatus = document.getElementById("review-current-status");
    const reviewLastReviewed = document.getElementById("review-last-reviewed");
    const reviewHistory = document.getElementById("review-history");

    if (
        !configElement || !chart || !tooltip || !emptyMessage || !status ||
        !summary || !latestValue || !previousValue || !changeValue ||
        !exerciseSelector || !sideSelector || !metricSelector ||
        !advisoryStatus || !advisoryContent || !advisoryEmpty ||
        !advisoryExercise || !advisorySide || !advisoryCount ||
        !advisoryClassification || !advisoryClassificationValue ||
        !advisoryReasons || !advisoryEvidence || !advisoryLimitations ||
        !reviewForm || !reviewDisposition || !reviewerReference ||
        !reviewNote || !reviewStatus || !reviewCurrentStatus ||
        !reviewLastReviewed || !reviewHistory
    ) {
        return;
    }

    const config = JSON.parse(configElement.textContent);
    const namespace = "http://www.w3.org/2000/svg";
    const chartWidth = 800;
    const chartHeight = 390;
    const plot = { left: 64, right: 24, top: 24, bottom: 70 };
    const metricLabels = {
        overall_score: "Overall Score",
        completed_repetitions: "Completed Repetitions",
        resistance_value: "Resistance",
    };
    const classificationLabels = {
        INSUFFICIENT_DATA: "INSUFFICIENT_DATA",
        NO_CHANGE: "NO_CHANGE",
        REVIEW_REQUIRED: "REVIEW_REQUIRED",
        POSSIBLE_PROGRESSION: "POSSIBLE_PROGRESSION",
        POSSIBLE_REGRESSION: "POSSIBLE_REGRESSION",
    };
    let allResults = [];
    let displayedResults = [];
    let advisoryRequestSequence = 0;

    function createSvgElement(name, attributes = {}) {
        const element = document.createElementNS(namespace, name);
        for (const [attribute, value] of Object.entries(attributes)) {
            element.setAttribute(attribute, value);
        }
        return element;
    }

    function addLabel(parent, text, x, y, className, anchor = "middle") {
        const label = createSvgElement("text", {
            x, y, class: className, "text-anchor": anchor,
        });
        label.textContent = text;
        parent.appendChild(label);
        return label;
    }

    function setStatus(message, isError = false) {
        status.textContent = message;
        status.classList.toggle("error", isError);
        status.hidden = !message;
    }

    function positionTooltip(clientX, clientY) {
        const bounds = chart.parentElement.getBoundingClientRect();
        const tooltipWidth = tooltip.offsetWidth;
        const left = Math.max(
            8,
            Math.min(clientX - bounds.left + 12, bounds.width - tooltipWidth - 8),
        );
        const top = Math.max(8, clientY - bounds.top - tooltip.offsetHeight - 12);
        tooltip.style.left = `${left}px`;
        tooltip.style.top = `${top}px`;
    }

    function formatDate(value) {
        const date = new Date(value);
        return Number.isNaN(date.getTime())
            ? value
            : date.toLocaleDateString(undefined, {
                year: "numeric", month: "short", day: "numeric",
            });
    }

    function formatDateTime(value) {
        const date = new Date(value);
        return Number.isNaN(date.getTime())
            ? value
            : date.toLocaleString(undefined, {
                year: "numeric", month: "short", day: "numeric",
                hour: "numeric", minute: "2-digit",
            });
    }

    function formatNumber(value) {
        return Number.isInteger(value) ? `${value}` : value.toFixed(1);
    }

    function formatMetricValue(result, metric) {
        const value = result[metric];
        if (value === null || value === undefined) {
            return null;
        }
        if (metric === "resistance_value") {
            return `${formatNumber(value)} ${result.resistance_unit || ""}`.trim();
        }
        return metric === "overall_score"
            ? `${formatNumber(value)}%`
            : formatNumber(value);
    }

    function showTooltip(point, clientX, clientY) {
        const result = point.result;
        const metric = metricSelector.value;
        const lines = [
            formatDate(result.occurred_at),
            result.exercise_display_name,
            `Side: ${result.side ? result.side[0].toUpperCase() + result.side.slice(1) : "Unknown"}`,
            `${metricLabels[metric]}: ${formatMetricValue(result, metric)}`,
        ];
        if (result.completed_repetitions !== null && result.target_repetitions !== null) {
            lines.push(`Reps: ${result.completed_repetitions} / ${result.target_repetitions}`);
        }
        if (result.resistance_value !== null && result.resistance_value !== undefined) {
            lines.push(`Resistance: ${formatNumber(result.resistance_value)} ${result.resistance_unit || ""}`.trim());
        }
        lines.push(`Source: ${result.source_type === "workout" ? "Workout" : "Assessment"}`);
        tooltip.textContent = lines.join("\n");
        tooltip.style.display = "block";
        positionTooltip(clientX, clientY);
    }

    function setSummary(values, metric) {
        summary.hidden = values.length === 0;
        if (!values.length) {
            latestValue.textContent = "—";
            previousValue.textContent = "—";
            changeValue.textContent = "—";
            return;
        }
        const latest = values[values.length - 1];
        const previous = values.length > 1 ? values[values.length - 2] : null;
        latestValue.textContent = formatMetricValue(latest, metric) || "—";
        previousValue.textContent = previous ? formatMetricValue(previous, metric) || "—" : "—";
        if (!previous || metric === "resistance_value" &&
            latest.resistance_unit !== previous.resistance_unit) {
            changeValue.textContent = "—";
            return;
        }
        const change = latest[metric] - previous[metric];
        changeValue.textContent = `${change >= 0 ? "+" : ""}${formatNumber(change)}${
            metric === "overall_score" ? "%" : ""
        }`;
    }

    function renderEmpty(message) {
        chart.replaceChildren();
        chart.hidden = true;
        summary.hidden = true;
        emptyMessage.hidden = false;
        emptyMessage.textContent = message;
        tooltip.style.display = "none";
    }

    function renderChart() {
        const metric = metricSelector.value;
        const values = displayedResults.filter(result => (
            result[metric] !== null && result[metric] !== undefined
        ));
        setSummary(values, metric);
        if (!displayedResults.length) {
            renderEmpty(
                allResults.length
                    ? "No results are available for this side."
                    : "No progression data is available for this patient yet.",
            );
            return;
        }
        if (!values.length) {
            renderEmpty("No data is available for this metric.");
            return;
        }
        if (metric === "resistance_value") {
            const units = new Set(values.map(result => result.resistance_unit || ""));
            if (units.size > 1) {
                renderEmpty(
                    "Resistance cannot be plotted together because the selected records use different units.",
                );
                return;
            }
        }

        chart.hidden = false;
        emptyMessage.hidden = true;
        const plotWidth = chartWidth - plot.left - plot.right;
        const plotHeight = chartHeight - plot.top - plot.bottom;
        const numericValues = values.map(result => result[metric]);
        const min = metric === "overall_score" ? 0 : Math.min(...numericValues, 0);
        const max = metric === "overall_score"
            ? 100
            : Math.max(...numericValues, 1);
        const yPosition = value => (
            plot.top + ((max - value) / Math.max(max - min, 1)) * plotHeight
        );
        const xPosition = index => values.length === 1
            ? plot.left + plotWidth / 2
            : plot.left + (index / (values.length - 1)) * plotWidth;

        chart.replaceChildren();
        for (let index = 0; index <= 4; index += 1) {
            const value = min + ((max - min) * index / 4);
            const y = yPosition(value);
            chart.appendChild(createSvgElement("line", {
                x1: plot.left, y1: y, x2: chartWidth - plot.right, y2: y,
                class: index === 0 ? "chart-axis" : "chart-gridline",
            }));
            addLabel(
                chart,
                `${formatNumber(value)}${metric === "overall_score" ? "%" : ""}`,
                plot.left - 12,
                y + 4,
                "chart-label",
                "end",
            );
        }
        chart.appendChild(createSvgElement("line", {
            x1: plot.left, y1: plot.top, x2: plot.left,
            y2: chartHeight - plot.bottom, class: "chart-axis",
        }));
        chart.appendChild(createSvgElement("line", {
            x1: plot.left, y1: chartHeight - plot.bottom,
            x2: chartWidth - plot.right, y2: chartHeight - plot.bottom,
            class: "chart-axis",
        }));
        addLabel(
            chart, metricLabels[metric], 18, plot.top + plotHeight / 2,
            "chart-axis-title",
        ).setAttribute("transform", `rotate(-90 18 ${plot.top + plotHeight / 2})`);
        addLabel(
            chart, "Date (oldest to newest)", plot.left + plotWidth / 2,
            chartHeight - 12, "chart-axis-title",
        );

        chart.appendChild(createSvgElement("polyline", {
            points: values.map((result, index) => (
                `${xPosition(index)},${yPosition(result[metric])}`
            )).join(" "),
            class: "progress-line",
        }));
        values.forEach((result, index) => {
            const circle = createSvgElement("circle", {
                cx: xPosition(index), cy: yPosition(result[metric]), r: 7,
                class: result.source_type === "workout"
                    ? "progress-point workout-point"
                    : "progress-point assessment-point",
                tabindex: 0,
                "aria-label": `${formatDate(result.occurred_at)}, ${
                    metricLabels[metric]
                }: ${formatMetricValue(result, metric)}`,
            });
            circle.result = result;
            circle.addEventListener("pointerenter", event => {
                showTooltip(circle, event.clientX, event.clientY);
            });
            circle.addEventListener("pointermove", event => {
                positionTooltip(event.clientX, event.clientY);
            });
            circle.addEventListener("pointerleave", () => {
                tooltip.style.display = "none";
            });
            circle.addEventListener("focus", () => {
                const bounds = circle.getBoundingClientRect();
                showTooltip(circle, bounds.left + bounds.width / 2, bounds.top);
            });
            circle.addEventListener("blur", () => {
                tooltip.style.display = "none";
            });
            chart.appendChild(circle);
        });
    }

    function formatSide(side) {
        return side
            ? side[0].toUpperCase() + side.slice(1)
            : "Unspecified";
    }

    function formatSource(sourceType) {
        return sourceType === "workout" ? "Workout" : "Legacy assessment";
    }

    function formatStatus(sessionStatus) {
        return sessionStatus ? sessionStatus : "Not applicable";
    }

    function formatResistance(record) {
        if (record.resistance_value === null || record.resistance_value === undefined) {
            return "Not recorded";
        }
        return `${formatNumber(record.resistance_value)} ${
            record.resistance_unit || ""
        }`.trim();
    }

    function setAdvisoryStatus(message, isError = false) {
        advisoryStatus.textContent = message;
        advisoryStatus.classList.toggle("error", isError);
        advisoryStatus.hidden = !message;
    }

    function renderAdvisoryTable(records) {
        advisoryEvidence.replaceChildren();
        if (!records.length) {
            const empty = document.createElement("p");
            empty.className = "advisory-empty";
            empty.textContent = "No observations support this classification.";
            advisoryEvidence.appendChild(empty);
            return;
        }
        const table = document.createElement("table");
        table.className = "advisory-evidence-table";
        const caption = document.createElement("caption");
        caption.textContent = "Evidence observations used by the software classification";
        table.appendChild(caption);
        const headers = [
            "Date", "Exercise", "Side", "Source", "Status",
            "Completed / Target", "Completion", "Overall Score",
            "Resistance", "Source ID",
        ];
        const head = document.createElement("thead");
        const headRow = document.createElement("tr");
        headers.forEach(header => {
            const cell = document.createElement("th");
            cell.scope = "col";
            cell.textContent = header;
            headRow.appendChild(cell);
        });
        head.appendChild(headRow);
        table.appendChild(head);
        const body = document.createElement("tbody");
        records.forEach(record => {
            const row = document.createElement("tr");
            const values = [
                formatDate(record.occurred_at),
                record.exercise_id || "Unknown",
                formatSide(record.side),
                formatSource(record.source_type),
                formatStatus(record.session_status),
                record.completed_repetitions === null ||
                record.target_repetitions === null
                    ? "Not available"
                    : `${record.completed_repetitions} / ${record.target_repetitions}`,
                record.completion_percentage === null ||
                record.completion_percentage === undefined
                    ? "Not available"
                    : `${formatNumber(record.completion_percentage)}%`,
                record.overall_score === null ||
                record.overall_score === undefined
                    ? "Not recorded"
                    : formatNumber(record.overall_score),
                formatResistance(record),
                record.source_id === null || record.source_id === undefined
                    ? "Not available"
                    : `${record.source_id}`,
            ];
            values.forEach(value => {
                const cell = document.createElement("td");
                cell.textContent = value;
                row.appendChild(cell);
            });
            body.appendChild(row);
        });
        table.appendChild(body);
        advisoryEvidence.appendChild(table);
    }

    function renderAdvisory(payload) {
        const summaryData = payload.evidence_summary || {};
        const classification = payload.classification || "INSUFFICIENT_DATA";
        advisoryContent.hidden = false;
        advisoryEmpty.hidden = true;
        advisoryExercise.textContent = exerciseSelector.options[
            exerciseSelector.selectedIndex
        ]?.textContent || payload.exercise_id || "Selected exercise";
        advisorySide.textContent = formatSide(payload.side);
        advisoryCount.textContent = `${summaryData.observation_count || 0}`;
        advisoryClassificationValue.textContent =
            classificationLabels[classification] || classification;
        advisoryClassification.className = "advisory-classification";
        if (classification === "REVIEW_REQUIRED") {
            advisoryClassification.classList.add("review");
        } else if (
            classification === "POSSIBLE_PROGRESSION" ||
            classification === "POSSIBLE_REGRESSION"
        ) {
            advisoryClassification.classList.add("possible");
        }
        advisoryReasons.replaceChildren();
        (summaryData.reasons || []).forEach(reason => {
            const item = document.createElement("p");
            item.textContent = reason;
            advisoryReasons.appendChild(item);
        });
        advisoryLimitations.replaceChildren();
        (payload.limitations || summaryData.limitations || []).forEach(limitation => {
            const item = document.createElement("li");
            item.textContent = limitation;
            advisoryLimitations.appendChild(item);
        });
        renderAdvisoryTable(payload.evidence_records || []);
    }

    function renderAdvisoryEmpty(message) {
        advisoryContent.hidden = true;
        advisoryEmpty.hidden = false;
        advisoryEmpty.textContent = message;
        reviewHistory.replaceChildren();
        reviewCurrentStatus.textContent = "UNREVIEWED";
        reviewLastReviewed.textContent = "—";
    }

    function setReviewStatus(message, isError = false) {
        reviewStatus.textContent = message;
        reviewStatus.classList.toggle("error", isError);
    }

    function renderReviewHistory(payload) {
        const reviews = payload.reviews || [];
        reviewCurrentStatus.textContent = payload.current_disposition || "UNREVIEWED";
        reviewLastReviewed.textContent = reviews.length
            ? formatDateTime(reviews[reviews.length - 1].reviewed_at)
            : "—";
        reviewHistory.replaceChildren();
        if (!reviews.length) {
            const empty = document.createElement("p");
            empty.className = "advisory-empty";
            empty.textContent = "No review events recorded.";
            reviewHistory.appendChild(empty);
            return;
        }
        const table = document.createElement("table");
        table.className = "advisory-evidence-table";
        const caption = document.createElement("caption");
        caption.textContent = "Append-only human review history";
        table.appendChild(caption);
        const head = document.createElement("thead");
        const headRow = document.createElement("tr");
        ["Reviewed", "Reviewer", "Disposition", "Note"].forEach(label => {
            const cell = document.createElement("th");
            cell.scope = "col";
            cell.textContent = label;
            headRow.appendChild(cell);
        });
        head.appendChild(headRow);
        table.appendChild(head);
        const body = document.createElement("tbody");
        reviews.forEach(review => {
            const row = document.createElement("tr");
            [
                formatDateTime(review.reviewed_at),
                review.reviewer_reference,
                review.disposition,
                review.note || "—",
            ].forEach(value => {
                const cell = document.createElement("td");
                cell.textContent = value;
                row.appendChild(cell);
            });
            body.appendChild(row);
        });
        table.appendChild(body);
        reviewHistory.appendChild(table);
    }

    async function loadReviewHistory(requestSequence) {
        const params = new URLSearchParams({
            exercise_id: exerciseSelector.value,
        });
        if (sideSelector.value) {
            params.set("side", sideSelector.value);
        }
        const response = await fetch(
            `/api/patients/${encodeURIComponent(config.patient_id)}/progression/advisory/reviews?${params}`,
            { headers: { Accept: "application/json" } },
        );
        if (!response.ok) {
            throw new Error("Unable to load review history.");
        }
        const payload = await response.json();
        if (requestSequence === advisoryRequestSequence) {
            renderReviewHistory(payload);
        }
    }

    async function loadAdvisory() {
        const requestSequence = ++advisoryRequestSequence;
        if (!exerciseSelector.value) {
            setAdvisoryStatus("");
            renderAdvisoryEmpty("Select an exercise to review its advisory history.");
            return;
        }
        const params = new URLSearchParams({
            exercise_id: exerciseSelector.value,
        });
        if (sideSelector.value) {
            params.set("side", sideSelector.value);
        }
        setAdvisoryStatus("Loading advisory review...");
        advisoryContent.hidden = true;
        advisoryEmpty.hidden = true;
        try {
            const response = await fetch(
                `/api/patients/${encodeURIComponent(config.patient_id)}/progression/advisory?${params}`,
                { headers: { Accept: "application/json" } },
            );
            if (!response.ok) {
                throw new Error("Unable to load advisory review.");
            }
            const payload = await response.json();
            if (requestSequence !== advisoryRequestSequence) {
                return;
            }
            setAdvisoryStatus("");
            renderAdvisory(payload);
            try {
                await loadReviewHistory(requestSequence);
                setReviewStatus("");
            } catch (error) {
                setReviewStatus(error.message, true);
            }
        } catch (error) {
            if (requestSequence !== advisoryRequestSequence) {
                return;
            }
            renderAdvisoryEmpty("Unable to load advisory review.");
            setAdvisoryStatus(error.message, true);
        }
    }

    function populateExercises(results) {
        const exercises = new Map();
        results.forEach(result => {
            if (result.exercise_id) {
                exercises.set(result.exercise_id, result.exercise_display_name);
            }
        });
        exerciseSelector.replaceChildren();
        [...exercises.entries()]
            .sort((a, b) => a[1].localeCompare(b[1]))
            .forEach(([id, name]) => {
                const option = document.createElement("option");
                option.value = id;
                option.textContent = name;
                exerciseSelector.appendChild(option);
            });
        if (!exercises.size && results.length) {
            const option = document.createElement("option");
            option.value = "";
            option.textContent = "All available history";
            exerciseSelector.appendChild(option);
        }
        exerciseSelector.disabled = !results.length;
        sideSelector.disabled = exercises.size === 0;
        if (exercises.size) {
            exerciseSelector.value = [...exercises.keys()][0];
        }
    }

    async function loadResults() {
        const params = new URLSearchParams();
        if (exerciseSelector.value) {
            params.set("exercise_id", exerciseSelector.value);
        }
        if (sideSelector.value) {
            params.set("side", sideSelector.value);
        }
        chart.hidden = true;
        summary.hidden = true;
        emptyMessage.hidden = true;
        setStatus("Loading progression history...");
        try {
            const response = await fetch(
                `/api/patients/${encodeURIComponent(config.patient_id)}/progression?${params}`,
                { headers: { Accept: "application/json" } },
            );
            if (!response.ok) {
                throw new Error("Unable to load progression history.");
            }
            const payload = await response.json();
            displayedResults = payload.results || [];
            setStatus("");
            renderChart();
        } catch (error) {
            displayedResults = [];
            renderEmpty("Unable to load progression history. Please try again.");
            setStatus(error.message, true);
        }
    }

    async function initialize() {
        setStatus("Loading progression history...");
        try {
            const response = await fetch(
                `/api/patients/${encodeURIComponent(config.patient_id)}/progression`,
                { headers: { Accept: "application/json" } },
            );
            if (!response.ok) {
                throw new Error("Unable to load progression history.");
            }
            const payload = await response.json();
            allResults = payload.results || [];
            populateExercises(allResults);
            if (!allResults.length) {
                setStatus("");
                renderEmpty("No progression data is available for this patient yet.");
                renderAdvisoryEmpty("No previous history is available for advisory review.");
                setAdvisoryStatus("");
                return;
            }
            setStatus("");
            await loadResults();
            if (!config.patient_portal) {
                await loadAdvisory();
            }
        } catch (error) {
            renderEmpty("Unable to load progression history. Please try again.");
            setStatus(error.message, true);
            renderAdvisoryEmpty("Unable to load advisory review.");
            setAdvisoryStatus(error.message, true);
        }
    }

    exerciseSelector.addEventListener("change", () => {
        loadResults();
        loadAdvisory();
    });
    sideSelector.addEventListener("change", () => {
        loadResults();
        loadAdvisory();
    });
    reviewForm.addEventListener("submit", async event => {
        event.preventDefault();
        if (!exerciseSelector.value) {
            return;
        }
        const params = new URLSearchParams({
            exercise_id: exerciseSelector.value,
        });
        if (sideSelector.value) {
            params.set("side", sideSelector.value);
        }
        setReviewStatus("Recording review...");
        try {
            const response = await fetch(
                `/api/patients/${encodeURIComponent(config.patient_id)}/progression/advisory/reviews?${params}`,
                {
                    method: "POST",
                    headers: {
                        Accept: "application/json",
                        "Content-Type": "application/json",
                        "X-CSRF-Token": document.querySelector(
                            'meta[name="csrf-token"]',
                        )?.content || "",
                    },
                    body: JSON.stringify({
                        disposition: reviewDisposition.value,
                        reviewer_reference: reviewerReference.value,
                        note: reviewNote.value,
                    }),
                },
            );
            const payload = await response.json();
            if (!response.ok) {
                throw new Error(payload.error || "Unable to record review.");
            }
            reviewerReference.value = "";
            reviewNote.value = "";
            await loadReviewHistory(advisoryRequestSequence);
            setReviewStatus("Review recorded.");
        } catch (error) {
            setReviewStatus(error.message, true);
        }
    });
    metricSelector.addEventListener("change", renderChart);
    initialize();
})();
