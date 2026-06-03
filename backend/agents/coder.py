"""
agents/coder.py
───────────────
Node 2 of the LangGraph pipeline.

RAG-Driven Code Assignment:
1. Converts each extracted medical concept into a search query
2. Runs semantic similarity retrieval against ChromaDB (no weight fine-tuning)
3. Passes retrieved candidates to the LLM as context
4. LLM selects the best valid code(s) from the candidates

CONSTRAINT: The LLM is NEVER asked to generate codes from memory.
It ONLY selects from the retrieved ChromaDB candidates — ensuring
all output codes are valid, existing alphanumeric healthcare strings.
"""
import json
import logging
from langchain_groq import ChatGroq
from langchain_core.messages import SystemMessage, HumanMessage
from schemas.medcode import MedCodeAgentState
from db.vector_store import semantic_search_icd10, semantic_search_cpt
from core.config import settings

logger = logging.getLogger(__name__)

CODER_SYSTEM_PROMPT = """You are a certified medical billing and coding specialist (CPC).

You will be given:
1. Extracted medical concepts from a clinical note
2. A set of RAG-retrieved candidate codes from a verified medical code database

Your task is to select the MOST appropriate codes from the provided candidates ONLY.

CRITICAL RULE: You MUST only output codes that appear in the "Candidates" section.
Do NOT generate, invent, or recall codes from memory. Only select from the provided list.

STRICT OUTPUT FORMAT — Respond with ONLY valid JSON, no markdown, no preamble:
{
  "icd10_codes": ["list of selected ICD-10 codes, e.g. K35.80"],
  "cpt_codes": ["list of selected CPT codes, e.g. 44950"],
  "reasoning": "brief one-sentence justification"
}

Selection rules:
- Select 1-3 ICD-10 codes that best match the diagnoses
- Select 1-3 CPT codes that best match the procedures performed
- If a concept has no suitable candidate match (distance > 0.6), omit it
- Prefer more specific codes over general ones"""


def _build_rag_context(state: MedCodeAgentState) -> tuple[str, str]:
    """
    Query ChromaDB for ICD-10 and CPT candidates based on extracted concepts.
    Returns (icd10_context, cpt_context) as formatted strings for the prompt.
    """
    # Build diagnosis queries from symptoms + diagnoses
    diagnosis_queries = state.diagnoses + state.symptoms[:3]

    # CPT queries: use procedures first, fall back to diagnoses if empty
    # (diagnoses imply standard procedures, e.g. appendicitis → appendectomy)
    procedure_queries = state.procedures + state.medications[:2]
    if not procedure_queries:
        procedure_queries = state.diagnoses[:3]

    # --- ICD-10 retrieval ---
    icd10_candidates: list[dict] = []
    seen_icd_codes = set()
    for query in diagnosis_queries:
        if not query:
            continue
        results = semantic_search_icd10(query, n_results=3)
        for r in results:
            if r["code"] not in seen_icd_codes and r["distance"] < 0.65:
                icd10_candidates.append(r)
                seen_icd_codes.add(r["code"])

    # --- CPT retrieval ---
    cpt_candidates: list[dict] = []
    seen_cpt_codes = set()
    for query in procedure_queries:
        if not query:
            continue
        results = semantic_search_cpt(query, n_results=3)
        for r in results:
            if r["code"] not in seen_cpt_codes and r["distance"] < 0.85:
                cpt_candidates.append(r)
                seen_cpt_codes.add(r["code"])

    # Format for prompt
    icd10_lines = "\n".join(
        f"  - {c['code']}: {c['description']} (similarity: {1 - c['distance']:.2f})"
        for c in sorted(icd10_candidates, key=lambda x: x["distance"])[:8]
    )
    cpt_lines = "\n".join(
        f"  - {c['code']}: {c['description']} (similarity: {1 - c['distance']:.2f})"
        for c in sorted(cpt_candidates, key=lambda x: x["distance"])[:8]
    )

    return icd10_lines or "  (no strong ICD-10 matches found)", cpt_lines or "  (no strong CPT matches found)"


def coder_node(state: MedCodeAgentState) -> MedCodeAgentState:
    """
    LangGraph node: RAG-driven code assignment via ChromaDB + Groq LLM.
    """
    logger.info(f"[Coder] Starting RAG code assignment (attempt {state.retry_count + 1})...")

    # Retrieve candidates from ChromaDB
    icd10_context, cpt_context = _build_rag_context(state)

    # Build the user message with full context
    user_message = f"""Clinical Summary:
- Symptoms: {', '.join(state.symptoms) or 'None documented'}
- Diagnoses: {', '.join(state.diagnoses) or 'None documented'}
- Procedures: {', '.join(state.procedures) or 'None documented'}
- Medications: {', '.join(state.medications) or 'None documented'}

ICD-10 Candidates (from verified database):
{icd10_context}

CPT Candidates (from verified database):
{cpt_context}

Validation Errors from previous attempt (if any):
{state.validation_errors if state.validation_errors else 'None — first attempt'}

Select the best codes from the candidates above."""

    llm = ChatGroq(
        model=settings.GROQ_MODEL,
        api_key=settings.GROQ_API_KEY,
        temperature=0.1,
        max_tokens=512,
    )

    messages = [
        SystemMessage(content=CODER_SYSTEM_PROMPT),
        HumanMessage(content=user_message),
    ]

    try:
        response = llm.invoke(messages)
        raw_content = response.content.strip()

        # Strip accidental markdown
        if raw_content.startswith("```"):
            raw_content = raw_content.split("```")[1]
            if raw_content.startswith("json"):
                raw_content = raw_content[4:]
            raw_content = raw_content.strip()

        coded = json.loads(raw_content)

        state.proposed_icd10 = coded.get("icd10_codes", [])
        state.proposed_cpt = coded.get("cpt_codes", [])
        # Clear previous validation errors before next validation pass
        state.validation_errors = []

        logger.info(
            f"[Coder] ✓ Proposed ICD-10: {state.proposed_icd10} | CPT: {state.proposed_cpt}"
        )

    except (json.JSONDecodeError, KeyError) as e:
        logger.error(f"[Coder] Failed to parse LLM response: {e}")
        state.error_message = f"Coder agent failed: {str(e)}"
        state.proposed_icd10 = []
        state.proposed_cpt = []

    return state