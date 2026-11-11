# Revaliv Product Requirements and Acceptance Traceability

**Status:** Requirements baseline for implementation on `revaliv-governance-requirements`  
**Source:** Product-planning decisions recorded in the Revaliv planning conversation, including Questions 87–101 and earlier decisions summarized below.  
**Important:** A recorded decision is a requirement, not evidence that a software control exists. Each requirement remains unverified until linked to implementation and suitable test, audit, clinical-validation, or hardware evidence.

## 1. Delivery and safety principles

1. Preserve patient safety and clinical validity as release-blocking gates. Business deadlines cannot waive them.
2. Use risk-proportionate controls: restrict affected capabilities when warranted and preserve unaffected, verified functions.
3. Separate documented policy from implemented enforcement and independently verified evidence.
4. Do not represent passing software tests as proof of clinical accuracy, hardware readiness, or production security.
5. Keep changes on this branch; do not modify or merge into `main` without a separately authorized review.

## 2. Product and clinical workflow requirements

| ID | Requirement | Acceptance evidence |
|---|---|---|
| PR-001 | Support patient and clinician workflows for hybrid clinic/home rehabilitation, with clinician oversight. | Role/workflow tests and documented intended-use boundary. |
| PR-002 | Provide a broad, governed exercise library covering shoulder, hip, knee, trunk, gait, and balance, while enabling only validated populations and exercises. | Versioned exercise catalogue, clinical approvals, scope restrictions, and tests. |
| PR-003 | Draft plans from assessment results and patient goals; require clinician approval before activation. | Authorization and state-transition tests showing unapproved plans cannot be used. |
| PR-004 | Adapt progression using objective movement measures and patient-reported response, within clinician-defined limits and safety rules. | Deterministic tests, traceable thresholds, clinical review, and validation evidence before consequential use. |
| PR-005 | Use a multidimensional outcomes profile: movement, functional tasks, symptoms, adherence, and patient-specific goals. | Data dictionary, persistence/round-trip tests, and report checks. |
| PR-006 | Personalize longitudinally; use de-identified population learning only after sufficient validation and authorization. | Dataset lineage, governance approvals, external validation where appropriate, and subgroup results. |
| PR-007 | Distinguish measured facts from inferred conclusions; expose confidence, uncertainty, limitations, evidence, and model/version provenance. | UI/API contract tests and explanation review. |
| PR-008 | Provide a unified clinician command center for prioritized risk alerts, patient progress, pending approvals, adherence, workload, and patient drill-down. | Role-based UI tests and alert-priority tests. |
| PR-009 | Use safety-first patient prioritization, transparent configurable rules, deadlines, and audited overrides. | Prioritization tests, override audit events, and escalation tests. |
| PR-010 | Monitor clinician capacity and recommend rebalancing; clinical responsibility changes and patient reassignment require authorized approval. | Permission tests and assignment audit history. |
| PR-011 | Provide layered accessible patient reports with goals, consistency, symptoms, validated trends, detail, and uncertainty labels. | Accessibility review, report tests, and data-provenance checks. |
| PR-012 | Support secure clinician messaging, personalized coaching, configurable notifications, and approved escalation protocols. | Authorization, delivery, escalation, and audit tests. |

## 3. Assessment, exercise, and model governance

