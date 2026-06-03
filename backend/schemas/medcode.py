from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any  # Any kept for PipelineEvent data field
from datetime import datetime
from models.case import CaseStatus


# -------------------------------------------------------
# Inbound: matches React formData keys exactly
# -------------------------------------------------------

class FormData(BaseModel):
    """Mirrors the React formData state object."""
    hospitalName: str = Field(..., min_length=1)
    doctorName: str = Field(..., min_length=1)
    patientName: str = Field(..., min_length=1)
    patientDob: str = Field(..., min_length=1)
    patientGender: str = Field(..., min_length=1)
    insuranceProvider: str = Field(..., min_length=1)
    insuranceNo: str = Field(..., min_length=1)
    groupNo: str = Field(..., min_length=1)
    clinicalNotes: str = Field(..., min_length=1)


# -------------------------------------------------------
# Outbound: OCR auto-fill response
# -------------------------------------------------------

class OCRAutoFillResponse(BaseModel):
    """
    Returned after PaddleOCR + LLM structural parsing.
    All keys correspond directly to React formData keys so
    the frontend can do: setFormData(response.data)
    """
    success: bool
    data: Dict[str, str]
    raw_text_preview: Optional[str] = None
    message: Optional[str] = None


# -------------------------------------------------------
# Outbound: SSE pipeline telemetry events
# -------------------------------------------------------

class PipelineEvent(BaseModel):
    """A single SSE event emitted to the client during pipeline execution."""
    event: str = Field(..., description="Agent step name: 'extractor' | 'coder' | 'validator' | 'complete' | 'error'")
    status: str = Field(..., description="'running' | 'success' | 'failed' | 'retrying'")
    message: str
    data: Optional[Dict[str, Any]] = None
    retry_count: Optional[int] = None


# -------------------------------------------------------
# Outbound: Case response
# -------------------------------------------------------

class CaseResponse(BaseModel):
    id: str
    status: CaseStatus
    patient_name: str
    hospital_name: str
    doctor_name: str
    insurance_provider: str
    insurance_no: str
    icd10_codes: Optional[List[str]] = None
    cpt_codes: Optional[List[str]] = None
    retry_count: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# -------------------------------------------------------
# Internal: LangGraph agent state
# -------------------------------------------------------

class MedCodeAgentState(BaseModel):
    """The shared state object passed between all LangGraph nodes."""
    form_data: FormData
    case_id: Optional[str] = None

    # Extractor output
    symptoms: List[str] = []
    diagnoses: List[str] = []
    procedures: List[str] = []
    medications: List[str] = []

    # Coder output
    proposed_icd10: List[str] = []
    proposed_cpt: List[str] = []

    # Validator output
    validation_passed: bool = False
    validation_errors: List[Dict[str, str]] = []

    # Orchestrator control
    retry_count: int = 0
    max_retries: int = 3
    final_status: Optional[str] = None
    error_message: Optional[str] = None

    class Config:
        arbitrary_types_allowed = True