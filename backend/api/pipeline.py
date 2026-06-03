"""
api/pipeline.py
────────────────
POST /api/v1/execute-pipeline

Streams LangGraph agent telemetry back to the React client via
Server-Sent Events (SSE). Each agent node transition emits an event.

On completion:
  - Persists the case to PostgreSQL with final status
  - Logs any validation errors to the validation_errors table
"""
import json
import logging
import asyncio
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sse_starlette.sse import EventSourceResponse
from sqlmodel import Session
from schemas.medcode import FormData, MedCodeAgentState
from models.case import Case, CaseStatus, ValidationError as ValidationErrorModel
from db.database import get_session
from agents.graph import medcode_graph
from core.config import settings
import uuid

logger = logging.getLogger(__name__)
router = APIRouter()


async def run_pipeline_stream(form_data: FormData, db: Session):
    """
    Async generator that:
    1. Creates a pending DB case record
    2. Runs the LangGraph pipeline synchronously (in thread pool)
    3. Streams SSE events for each phase
    4. Persists final results to PostgreSQL
    """
    case_id = str(uuid.uuid4())

    # --- Create initial DB record ---
    case = Case(
        id=case_id,
        hospital_name=form_data.hospitalName,
        doctor_name=form_data.doctorName,
        patient_name=form_data.patientName,
        patient_dob=form_data.patientDob,
        patient_gender=form_data.patientGender,
        insurance_provider=form_data.insuranceProvider,
        insurance_no=form_data.insuranceNo,
        group_no=form_data.groupNo,
        clinical_notes=form_data.clinicalNotes,
        status=CaseStatus.processing,
        source="manual",
    )
    db.add(case)
    db.commit()
    db.refresh(case)

    logger.info(f"[Pipeline] Case {case_id} created. Starting agent graph...")

    # --- Emit: Pipeline started ---
    yield {
        "event": "pipeline_start",
        "data": json.dumps({
            "event": "pipeline_start",
            "status": "running",
            "message": f"Pipeline initiated for patient: {form_data.patientName}",
            "data": {"case_id": case_id},
        }),
    }
    await asyncio.sleep(0)

    # --- Emit: Extractor starting ---
    yield {
        "event": "extractor",
        "data": json.dumps({
            "event": "extractor",
            "status": "running",
            "message": "Extractor Agent: Parsing clinical notes for medical concepts...",
        }),
    }
    await asyncio.sleep(0)

    # --- Run LangGraph (blocking — run in thread pool for async compat) ---
    initial_state = MedCodeAgentState(
        form_data=form_data,
        case_id=case_id,
        max_retries=settings.MAX_AGENT_RETRIES,
    ).dict()

    loop = asyncio.get_event_loop()
    try:
        final_state_dict = await loop.run_in_executor(
            None,
            lambda: medcode_graph.invoke(initial_state)
        )
        final_state = MedCodeAgentState(**final_state_dict)
    except Exception as e:
        import traceback
        logger.error(f"[Pipeline] Graph execution error: {e}")
        logger.error(traceback.format_exc())
        yield {
            "event": "error",
            "data": json.dumps({
                "event": "error",
                "status": "failed",
                "message": f"Pipeline execution error: {str(e)}",
            }),
        }
        try:
            case.status = CaseStatus.rejected
            case.updated_at = datetime.utcnow()
            db.add(case)
            db.commit()
        except Exception:
            pass
        return

    # --- Emit: Extractor complete ---
    yield {
        "event": "extractor",
        "data": json.dumps({
            "event": "extractor",
            "status": "success",
            "message": "Extractor Agent: Concepts extracted successfully.",
            "data": {
                "symptoms": final_state.symptoms,
                "diagnoses": final_state.diagnoses,
                "procedures": final_state.procedures,
                "medications": final_state.medications,
            },
        }),
    }
    await asyncio.sleep(0)

    # --- Emit: Coder complete ---
    yield {
        "event": "coder",
        "data": json.dumps({
            "event": "coder",
            "status": "success" if final_state.proposed_icd10 else "failed",
            "message": f"Coder Agent: Assigned {len(final_state.proposed_icd10)} ICD-10 and {len(final_state.proposed_cpt)} CPT codes via RAG lookup.",
            "data": {
                "icd10_codes": final_state.proposed_icd10,
                "cpt_codes": final_state.proposed_cpt,
            },
        }),
    }
    await asyncio.sleep(0)

    # --- Emit: Validator result ---
    validator_status = "success" if final_state.validation_passed else "failed"
    yield {
        "event": "validator",
        "data": json.dumps({
            "event": "validator",
            "status": validator_status,
            "message": "Validator Agent: All checks passed." if final_state.validation_passed else f"Validator Agent: {len(final_state.validation_errors)} issue(s) found.",
            "retry_count": final_state.retry_count,
            "data": {
                "validation_errors": final_state.validation_errors,
            },
        }),
    }
    await asyncio.sleep(0)

    # --- Persist final state to PostgreSQL ---
    final_status = CaseStatus.accepted if final_state.final_status == "accepted" else CaseStatus.pending

    case.status = final_status
    case.icd10_codes = json.dumps(final_state.proposed_icd10)
    case.cpt_codes = json.dumps(final_state.proposed_cpt)
    case.retry_count = final_state.retry_count
    case.updated_at = datetime.utcnow()
    db.add(case)

    # --- Log validation errors to DB ---
    for attempt_idx, error in enumerate(final_state.validation_errors):
        err_record = ValidationErrorModel(
            case_id=case_id,
            retry_attempt=final_state.retry_count,
            error_type=error.get("error_type", "unknown"),
            error_detail=error.get("error_detail", ""),
            proposed_codes=json.dumps({
                "icd10": final_state.proposed_icd10,
                "cpt": final_state.proposed_cpt,
            }),
        )
        db.add(err_record)

    db.commit()
    logger.info(f"[Pipeline] Case {case_id} finalized with status: {final_status}")

    # --- Emit: Final completion event ---
    yield {
        "event": "complete",
        "data": json.dumps({
            "event": "complete",
            "status": final_state.final_status or "pending",
            "message": f"Pipeline complete. Case routed to: {final_state.final_status or 'pending'}",
            "data": {
                "case_id": case_id,
                "final_status": final_state.final_status,
                "icd10_codes": final_state.proposed_icd10,
                "cpt_codes": final_state.proposed_cpt,
            },
        }),
    }


@router.post("/execute-pipeline")
async def execute_pipeline(
    form_data: FormData,
    db: Session = Depends(get_session),
):
    """
    Invokes the LangGraph multi-agent pipeline and streams
    step-by-step telemetry back to the React client via SSE.
    """
    return EventSourceResponse(
        run_pipeline_stream(form_data, db),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",   # disables nginx buffering
            "Connection": "keep-alive",
        },
    )