| ID | Requirement | Acceptance evidence |
|---|---|---|
| VAL-001 | Validate measurement families in sequence: joint angles/range of motion, functional movement, balance, then gait; each has separate criteria. | Approved protocols, reference data, predeclared metrics, and results. |
| VAL-002 | Use instrumented references where feasible, standardized clinician measures, and repeated trials. | Protocol and annotated validation dataset with provenance. |
| VAL-003 | Establish controlled camera baselines, then separately evaluate position, distance, lighting, and partial occlusion. | Test matrix and reproducible results. |
| VAL-004 | Gate measurements on confidence; guide repositioning, reject unreliable data, permit only suitable low-risk activity, and block activities requiring reliable tracking. | Failure-mode tests for low confidence, missing joints, occlusion, and out-of-frame movement. |
| VAL-005 | Define measurement acceptance thresholds by intended use and consequence: reporting, clinician review, or progression. | Approved acceptance criteria and enforced use restrictions. |
| VAL-006 | Preserve both sides of measurement disagreements, provenance, investigation, and documented resolution before consequential use. | Discrepancy records, workflow tests, and audit trail. |
| VAL-007 | Centrally review/version core exercises; allow authorized clinic extensions with distinct approval and validation scope. | Version, role, and scope tests. |
| VAL-008 | Clinically review every exercise; technically validate camera-derived metrics; require stronger evidence for higher-risk or progression-impacting exercises. | Exercise approval records and gated activation tests. |
| VAL-009 | Changes to exercise delivery require clinical approval; changes to measurements, safety assumptions, population, or progression trigger appropriate revalidation. | Change-impact matrix, version history, and regression tests. |
| VAL-010 | Patient-specific modifications stay within validated parameters and clinician-approved limits; changes outside those limits require additional review. | Parameter-boundary tests and approval audit events. |
| VAL-011 | Label out-of-scope AI recommendations as unvalidated proposals; prohibit adding them to active plans before review, validation, and authorization. | API/UI state tests preventing activation. |
| VAL-012 | Clinicians may reject, modify, or defer AI recommendations within their authority; capture rationale and use feedback for governed quality review, not automatic model changes. | Decision audit records and controlled feedback-pipeline evidence. |
| VAL-013 | Govern training data by purpose, authorization, lawful basis, consent/contracts as applicable, de-identification verification, representativeness, lineage, versioning, and required withdrawal. | Dataset registry and governance approval evidence. |
| VAL-014 | Separate evaluation by patient, site, and time where appropriate; use independent external validation for consequential claims. | Evaluation design and reproducible reports. |
| VAL-015 | Set intended-use-specific model gates for sample size, statistical precision, overall and subgroup performance, safety, and external validation. | Predefined criteria and signed evidence package. |
| VAL-016 | If a subgroup criterion fails, restrict affected uses/populations; other uses may proceed only when independently supported. | Enforced population/use restrictions and tests. |
| VAL-017 | Roll out model changes in stages with enhanced surveillance; define rollback triggers and a tested rollback path. | Release record, monitoring results, rollback exercise, and version traceability. |
| VAL-018 | After rollback, identify affected plans, measurements, and decisions; preserve history; reassess unsafe outputs; notify clinicians with acknowledgment and escalation. | Impact analysis, notification tests, and reconciliation evidence. |

## 4. Authorization, privacy, and clinical-record integrity

| ID | Requirement | Acceptance evidence |
|---|---|---|
| SEC-001 | Enforce role, active assignment, and patient/site policy at every patient-specific read, write, export, history query, and mutation. | Route inventory plus two-clinician isolation tests for each protected endpoint. |
| SEC-002 | Explicitly decide and enforce administrator clinical-record access, unassigned-patient visibility/claiming, historical-report access after reassignment, and clinic/tenant boundaries. | Approved policy and corresponding tests; no assumptions from role name alone. |
| SEC-003 | Govern history access through assignment, authorized transfer, patient-authorized sharing where appropriate, and tightly controlled audited exceptional access. | Permission matrix and access-log tests. |
| SEC-004 | Support governed portability for patients and authorized clinic-to-clinic transfers with identity verification, recipient authorization, consent where required, minimization, secure delivery, and audit. | Transfer tests and audit evidence. |
| SEC-005 | Preserve values, units, definitions, timestamps, provenance, validation status, and model versions during portability; map only when equivalence is verified. | Round-trip and semantic-equivalence tests; explicit unmapped/non-equivalent labels. |
| SEC-006 | Correct clinical records through an auditable, impact-tiered workflow; flag downstream decisions affected by erroneous data. | Correction tests, lineage tracing, and downstream-impact review. |
| SEC-007 | Trace affected decisions after correction; block or reverse predefined unsafe changes where safe, otherwise restrict and require clinician review. | Scenario tests and documented resolution records. |
| SEC-008 | Apply purpose-specific data governance, data minimization, retention schedules, legal holds, authorized deletion/de-identification, and auditable disposal. | Retention schedule, deletion tests, and audit records. |
| SEC-009 | Maintain tamper-evident, access-controlled audit records; independently monitor suspicious access, gaps, unauthorized changes, and attempted alteration/deletion. | Tamper/access tests and monitoring evidence. |
| SEC-010 | Validate clinical-record integrity, audit continuity, authorization rules, plan/model versions, and incident state before recovered services return to use. | Disaster-recovery exercise and integrity reconciliation. |
| SEC-011 | Treat critical integrity failure as a mandatory shutdown; isolate other affected records/capabilities and permit only explicitly authorized, verified unaffected functions. | Fault-injection tests and recovery authorization records. |
| SEC-012 | Define and test tiered recovery-point and recovery-time objectives, stricter for clinical records, authorization changes, audit events, and incident state. | Approved RPO/RTO matrix and measured recovery tests. |

