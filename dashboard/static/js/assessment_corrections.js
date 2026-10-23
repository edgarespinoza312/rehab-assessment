(() => {
    "use strict";

    const csrfToken = () =>
        document.querySelector('meta[name="csrf-token"]')?.content
        || document.querySelector('input[name="csrf_token"]')?.value
        || "";

    async function postJson(url, payload) {
        const response = await fetch(url, {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "X-CSRF-Token": csrfToken(),
            },
            body: JSON.stringify(payload),
        });
        let data;
        try {
            data = await response.json();
        } catch {
            data = { error: `Request failed (${response.status})` };
        }
        if (!response.ok) {
            throw new Error(data.error || `Request failed (${response.status})`);
        }
        return data;
    }

    const correctionForm = document.getElementById("assessment-correction-form");
    if (correctionForm) {
        correctionForm.addEventListener("submit", async event => {
            event.preventDefault();
            const message = document.getElementById("correction-submit-message");
            const submit = correctionForm.querySelector('button[type="submit"]');
            const field = correctionForm.elements.field_name.value;
            const raw = correctionForm.elements.proposed_value.value.trim();
            let proposedValue = raw;

            try {
                if (["average_score", "best_score", "worst_score"].includes(field)) {
                    proposedValue = Number(raw);
                    if (!Number.isFinite(proposedValue)) {
                        throw new Error("Score must be a finite number.");
                    }
                } else if (field === "repetitions") {
                    proposedValue = Number(raw);
                    if (!Number.isInteger(proposedValue)) {
                        throw new Error("Repetitions must be a whole number.");
                    }
                } else if (field === "feedback") {
                    try {
                        proposedValue = JSON.parse(raw);
                    } catch {
                        proposedValue = raw;
                    }
                }

                submit.disabled = true;
                message.textContent = "Submitting correction request…";
                const result = await postJson(
                    `/api/assessments/${encodeURIComponent(correctionForm.dataset.assessmentId)}/corrections`,
                    {
                        field_name: field,
                        proposed_value: proposedValue,
                        reason: correctionForm.elements.reason.value,
                        evidence_reference: correctionForm.elements.evidence_reference.value || null,
                    },
                );
                message.textContent =
                    `Correction #${result.correction_id} recorded as ${result.status}. Original data was not changed.`;
                window.setTimeout(() => window.location.reload(), 700);
            } catch (error) {
                message.textContent = error.message;
                submit.disabled = false;
            }
        });
    }

    const delegationForm = document.getElementById("review-delegation-form");
    if (delegationForm) {
        delegationForm.addEventListener("submit", async event => {
            event.preventDefault();
            const message = document.getElementById("review-delegation-message");
            const submit = delegationForm.querySelector('button[type="submit"]');
            submit.disabled = true;
            try {
                const result = await postJson(
                    `/api/patients/${encodeURIComponent(delegationForm.dataset.patientId)}/review-delegations`,
                    {
                        reviewer_user_id: Number(delegationForm.elements.reviewer_user_id.value),
                        scope: delegationForm.elements.scope.value,
                        reason: delegationForm.elements.reason.value,
                    },
                );
                message.textContent =
                    `Delegation #${result.delegation_id} created for ${result.scope}. Access is limited to the specified review task and remains tied to your active patient assignment.`;
                window.setTimeout(() => window.location.reload(), 900);
            } catch (error) {
                message.textContent = error.message;
                submit.disabled = false;
            }
        });
    }
})();
