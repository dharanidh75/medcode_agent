"""
api/cases.py
─────────────
Case management endpoints — single-entry workflow only.

GET  /api/v1/cases         — List all cases (optional ?status= filter)
GET  /api/v1/cases/{id}    — Single case by ID
GET  /api/v1/pending       — Cases awaiting manual review
GET  /api/v1/accepted      — Accepted cases
GET  /api/v1/rejected      — Rejected cases
"""
import json
import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select
from schemas.medcode import CaseResponse
from models.case import Case, CaseStatus
from db.database import get_session

logger = logging.getLogger(__name__)
router = APIRouter()


def serialize_case(case: Case) -> dict:
    """
    Convert a Case ORM object to a dict with icd10_codes and cpt_codes
    properly deserialized from JSON strings into Python lists.
    """
    def parse_codes(val):
        if val is None:
            return []
        if isinstance(val, list):
            return val
        try:
            return json.loads(val)
        except (json.JSONDecodeError, TypeError):
            return []

    return {
        "id": case.id,
        "status": case.status,
        "patient_name": case.patient_name,
        "hospital_name": case.hospital_name,
        "doctor_name": case.doctor_name,
        "insurance_provider": case.insurance_provider,
        "insurance_no": case.insurance_no,
        "icd10_codes": parse_codes(case.icd10_codes),
        "cpt_codes": parse_codes(case.cpt_codes),
        "retry_count": case.retry_count,
        "created_at": case.created_at,
        "updated_at": case.updated_at,
    }


@router.get("/cases", response_model=list[CaseResponse])
def list_cases(
    status: CaseStatus | None = None,
    db: Session = Depends(get_session),
):
    query = select(Case)
    if status:
        query = query.where(Case.status == status)
    query = query.order_by(Case.created_at.desc())
    return [serialize_case(c) for c in db.exec(query).all()]


@router.get("/cases/{case_id}", response_model=CaseResponse)
def get_case(case_id: str, db: Session = Depends(get_session)):
    case = db.get(Case, case_id)
    if not case:
        raise HTTPException(status_code=404, detail=f"Case {case_id} not found.")
    return serialize_case(case)


@router.get("/pending", response_model=list[CaseResponse])
def get_pending_cases(db: Session = Depends(get_session)):
    cases = db.exec(
        select(Case).where(Case.status == CaseStatus.pending).order_by(Case.created_at.desc())
    ).all()
    return [serialize_case(c) for c in cases]


@router.get("/accepted", response_model=list[CaseResponse])
def get_accepted_cases(db: Session = Depends(get_session)):
    cases = db.exec(
        select(Case).where(Case.status == CaseStatus.accepted).order_by(Case.updated_at.desc())
    ).all()
    return [serialize_case(c) for c in cases]


@router.get("/rejected", response_model=list[CaseResponse])
def get_rejected_cases(db: Session = Depends(get_session)):
    cases = db.exec(
        select(Case).where(Case.status == CaseStatus.rejected).order_by(Case.updated_at.desc())
    ).all()
    return [serialize_case(c) for c in cases]