## 5. Clinical safety and incident governance

| ID | Requirement | Acceptance evidence |
|---|---|---|
| SAFE-001 | Use tiered symptom handling: warnings for lower-risk concerns, pauses for threshold breaches, clinician review for serious/persistent symptoms, and urgent-care instructions for urgent symptoms. | Clinically approved protocols and scenario tests. |
| SAFE-002 | Combine baseline symptom rules with clinic-approved escalation protocols, patient guidance, audit trails, and explicit limits on automated interpretation. | Protocol approvals and tests. |
| SAFE-003 | Manage safety incidents through formal reporting, severity escalation, evidence preservation, root-cause analysis, corrective/preventive actions, controlled suspension, and authorized reactivation. | End-to-end incident exercise and audit trail. |
| SAFE-004 | Permit authorized clinical-safety, engineering, and security leads to impose temporary restrictions within predefined scopes; critical triggers permit immediate containment and prompt review. | Permission tests, trigger tests, and review records. |
| SAFE-005 | Require independent verification for routine reactivation; require multidisciplinary board approval for critical safety, validity, privacy, or security incidents. | Approval-workflow tests and signed evidence. |
| SAFE-006 | Apply risk-based, precautionary handling to uncertain signals: assess plausible worst-case consequences, uncertainty, exposure, and safeguards; apply targeted temporary restrictions when warranted; preserve verified safe functions; assign owner/deadline; reassess. | Scenario exercises, ownership/deadline fields, restriction logs, and reassessment records. |
| SAFE-007 | Trigger formal investigation when predefined severity, plausibility, exposure, or control-failure criteria are met, even if evidence is incomplete. | Approved trigger matrix and threshold tests. |
| SAFE-008 | Routine investigation closure requires independent review; serious/critical cases require multidisciplinary safety-board approval. | Role separation and closure-authorization tests. |
| SAFE-009 | If root cause remains unknown, document evidence gaps and competing explanations, maintain proportionate restrictions, assign follow-up, set review deadline, and require authorized sign-off. | Unresolved-case workflow tests. |
| SAFE-010 | Reopen closed investigations when predefined criteria for new evidence, recurrence, ineffective corrective actions, or changed exposure are met; credible critical risks allow immediate reopening. | Reopening trigger tests and audit history. |
| SAFE-011 | Link potentially related cases across features, versions, exposures, patients, and sites; appoint a coordinating owner, retain separate case records, assess aggregate risk, and apply proportionate cross-feature restrictions. | Cross-case correlation workflow and record-separation tests. |
| SAFE-012 | Escalate systemic risks when predefined severity, exposure breadth, shared failure mechanisms, control failures, or credible critical-risk evidence triggers are met. | Trigger matrix and escalation tests. |
| SAFE-013 | Resolve disagreements through a safe interim state and deadline-bound independent multidisciplinary escalation; expedite critical cases. | Deadline/escalation tests and documented interim restrictions. |
| SAFE-014 | Require conflict disclosures, recusal from affected approval decisions, independent review for consequential cases, and alternate decision authority; conflicted personnel cannot independently clear their own work. | Conflict register and separation-of-duty tests. |
| SAFE-015 | Do not waive release-blocking safety or clinical-validity gates for business reasons. Only predefined noncritical requirements may have controlled, independently authorized exceptions with rationale and expiration/reassessment. | Release-gate tests and exception register. |
| SAFE-016 | Provide confidential safety-reporting channels, direct independent escalation, non-retaliation protections, tracked outcomes, and review of alleged retaliation. | Reporting-channel exercise and protected-case audit. |
| SAFE-017 | Set severity-based acknowledgment, triage, escalation, and review deadlines; track overdue reports and automatically escalate missed critical deadlines. | SLA threshold tests and immutable event history. |
| SAFE-018 | Assess governance effectiveness using compliance plus recurrence, time to containment, overdue critical actions, corrective-action effectiveness, reporting confidence, and independent audit findings; thresholds trigger remediation. | Governance dashboard, data definitions, and threshold-response tests. |
| SAFE-019 | Deteriorating governance metrics require root-cause assessment, accountable owner, deadline, and effectiveness check; repeated/critical failures escalate to independent oversight and proportionate process restrictions. | Remediation workflow and closure evidence. |
| SAFE-020 | Separate incident closure from longer-term prevention tasks; track linked actions with owners, deadlines, risk ratings, effectiveness checks, and escalation for overdue/ineffective actions. | Linked action tracking and effectiveness tests. |
| SAFE-021 | Use risk-based external reporting rules with jurisdiction-aware categories, thresholds, deadlines, owners, evidence, qualified review for uncertain cases, and follow-up tracking. | Approved reporting matrix and case simulations. |
| SAFE-022 | Notify affected patients according to risk-based disclosure criteria and applicable obligations, using authorized personnel, known facts, potential impact, next steps, and follow-up. | Notification protocol and audit evidence. |
| SAFE-023 | Apply predefined critical-audit-finding containment and independent clearance; block affected release/clinical use until formally cleared. | Audit finding workflow and release-gate tests. |
| SAFE-024 | Accept residual risk only through formal risk-tiered authorization, documented justification, predefined limits, restrictions, and reassessment; prohibit acceptance above limits. | Risk register and authorization tests. |
| SAFE-025 | Monitor safety signals, measurement drift, data quality, subgroup performance, adverse events, and corrective-action effectiveness continuously where feasible and through scheduled reviews. | Monitoring specification, alert tests, and review records. |
| SAFE-026 | When performance drifts or subgroup criteria fail, restrict affected consequential uses as needed, preserve verified unaffected capabilities, investigate, and revalidate before restoring use. | Drift/subgroup simulations and reinstatement approvals. |
| SAFE-027 | Authorize new populations and assessments only through population-/intended-use-specific staged validation, defined evidence criteria, clinical review, and documented approval. | Scope registry and gated activation tests. |

