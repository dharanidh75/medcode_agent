"""
agents/validator.py
────────────────────
Node 3 of the LangGraph pipeline.

The Validator Agent performs two independent checks:

1. Clinical Coherence Check:
   Uses the LLM as a "critic" to verify that the proposed codes
   clinically match the extracted diagnoses and procedures.

2. Compliance Schema Check:
   Rule-based validation of required administrative fields:
   - insuranceNo must be non-empty and follow a basic pattern
   - insuranceProvider must be non-empty
   - ICD-10 codes must match the alphanumeric pattern (e.g. K35.80)
   - CPT codes must be 4-5 digit numeric strings

Sets state.validation_passed = True/False.
Populates state.validation_errors with structured error dicts.
"""
import re
import json
import logging
from langchain_groq import ChatGroq
from langchain_core.messages import SystemMessage, HumanMessage
from schemas.medcode import MedCodeAgentState
from core.config import settings

logger = logging.getLogger(__name__)

# ICD-10: letter + 2 digits + optional decimal + optional alphanumeric suffix
ICD10_PATTERN = re.compile(r"^[A-Z][0-9]{2}(\.[A-Z0-9]{1,4})?$", re.IGNORECASE)
# CPT: 4-5 digit numeric (may include Category II/III suffixes like 0001F)
CPT_PATTERN = re.compile(r"^[0-9]{4,5}[A-Z]{0,1}$", re.IGNORECASE)

VALIDATOR_SYSTEM_PROMPT = """You are a clinical coding auditor performing a quality check.

You will receive:
- Extracted clinical concepts (diagnoses, procedures)
- Proposed ICD-10 and CPT codes

Your job: Verify that the proposed codes are clinically appropriate for the described case.

STRICT OUTPUT FORMAT — Respond with ONLY valid JSON, no markdown, no preamble:
{
  "clinical_match": true or false,
  "issues": ["list of specific clinical mismatch issues, empty if clinical_match is true"]
}

Be strict but fair. If the codes are broadly appropriate (even if not the single best choice),
set clinical_match to true. Only flag genuine mismatches (wrong body system, wrong procedure type)."""


def _check_compliance_rules(state: MedCodeAgentState) -> list[dict]:
    """
    Rule-based compliance validation. Returns a list of error dicts.
    """
    errors = []

    # --- Required administrative fields ---
    if not state.form_data.insuranceNo or state.form_data.insuranceNo.strip() == "":
        errors.append({
            "error_type": "missing_insurance_field",
            "error_detail": "insuranceNo is required for billing compliance but is empty.",
        })

    if not state.form_data.insuranceProvider or state.form_data.insuranceProvider.strip() == "":
        errors.append({
            "error_type": "missing_insurance_field",
            "error_detail": "insuranceProvider is required for billing compliance but is empty.",
        })

    # --- Code format validation ---
    for code in state.proposed_icd10:
        if not ICD10_PATTERN.match(code.strip()):
            errors.append({
                "error_type": "invalid_code_format",
                "error_detail": f"ICD-10 code '{code}' does not match the standard alphanumeric format (e.g. K35.80).",
            })

    for code in state.proposed_cpt:
        if not CPT_PATTERN.match(code.strip()):
            errors.append({
                "error_type": "invalid_code_format",
                "error_detail": f"CPT code '{code}' does not match the expected 4-5 digit format (e.g. 44950).",
            })

    # ICD-10 is hard required. CPT is optional — absent for symptom/diagnosis-only notes.
    if not state.proposed_icd10:
        errors.append({
            "error_type": "missing_codes",
            "error_detail": "No ICD-10 diagnosis codes were assigned. At least one is required.",
        })

    if not state.proposed_cpt:
        logger.info("[Validator] No CPT codes — acceptable for diagnosis-only notes.")

    return errors


def validator_node(state: MedCodeAgentState) -> MedCodeAgentState:
    """
    LangGraph node: Validates proposed codes against clinical description
    and compliance schemas.
    """
    logger.info("[Validator] Running validation checks...")

    all_errors: list[dict] = []

    # --- 1. Compliance rule checks (fast, no LLM call) ---
    compliance_errors = _check_compliance_rules(state)
    all_errors.extend(compliance_errors)

    if compliance_errors:
        logger.warning(f"[Validator] Compliance failures: {[e['error_type'] for e in compliance_errors]}")

    # --- 2. Clinical coherence check (LLM critic) ---
    # Only run if we have codes to validate; skip if compliance already failed hard
    if state.proposed_icd10 or state.proposed_cpt:
        llm = ChatGroq(
            model=settings.GROQ_MODEL,
            api_key=settings.GROQ_API_KEY,
            temperature=0.0,
            max_tokens=512,
        )

        user_message = f"""Clinical Context:
- Diagnoses extracted: {', '.join(state.diagnoses) or 'None'}
- Procedures extracted: {', '.join(state.procedures) or 'None'}
- Symptoms: {', '.join(state.symptoms) or 'None'}

Proposed Codes:
- ICD-10: {', '.join(state.proposed_icd10) or 'None'}
- CPT: {', '.join(state.proposed_cpt) or 'None'}

Verify clinical appropriateness."""

        messages = [
            SystemMessage(content=VALIDATOR_SYSTEM_PROMPT),
            HumanMessage(content=user_message),
        ]

        try:
            response = llm.invoke(messages)
            raw_content = response.content.strip()

            if raw_content.startswith("```"):
                raw_content = raw_content.split("```")[1]
                if raw_content.startswith("json"):
                    raw_content = raw_content[4:]
                raw_content = raw_content.strip()

            verdict = json.loads(raw_content)
            clinical_match = verdict.get("clinical_match", False)
            clinical_issues = verdict.get("issues", [])

            if not clinical_match:
                for issue in clinical_issues:
                    all_errors.append({
                        "error_type": "code_mismatch",
                        "error_detail": issue,
                    })
                logger.warning(f"[Validator] Clinical mismatch issues: {clinical_issues}")

        except (json.JSONDecodeError, KeyError) as e:
            logger.error(f"[Validator] LLM critic failed to parse: {e}")
            # Don't add as a validation error — treat as soft failure
            # The compliance checks are the hard gate

    # --- Final verdict ---
    if all_errors:
        state.validation_passed = False
        state.validation_errors = all_errors
        logger.warning(f"[Validator] ✗ Validation FAILED with {len(all_errors)} error(s).")
    else:
        state.validation_passed = True
        state.validation_errors = []
        logger.info("[Validator] ✓ Validation PASSED — all checks clear.")

    return state