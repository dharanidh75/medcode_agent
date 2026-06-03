"""
api/ocr.py
───────────
POST /api/v1/ocr-upload

Pipeline:
  1. Accept image/PDF via multipart form-data
  2. Run PaddleOCR v3 to extract raw text
  3. Pass raw text to Groq LLM to map it into the React formData schema
  4. Return normalized JSON that the frontend can call setFormData() with
"""
import io
import json
import logging
import tempfile
import os
from fastapi import APIRouter, UploadFile, File, HTTPException
from langchain_groq import ChatGroq
from langchain_core.messages import SystemMessage, HumanMessage
from schemas.medcode import OCRAutoFillResponse
from core.config import settings

logger = logging.getLogger(__name__)
router = APIRouter()

OCR_PARSE_SYSTEM_PROMPT = """You are a medical document parser.

You will receive raw text extracted from a scanned medical note, chart, or insurance form.
Your task is to map the content into a strict JSON schema that matches a medical coding form.

STRICT OUTPUT FORMAT — Respond with ONLY valid JSON, no markdown, no preamble:
{
  "hospitalName": "extracted or empty string",
  "doctorName": "extracted or empty string",
  "patientName": "extracted or empty string",
  "patientDob": "YYYY-MM-DD format or empty string",
  "patientGender": "Male or Female or Other or empty string",
  "insuranceProvider": "extracted or empty string",
  "insuranceNo": "extracted policy/insurance number or empty string",
  "groupNo": "extracted group number or empty string",
  "clinicalNotes": "extracted clinical narrative, diagnoses, and procedures as a single paragraph"
}

Rules:
- If a field cannot be confidently extracted, return an empty string "" for that field
- For patientDob: convert any date format to YYYY-MM-DD. If ambiguous, return ""
- For patientGender: normalize to "Male", "Female", or "Other" only
- clinicalNotes should be a coherent clinical summary, not a list
- Never invent or hallucinate values not present in the source text"""


def run_paddleocr(file_bytes: bytes, file_extension: str) -> str:
    """
    Run PaddleOCR on the uploaded file and return extracted text.
    Handles both image files and PDFs.
    """
    try:
        from paddleocr import PaddleOCR
    except ImportError:
        raise HTTPException(
            status_code=500,
            detail="PaddleOCR is not installed. Run: pip install paddleocr paddlepaddle",
        )

    # Write to a temp file (PaddleOCR needs a file path)
    with tempfile.NamedTemporaryFile(
        suffix=f".{file_extension}", delete=False
    ) as tmp:
        tmp.write(file_bytes)
        tmp_path = tmp.name

    try:
        ocr = PaddleOCR(lang="en", use_gpu=False, show_log=False)
        result = ocr.ocr(tmp_path, cls=True)

        # Flatten results: result is a list of pages, each page is a list of [bbox, [text, confidence]]
        lines = []
        if result:
            for page in result:
                if page:
                    for line in page:
                        text_block = line[1]
                        if text_block and text_block[1] > 0.5:  # Confidence threshold
                            lines.append(text_block[0])

        return "\n".join(lines)

    finally:
        os.unlink(tmp_path)  # Clean up temp file


@router.post("/ocr-upload", response_model=OCRAutoFillResponse)
async def ocr_upload(file: UploadFile = File(...)) -> OCRAutoFillResponse:
    """
    Accepts an image or PDF upload, runs PaddleOCR, and returns
    a normalized JSON payload matching the React formData schema.
    """
    # Validate file type
    allowed_types = {
        "image/jpeg", "image/jpg", "image/png", "image/tiff",
        "image/bmp", "image/webp", "application/pdf",
    }
    if file.content_type not in allowed_types:
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported file type: {file.content_type}. Accepted: JPEG, PNG, TIFF, BMP, WEBP, PDF",
        )

    logger.info(f"[OCR] Processing upload: {file.filename} ({file.content_type})")

    # Read file bytes
    file_bytes = await file.read()
    if len(file_bytes) > 20 * 1024 * 1024:  # 20MB limit
        raise HTTPException(status_code=413, detail="File too large. Maximum size is 20MB.")

    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else "jpg"

    # --- Step 1: PaddleOCR text extraction ---
    try:
        raw_text = run_paddleocr(file_bytes, ext)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[OCR] PaddleOCR failed: {e}")
        raise HTTPException(status_code=500, detail=f"OCR processing failed: {str(e)}")

    if not raw_text.strip():
        return OCRAutoFillResponse(
            success=False,
            data={k: "" for k in [
                "hospitalName", "doctorName", "patientName", "patientDob",
                "patientGender", "insuranceProvider", "insuranceNo", "groupNo", "clinicalNotes"
            ]},
            message="OCR could not extract any text from the uploaded file.",
        )

    logger.info(f"[OCR] Extracted {len(raw_text)} characters of raw text.")

    # --- Step 2: LLM structural parsing ---
    llm = ChatGroq(
        model=settings.GROQ_MODEL,
        api_key=settings.GROQ_API_KEY,
        temperature=0.0,
        max_tokens=1024,
    )

    messages = [
        SystemMessage(content=OCR_PARSE_SYSTEM_PROMPT),
        HumanMessage(content=f"Raw OCR Text:\n\n{raw_text[:4000]}"),  # Truncate to context limit
    ]

    try:
        response = llm.invoke(messages)
        raw_content = response.content.strip()

        if raw_content.startswith("```"):
            raw_content = raw_content.split("```")[1]
            if raw_content.startswith("json"):
                raw_content = raw_content[4:]
            raw_content = raw_content.strip()

        parsed_data: dict = json.loads(raw_content)

        # Ensure all formData keys are present
        expected_keys = [
            "hospitalName", "doctorName", "patientName", "patientDob",
            "patientGender", "insuranceProvider", "insuranceNo", "groupNo", "clinicalNotes"
        ]
        for key in expected_keys:
            if key not in parsed_data:
                parsed_data[key] = ""

        logger.info(f"[OCR] ✓ Successfully parsed into formData schema.")
        return OCRAutoFillResponse(
            success=True,
            data=parsed_data,
            raw_text_preview=raw_text[:300] + "..." if len(raw_text) > 300 else raw_text,
            message="Document parsed successfully. Please review and correct any fields.",
        )

    except (json.JSONDecodeError, Exception) as e:
        logger.error(f"[OCR] LLM parsing failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"LLM structural parsing failed: {str(e)}",
        )