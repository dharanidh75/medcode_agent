from sqlmodel import SQLModel, Field, Column
from sqlalchemy import Text, JSON
from typing import Optional, List
from datetime import datetime
from enum import Enum
import uuid


class CaseStatus(str, Enum):
    pending = "pending"
    accepted = "accepted"
    rejected = "rejected"
    processing = "processing"


class Case(SQLModel, table=True):
    """
    Core case record: patient demographics, assigned codes,
    raw clinical notes, and a status enum flag.
    """
    __tablename__ = "cases"

    id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        primary_key=True,
        index=True,
    )

    # --- Administrative fields (mirror React formData) ---
    hospital_name: str = Field(max_length=255)
    doctor_name: str = Field(max_length=255)
    patient_name: str = Field(max_length=255)
    patient_dob: str = Field(max_length=20)
    patient_gender: str = Field(max_length=20)
    insurance_provider: str = Field(max_length=255)
    insurance_no: str = Field(max_length=100)
    group_no: str = Field(max_length=100)

    # --- Clinical content ---
    clinical_notes: str = Field(sa_column=Column(Text))

    # --- Assigned codes (stored as JSON array strings) ---
    icd10_codes: Optional[str] = Field(
        default=None,
        sa_column=Column(JSON),
        description="List of assigned ICD-10 codes, e.g. ['K35.80']",
    )
    cpt_codes: Optional[str] = Field(
        default=None,
        sa_column=Column(JSON),
        description="List of assigned CPT codes, e.g. ['44950']",
    )

    # --- Pipeline metadata ---
    status: CaseStatus = Field(default=CaseStatus.processing)
    retry_count: int = Field(default=0)
    source: str = Field(default="manual", description="manual | ocr")

    # --- Timestamps ---
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class ValidationError(SQLModel, table=True):
    """
    Captures systemic log traces whenever the multi-agent
    critic chain triggers a retry loop or marks a case rejected.
    """
    __tablename__ = "validation_errors"

    id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        primary_key=True,
        index=True,
    )

    case_id: str = Field(foreign_key="cases.id", index=True)
    retry_attempt: int = Field(description="Which retry number triggered this log")

    # The specific validation failure trace from the Validator Agent
    error_type: str = Field(max_length=100, description="e.g. 'code_mismatch', 'missing_insurance_field'")
    error_detail: str = Field(sa_column=Column(Text))

    # The raw code proposals that failed validation
    proposed_codes: Optional[str] = Field(
        default=None,
        sa_column=Column(JSON),
    )

    created_at: datetime = Field(default_factory=datetime.utcnow)