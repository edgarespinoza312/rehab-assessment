(() => {
    const definitions = JSON.parse(
        document.getElementById("builder-exercise-data").textContent,
    );
    const MAX_WORKOUT_PLAN_EXERCISES = 50;
    const list = document.getElementById("builder-exercise-list");
    const emptyMessage = document.getElementById("builder-empty-message");
    const choice = document.getElementById("builder-exercise-choice");
    const message = document.getElementById("builder-message");
    const saveButton = document.getElementById("builder-save-workout");
    const patientSelector = document.getElementById("workout-plan-patient");
    let historyRequestSequence = 0;
    let draggedCard = null;

    function moveCard(card, direction) {
        const cards = [...list.children];
        const index = cards.indexOf(card);
        const destination = index + direction;
        if (destination < 0 || destination >= cards.length) return;
        if (direction < 0) {
            list.insertBefore(card, cards[destination]);
        } else {
            list.insertBefore(cards[destination], card);
        }
    }

    function addField(card, labelText, control, description = null) {
        const label = document.createElement("label");
        label.className = "builder-field";
        const labelRow = document.createElement("span");
        labelRow.className = "builder-label-row";
        labelRow.appendChild(document.createTextNode(labelText));
        if (description) {
            const info = document.createElement("button");
            const descriptionId = `builder-info-${Math.random().toString(36).slice(2)}`;
            info.type = "button";
            info.className = "builder-info";
            info.textContent = "i";
            info.setAttribute("aria-label", `More information about ${labelText}`);
            info.setAttribute("aria-describedby", descriptionId);
            info.setAttribute("aria-expanded", "false");
            info.title = description;
            const descriptionElement = document.createElement("span");
            descriptionElement.id = descriptionId;
            descriptionElement.className = "builder-info-popover";
            descriptionElement.textContent = description;
            labelRow.append(info, descriptionElement);
            info.addEventListener("click", () => {
                const expanded = info.getAttribute("aria-expanded") === "true";
                info.setAttribute("aria-expanded", String(!expanded));
                descriptionElement.classList.toggle("is-open", !expanded);
            });
        }
        label.append(labelRow, control);
        card.appendChild(label);
        return control;
    }

    function formatHistoryDate(value) {
        const date = new Date(value);
        return Number.isNaN(date.getTime())
            ? value
            : date.toLocaleDateString(undefined, {
                year: "numeric", month: "short", day: "numeric",
            });
    }

    function formatHistoryValue(value) {
        if (value === null || value === undefined) return "—";
        return Number.isInteger(value) ? `${value}` : Number(value).toFixed(1);
    }

    function formatResistance(value, unit, resistanceType) {
        if (value === null || value === undefined) return "—";
        return [
            formatHistoryValue(value),
            unit || null,
            resistanceType || null,
        ].filter(Boolean).join(" ");
    }

    function escapeHtml(value) {
        return String(value)
            .replaceAll("&", "&amp;")
            .replaceAll("<", "&lt;")
            .replaceAll(">", "&gt;")
            .replaceAll('"', "&quot;")
            .replaceAll("'", "&#039;");
    }

    function createHistoryPanel(card, exerciseId, sideSelector) {
        const panel = document.createElement("section");
        panel.className = "builder-history";
        panel.setAttribute("aria-labelledby", `builder-history-title-${exerciseId}`);
        const heading = document.createElement("h3");
        heading.id = `builder-history-title-${exerciseId}`;
        heading.textContent = "Recent History";
        panel.appendChild(heading);

        const status = document.createElement("p");
        status.className = "builder-history-status";
        status.setAttribute("role", "status");
        status.textContent = "Select a patient to load history.";
        panel.appendChild(status);

        const latest = document.createElement("div");
        latest.className = "builder-history-latest";
        latest.hidden = true;
        panel.appendChild(latest);

        const table = document.createElement("table");
        table.className = "builder-history-table";
        table.hidden = true;
        table.innerHTML = `
            <caption class="sr-only">Recent exercise history</caption>
            <thead><tr>
                <th scope="col">Date</th>
                <th scope="col">Reps</th>
                <th scope="col">Completion</th>
                <th scope="col">Score</th>
                <th scope="col">Resistance</th>
            </tr></thead>
            <tbody></tbody>
        `;
        panel.appendChild(table);
        card.appendChild(panel);
        panel.history = { status, latest, table, sideSelector, exerciseId, requestId: 0 };
        return panel;
    }

    function renderHistory(panel, payload) {
        const { status, latest, table } = panel.history;
        const contexts = payload.contexts || [];
        latest.hidden = true;
        table.hidden = true;
        table.querySelector("tbody").replaceChildren();
        if (!contexts.length) {
            status.className = "builder-history-status";
            status.textContent = "No previous history for this exercise.";
            return;
        }

        const context = contexts[0];
        const side = context.side
            ? context.side[0].toUpperCase() + context.side.slice(1)
            : "Side unspecified";
        const source = context.source_type === "workout" ? "Workout" : "Assessment";
        const session = context.session_status && context.source_type === "workout"
            ? ` · ${context.session_status}`
            : "";
        const reps = context.previous_target_repetitions === null
            ? `${formatHistoryValue(context.previous_completed_repetitions)} reps`
            : `${formatHistoryValue(context.previous_completed_repetitions)} / ${
                formatHistoryValue(context.previous_target_repetitions)
            } reps`;
        const completion = context.previous_completion_percentage === null
            ? "—"
            : `${formatHistoryValue(context.previous_completion_percentage)}%`;
        latest.innerHTML = `
            <strong>${escapeHtml(`${side} · ${source}${session}`)}</strong><br>
            ${escapeHtml(formatHistoryDate(context.latest_observation_at))}<br>
            ${escapeHtml(`${reps} · ${completion} completion`)}<br>
            Overall Score: ${escapeHtml(formatHistoryValue(context.previous_overall_score))}<br>
            Resistance: ${escapeHtml(formatResistance(
                context.previous_resistance_value,
                context.previous_resistance_unit,
                context.previous_resistance_type,
            ))}
        `;
        latest.hidden = false;

        const observations = context.recent_resistance_observations || [];
        const rows = Math.max(
            context.recent_overall_scores?.length || 0,
            context.recent_completion_percentages?.length || 0,
            observations.length,
        );
        const historyDates = context.recent_observation_dates || [];
        for (let index = 0; index < rows; index += 1) {
            const row = document.createElement("tr");
            const date = historyDates[index] || context.latest_observation_at;
            const score = context.recent_overall_scores?.[index];
            const percentage = context.recent_completion_percentages?.[index];
            const resistance = observations[index];
            row.innerHTML = `
                <td>${escapeHtml(formatHistoryDate(date))}</td>
                <td>${escapeHtml(index === rows - 1 ? reps : "—")}</td>
                <td>${escapeHtml(percentage === null || percentage === undefined
                    ? "—" : `${formatHistoryValue(percentage)}%`)}</td>
                <td>${escapeHtml(formatHistoryValue(score))}</td>
                <td>${escapeHtml(resistance
                    ? formatResistance(resistance.value, resistance.unit, resistance.resistance_type)
                    : "—")}</td>
            `;
            table.querySelector("tbody").appendChild(row);
        }
        table.hidden = rows === 0;
        status.className = "builder-history-status";
        status.textContent = "";
    }

    async function loadHistory(panel) {
        const patientId = patientSelector.value;
        const { status, sideSelector, exerciseId } = panel.history;
        const requestId = ++historyRequestSequence;
        panel.history.requestId = requestId;
        panel.history.latest.hidden = true;
        panel.history.table.hidden = true;
        status.className = "builder-history-status";
        status.textContent = patientId
            ? "Loading progression history..."
            : "Select a patient to load history.";
        if (!patientId) return;

        const params = new URLSearchParams({
            exercise_id: exerciseId,
            recent_limit: "5",
        });
        if (sideSelector.value) params.set("side", sideSelector.value);
        try {
            const response = await fetch(
                `/api/patients/${encodeURIComponent(patientId)}/progression/context?${params}`,
                { headers: { Accept: "application/json" } },
            );
            if (!response.ok) throw new Error("Unable to load progression history.");
            const payload = await response.json();
            if (requestId !== historyRequestSequence) return;
            renderHistory(panel, payload);
        } catch (error) {
            if (requestId !== historyRequestSequence) return;
            status.className = "builder-history-status error";
            status.textContent = "Unable to load progression history.";
        }
    }

    function addExercise() {
        const definition = definitions.find(item => item.id === choice.value);
        if (!definition) return;
        if (list.children.length >= MAX_WORKOUT_PLAN_EXERCISES) {
            message.textContent = `A workout can contain at most ${MAX_WORKOUT_PLAN_EXERCISES} exercises.`;
            return;
        }

        const card = document.createElement("li");
        card.className = "builder-exercise-card";
        card.draggable = true;
        card.dataset.exerciseId = definition.id;

        const heading = document.createElement("div");
        heading.className = "builder-exercise-heading";
        const title = document.createElement("strong");
        title.textContent = definition.name;
        const dragHint = document.createElement("span");
        dragHint.textContent = "Drag to reorder";
        heading.append(title, dragHint);
        card.appendChild(heading);

        const side = document.createElement("select");
        side.className = "builder-side";
        for (const value of definition.sides) {
            const option = document.createElement("option");
            option.value = value;
            option.textContent = value[0].toUpperCase() + value.slice(1);
            side.appendChild(option);
        }
        addField(card, "Side", side);
        const historyPanel = createHistoryPanel(card, definition.id, side);
        side.addEventListener("change", () => loadHistory(historyPanel));

        const repetitions = document.createElement("input");
        repetitions.className = "builder-repetitions";
        repetitions.type = "number";
        repetitions.min = "1";
        repetitions.step = "1";
        repetitions.value = "10";
        repetitions.required = true;
        addField(card, "Target repetitions", repetitions);

        const resistance = document.createElement("input");
        resistance.className = "builder-resistance";
        resistance.type = "number";
        resistance.min = "0";
        resistance.step = "any";
        resistance.placeholder = "Optional";
        addField(
            card,
            "Resistance value",
            resistance,
            "The numerical amount of resistance used for this exercise, when applicable.",
        );

        const unit = document.createElement("input");
        unit.className = "builder-resistance-unit";
        unit.type = "text";
        unit.maxLength = 24;
        unit.placeholder = "e.g. lb, kg";
        addField(
            card,
            "Resistance unit",
            unit,
            "The unit associated with the resistance value, such as lb or kg.",
        );

        const resistanceType = document.createElement("input");
        resistanceType.className = "builder-resistance-type";
        resistanceType.type = "text";
        resistanceType.maxLength = 40;
        resistanceType.placeholder = "Optional";
        addField(
            card,
            "Resistance type",
            resistanceType,
            "The type or source of resistance, such as dumbbell, resistance band, cable, or bodyweight.",
        );

        const controls = document.createElement("div");
        controls.className = "builder-card-actions";
        for (const [label, direction] of [["Move up", -1], ["Move down", 1]]) {
            const button = document.createElement("button");
            button.type = "button";
            button.textContent = label;
            button.addEventListener("click", () => moveCard(card, direction));
            controls.appendChild(button);
        }
        const remove = document.createElement("button");
        remove.type = "button";
        remove.textContent = "Remove";
        remove.addEventListener("click", () => {
            card.remove();
            updateEmptyState();
        });
        controls.appendChild(remove);
        card.appendChild(controls);
        list.appendChild(card);
        updateEmptyState();
        loadHistory(historyPanel);
    }

    function updateEmptyState() {
        emptyMessage.hidden = list.children.length > 0;
    }

    list.addEventListener("dragstart", event => {
        const card = event.target.closest(".builder-exercise-card");
        if (!card) return;
        draggedCard = card;
        card.classList.add("is-dragging");
        event.dataTransfer.effectAllowed = "move";
    });
    list.addEventListener("dragend", () => {
        draggedCard?.classList.remove("is-dragging");
        draggedCard = null;
    });
    list.addEventListener("dragover", event => {
        event.preventDefault();
        const target = event.target.closest(".builder-exercise-card");
        if (!draggedCard || !target || target === draggedCard) return;
        const bounds = target.getBoundingClientRect();
        const insertAfter = event.clientY > bounds.top + bounds.height / 2;
        list.insertBefore(draggedCard, insertAfter ? target.nextSibling : target);
    });

    document.getElementById("builder-add-exercise").addEventListener(
        "click",
        addExercise,
    );
    patientSelector.addEventListener("change", () => {
        list.querySelectorAll(".builder-history").forEach(loadHistory);
    });
    saveButton.addEventListener("click", async () => {
        const name = document.getElementById("workout-plan-name").value.trim();
        const description = document.getElementById("workout-plan-description").value;
        const cards = [...list.querySelectorAll(".builder-exercise-card")];
        if (!name) {
            message.textContent = "Enter a workout name.";
            return;
        }
        if (!cards.length) {
            message.textContent = "Add at least one exercise.";
            return;
        }

        const exercises = [];
        for (const [position, card] of cards.entries()) {
            const rawRepetitions = card.querySelector(".builder-repetitions").value;
            const targetRepetitions = Number(rawRepetitions);
            if (!Number.isInteger(targetRepetitions) || targetRepetitions < 1) {
                message.textContent = "Every exercise needs a positive whole-number rep target.";
                return;
            }
            const rawResistance = card.querySelector(".builder-resistance").value.trim();
            const resistanceValue = rawResistance === "" ? null : Number(rawResistance);
            const resistanceUnit = card.querySelector(".builder-resistance-unit").value.trim();
            if (
                resistanceValue !== null
                && (!Number.isFinite(resistanceValue) || resistanceValue < 0 || !resistanceUnit)
            ) {
                message.textContent = "Resistance requires a non-negative value and a unit.";
                return;
            }
            const resistanceType = card.querySelector(".builder-resistance-type").value.trim();
            if (resistanceValue === null && (resistanceUnit || resistanceType)) {
                message.textContent = "Enter a resistance value or clear its unit and type.";
                return;
            }
            exercises.push({
                position,
                exercise_id: card.dataset.exerciseId,
                side: card.querySelector(".builder-side").value,
                target_repetitions: targetRepetitions,
                resistance_value: resistanceValue,
                resistance_unit: resistanceValue === null ? null : resistanceUnit,
                resistance_type: resistanceValue === null
                    ? null
                    : resistanceType || null,
            });
        }

        const rawPatientId = document.getElementById("workout-plan-patient").value;
        const payload = {
            name,
            description,
            patient_id: rawPatientId ? Number(rawPatientId) : null,
            exercises,
        };
        saveButton.disabled = true;
        message.textContent = "Saving workout…";
        try {
            const response = await fetch("/workout/plans", {
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
                throw new Error(result.error || `Workout save failed (${response.status})`);
            }
            const query = rawPatientId
                ? `?patient_id=${encodeURIComponent(rawPatientId)}`
                : "";
            window.location.assign(`/selection${query}`);
        } catch (error) {
            message.textContent = error.message;
            saveButton.disabled = false;
        }
    });
})();
