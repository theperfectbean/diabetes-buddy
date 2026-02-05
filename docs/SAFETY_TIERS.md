# Evidence-Graded Safety Model (Tiered Auditor)

## Why the tiered model exists
The safety auditor now balances clinical utility with evidence-based safeguards. Diabetes self-management education and support (DSMES) explicitly aims to build knowledge, decision-making, and skills for self-care, which requires practical guidance rather than blanket blocking. The OpenAPS community demonstrates safety-focused design for autonomous insulin adjustments within defined boundaries, and clinical decision support (CDS) is intended to deliver timely, patient-specific information that enhances decision-making.

**Evidence sources:**
- ADA Standards of Care (DSMES recommendations emphasize knowledge, decision-making, and skills mastery for self-care): https://diabetesjournals.org/care/article/46/Supplement_1/S68/148082/5-Facilitating-Behavior-Change-and-Well
- OpenAPS safety-focused reference design and safe automation context: https://openaps.org/
- CDS definition and patient-centered CDS supporting decision-making: https://www.healthit.gov/topic/safety/clinical-decision-support

## Tier definitions
### Tier 1 — Evidence-Based Education
**Goal:** Allow guidance anchored in authoritative sources (ADA standards, OpenAPS documentation, device manuals), especially for education about ranges, targets, and safe practices.
**Allow:** General best practices, safe ranges, and evidence-based explanations with citations.
**Disallow:** Specific unit dosing or unsafe targets.

### Tier 2 — Personalized Analysis
**Goal:** Provide safe pattern analysis based on personal data (e.g., Glooko), with cautious, testable adjustments.
**Allow:** Pattern analysis and small adjustments (≤20%) with monitoring/testing protocols.
**Disallow:** Large or untested adjustments, or clinical decisions that require clinician oversight.

### Tier 3 — Clinical Decisions (Defer)
**Goal:** Defer decisions that require clinician oversight with a clear explanation of why.
**Examples:** Starting/stopping medication, changing prescriptions, pregnancy-related insulin management.
**Response pattern:** Explain that the decision depends on medical history, labs, and risk of hypoglycemia, and should be made with a clinician.

### Tier 4 — Dangerous Advice (Block)
**Goal:** Block genuinely unsafe instructions.
**Examples:** Skipping insulin, unsafe A1C targets, specific unit dosing without clinician oversight.
**Response pattern:** Provide a brief safety explanation and direct the user to seek appropriate care.

## Implementation summary
- **Classification rules:** Implemented in [agents/safety_tiers.py](../agents/safety_tiers.py).
- **Safety auditing:** Tier decision is applied in [agents/safety.py](../agents/safety.py), which may override responses for Tier 3/4 and append tier-specific disclaimers.
- **API formatting:** Responses now surface tier-specific disclaimers in [web/app.py](../web/app.py).

## Success criteria mapping
- **Basal adjustment query** → Tier 1 educational guidance with evidence markers (OpenAPS/ADA).
- **Breakfast spikes with Glooko data** → Tier 2 personalized analysis with ≤20% testable adjustments.
- **Stopping medication** → Tier 3 deferral with a clear explanation of why clinician input is required.
- **Dangerous A1C target** → Tier 4 block with safety reasoning.