## 6. Deployment, integrations, and continuity

| ID | Requirement | Acceptance evidence |
|---|---|---|
| OPS-001 | Treat the current shared camera and in-process runtime as single-consumer/single-process infrastructure; do not claim distributed scalability without a separate design and acceptance test. | Architecture statement and hardware test evidence. |
| OPS-002 | Test Jetson/camera startup, repeated capture failure, recovery/cleanup, shutdown, frame rate, end-to-end latency, persistence, poor visibility, occlusion, multiple people, disconnects, and resource use. | Recorded target-hardware acceptance report. |
| OPS-003 | Govern approved EHR, scheduling, and device integrations with scoped permissions, secure interfaces, data validation, explicit authorization, audit, revocation, and risk-appropriate security/clinical review. | Integration threat model and contract tests. |
| OPS-004 | On integration failure, retry transient failures safely, quarantine invalid/conflicting data, suspend compromised access, prevent unverified external data from driving decisions, escalate by severity, and verify recovery. | Fault-injection tests and recovery evidence. |
| OPS-005 | Assess vendors before approval and continuously by risk; track security/service changes, subcontractors/data use, periodic reassessment, suspension/termination, return, and verified deletion. | Vendor register and reassessment evidence. |
| OPS-006 | Keep production secrets out of source control/logs; configure stable secret key, production mode, HTTPS/secure cookies, public origin, SMTP/TLS, rate limiting/abuse monitoring, backup, retention, logging, and rollback. | Deployment checklist, secret scan, security tests, and recovery drill. |
| OPS-007 | Run staged releases: internal technical tests, healthy-adult validation, then a separately approved clinical pilot only when evidence and oversight gates pass. | Stage-gate approvals and evidence packages. |
| OPS-008 | Require formal independent review before stage transitions and a multidisciplinary authorization board for clinical pilots. | Signed approval and conflict-of-interest records. |
| OPS-009 | Produce a release evidence package for every clinical release, including risk analysis, test evidence, validation, traceability, approvals, and additional review for high-risk changes. | Versioned release package and release-blocking checks. |
| OPS-010 | Keep automated progression labels advisory and unvalidated until appropriate clinical evidence and domain approval support consequential use. | UI/API restrictions and release evidence. |

