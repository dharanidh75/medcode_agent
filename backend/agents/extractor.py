"""
agents/extractor.py
────────────────────
Node 1 of the LangGraph pipeline.

Receives the raw clinical notes from formData and uses a structured
LLM prompt to extract four concept buckets:
  - symptoms
  - diagnoses
  - procedures
  - medications

Returns: updated MedCodeAgentState with populated concept lists.
"""
import json
import logging
from langchain_groq import ChatGroq
from langchain_core.messages import SystemMessage, HumanMessage
from schemas.medcode import MedCodeAgentState
from core.config import settings

logger = logging.getLogger(__name__)

EXTRACTOR_SYSTEM_PROMPT = """You are a Clinical Natural Language Processing (NLP) engine.

Your ONLY task is to parse the clinical notes provided and extract medical concepts into
exactly four structured categories.

STRICT OUTPUT FORMAT — Respond with ONLY valid JSON, no markdown, no preamble, no explanation:
{
  "symptoms": ["list of symptom strings"],
  "diagnoses": ["list of diagnosis strings"],
  "procedures": ["list of procedure strings"],
  "medications": ["list of medication strings"]
}

Rules:
- Use standard clinical terminology (e.g. "acute appendicitis", not "bad stomach pain")
- Each string should be a concise, searchable medical term
- If a category has no findings, return an empty list []
- Never invent findings not present in the notes
- Never include JSON fences or extra text — raw JSON only"""


def extractor_node(state: MedCodeAgentState) -> MedCodeAgentState:
    """
    LangGraph node: Extracts structured medical entities from clinical notes.
    """
    logger.info("[Extractor] Starting concept extraction from clinical notes...")

    llm = ChatGroq(
        model=settings.GROQ_MODEL,
        api_key=settings.GROQ_API_KEY,
        temperature=0.0,  # Deterministic extraction
        max_tokens=1024,
    )

    clinical_notes = state.form_data.clinicalNotes
    messages = [
        SystemMessage(content=EXTRACTOR_SYSTEM_PROMPT),
        HumanMessage(content=f"Clinical Notes:\n{clinical_notes}"),
    ]

    try:
        response = llm.invoke(messages)
        raw_content = response.content.strip()

        # Strip accidental markdown fences if the model disobeys
        if raw_content.startswith("```"):
            raw_content = raw_content.split("```")[1]
            if raw_content.startswith("json"):
                raw_content = raw_content[4:]
            raw_content = raw_content.strip()

        extracted = json.loads(raw_content)

        state.symptoms = extracted.get("symptoms", [])
        state.diagnoses = extracted.get("diagnoses", [])
        state.procedures = extracted.get("procedures", [])
        state.medications = extracted.get("medications", [])

        logger.info(
            f"[Extractor] ✓ Extracted — "
            f"symptoms: {len(state.symptoms)}, "
            f"diagnoses: {len(state.diagnoses)}, "
            f"procedures: {len(state.procedures)}, "
            f"medications: {len(state.medications)}"
        )

    except (json.JSONDecodeError, KeyError) as e:
        logger.error(f"[Extractor] Failed to parse LLM response: {e}")
        state.error_message = f"Extractor agent failed: {str(e)}"

    return state