## 7. Safety decision record — Questions 87–101

These explicit decisions are mandatory policy requirements for implementation:

- **Q87 — Prioritization:** Rank signals by clinical risk using potential severity, likelihood, affected population, exposure, evidence strength, and existing-control failure; credible critical risks escalate immediately; incident count alone does not determine priority.
- **Q88 — Investigation threshold:** Investigate when predefined severity, plausibility, exposure, or control-failure criteria are met, even with incomplete evidence.
- **Q89 — Closure authority:** Independent review for routine cases; multidisciplinary safety-board approval for serious/critical cases.
- **Q90 — Unknown root cause:** Document gaps/competing explanations, retain proportionate restrictions, assign follow-up and deadline, require authorized sign-off.
- **Q91 — Reopening:** Predefined triggers for new evidence, recurrence, ineffective corrective actions, or changed exposure; immediate reopening for credible critical risk.
- **Q92 — Cross-case signals:** Coordinate potentially related cases, preserve separate records, assign a coordinating owner, assess aggregate risk, and restrict proportionately.
- **Q93 — Systemic escalation:** Predefined severity, breadth, shared-mechanism, control-failure, and credible critical-risk triggers; do not wait for widespread confirmed harm.
- **Q94 — Emergency restrictions:** Delegated temporary authority for authorized clinical-safety, engineering, and security leads; critical triggers allow immediate containment with prompt independent review.
- **Q95 — Leadership disagreement:** Maintain a proportionate safe interim state and escalate by a defined deadline to independent multidisciplinary authority; expedite critical cases.
- **Q96 — Conflicts of interest:** Disclose, recuse, independently review consequential decisions, and prohibit conflicted self-clearance.
- **Q97 — Release pressure:** Non-waivable release-blocking safety/validity gates; narrowly controlled exceptions only for predefined noncritical requirements.
- **Q98 — Protected reporting:** Confidential channels, independent escalation, non-retaliation protections, outcome tracking, and retaliation review.
- **Q99 — Response timeliness:** Severity-based acknowledgment/triage/escalation/review service levels, overdue tracking, automatic escalation for missed critical deadlines.
- **Q100 — Governance effectiveness:** Outcome-based assurance combining compliance, recurrence, containment time, overdue actions, corrective-action effectiveness, reporting confidence, and independent audits.
- **Q101 — Governance deterioration:** Threshold-triggered root-cause assessment, accountable remediation owner/deadline/effectiveness check, independent escalation for repeated/critical failures, and risk-proportionate restrictions.

## 8. Implementation and evidence tracking

Use these statuses for every requirement; do not mark a requirement complete solely because it is documented:

- **Not assessed:** No current implementation/evidence review.
- **Missing:** Required control or capability is absent.
- **Partially implemented:** Some behavior exists but does not meet all acceptance criteria.
- **Implemented, unverified:** Code/configuration exists but required tests or external evidence are missing.
- **Verified in software:** Relevant automated tests and code review pass.
- **Externally validated:** Required clinical, hardware, security, or independent-review evidence is accepted.
- **Blocked:** Depends on a policy decision, evidence, approval, or infrastructure that is not yet available.

For each requirement, the implementation tracker must capture owner, affected files/routes, risk tier, acceptance criteria, automated tests, external evidence, reviewer/approver, status, residual risk, and next action. Add explicit trace links from release gates to requirements, test results, validation artifacts, and approvals.

## 9. Required next engineering sequence

1. Inventory all routes, APIs, persistence paths, runtime capabilities, model/assessment flows, and existing tests.
2. Map existing behavior to this baseline without presuming it is absent or compliant.
3. Prioritize authorization/isolation and clinical-safety enforcement; implement regression tests for every protected path.
4. Build the incident/safety-signal and corrective-action workflow with role separation, deadlines, auditability, cross-case links, and release restrictions.
5. Add data-integrity, backup/recovery, model/plan versioning, and rollback verification.
6. Close software-level gates with CI and code review.
7. Keep Jetson/camera performance and movement-measurement clinical validation open until evidence is collected on representative hardware/recordings.
8. Maintain a requirements-to-test traceability report and a release checklist; do not claim clinical readiness until every applicable gate has accepted evidence.
