from fastapi import FastAPI, BackgroundTasks, HTTPException, UploadFile, File, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
import io
try:
    from pypdf import PdfReader
    import pytesseract
    from pdf2image import convert_from_bytes
    from PIL import Image
except ImportError:
    pass
import os
from dotenv import load_dotenv

# Load environment variables explicitly from the backend directory
dotenv_path = os.path.join(os.path.dirname(__file__), ".env")
load_dotenv(dotenv_path)

from pipeline import process_clinical_text, check_local_model_health, supabase

app = FastAPI(title="MedCode Assist Backend")

# Setup CORS - Currently allowing all for local dev, but should be scoped to Vercel domain later
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # TODO: Restrict this to the Vercel frontend domain before production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class SubmitRequest(BaseModel):
    raw_text: str

class CorrectionInput(BaseModel):
    model_config = {'protected_namespaces': ()}
    request_id: str
    original_text_span: Optional[str] = None
    model_code: Optional[str] = None
    coder_corrected_code: Optional[str] = None

class CorrectionsPayload(BaseModel):
    corrections: List[CorrectionInput]

@app.get("/health")
async def health_check():
    """
    Basic health check endpoint.
    """
    return {"status": "ok", "service": "backend"}

@app.post("/process")
async def submit_process(request: SubmitRequest, background_tasks: BackgroundTasks):
    if not supabase:
        raise HTTPException(status_code=500, detail="Supabase client not initialized")
        
    # Check if local model tunnel is healthy first
    is_healthy = await check_local_model_health()
    if not is_healthy:
        raise HTTPException(status_code=503, detail="Local model service tunnel is unreachable or unhealthy.")
        
    # Insert row into Supabase
    try:
        response = supabase.table("requests").insert({
            "raw_input": request.raw_text,
            "status": "pending"
        }).execute()
        
        request_id = response.data[0]["request_id"]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database insert failed: {str(e)}")
        
    # Kick off background task
    background_tasks.add_task(process_clinical_text, request_id, request.raw_text)
    
    return {"request_id": request_id, "status": "pending"}

@app.post("/upload")
async def submit_upload(background_tasks: BackgroundTasks, file: UploadFile = File(...)):
    if not supabase:
        raise HTTPException(status_code=500, detail="Supabase client not initialized")
        
    is_healthy = await check_local_model_health()
    if not is_healthy:
        raise HTTPException(status_code=503, detail="Local model service tunnel is unreachable or unhealthy.")
        
    filename = file.filename
    content = await file.read()
    
    # Extract text based on file type
    extracted_text = ""
    filename_lower = filename.lower()
    
    if filename_lower.endswith(".pdf"):
        try:
            # 1. Try standard text extraction first (fastest)
            reader = PdfReader(io.BytesIO(content))
            for page in reader.pages:
                extracted_text += page.extract_text() + "\n"
                
            # 2. If it's empty (scanned PDF), fallback to OCR
            if not extracted_text.strip():
                print(f"Standard extraction empty for {filename}, falling back to OCR...")
                images = convert_from_bytes(content)
                for img in images:
                    extracted_text += pytesseract.image_to_string(img) + "\n"
                    
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Failed to parse PDF: {str(e)}")
            
    elif filename_lower.endswith((".jpg", ".jpeg", ".png", ".webp")):
        # Image OCR
        try:
            image = Image.open(io.BytesIO(content))
            extracted_text = pytesseract.image_to_string(image)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Failed to extract text from image: {str(e)}")
            
    else:
        # Fallback for plain text or unsupported docs (we'll just try to decode it)
        try:
            extracted_text = content.decode("utf-8")
        except:
            raise HTTPException(status_code=400, detail="Unsupported file format or failed to decode text.")
            
    if not extracted_text.strip():
        raise HTTPException(status_code=400, detail="Could not extract any text from the document. Please ensure it is legible.")
        
    # Insert row into Supabase including filename
    try:
        response = supabase.table("requests").insert({
            "raw_input": extracted_text,
            "filename": filename,
            "status": "pending"
        }).execute()
        
        request_id = response.data[0]["request_id"]
    except Exception as e:
        # If the filename column doesn't exist yet, it will throw an error.
        raise HTTPException(status_code=500, detail=f"Database insert failed: {str(e)}")
        
    # Kick off background task
    background_tasks.add_task(process_clinical_text, request_id, extracted_text)
    
    return {"request_id": request_id, "status": "pending"}

@app.get("/requests")
async def get_requests(status: Optional[str] = None, limit: int = 50):
    if not supabase:
        raise HTTPException(status_code=500, detail="Supabase not initialized")
    
    query = supabase.table("requests").select("*").order("created_at", desc=True).limit(limit)
    if status:
        query = query.eq("status", status)
        
    res = query.execute()
    return res.data

@app.get("/requests/{request_id}")
async def get_request(request_id: str):
    if not supabase:
        raise HTTPException(status_code=500, detail="Supabase not initialized")
        
    res = supabase.table("requests").select("*").eq("request_id", request_id).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="Request not found")
    return res.data[0]

@app.get("/corrections/reviewed-ids")
async def get_reviewed_ids():
    if not supabase:
        raise HTTPException(status_code=500, detail="Supabase not initialized")
        
    # We just need the unique request_ids that have corrections
    res = supabase.table("corrections").select("request_id").execute()
    unique_ids = list(set([r["request_id"] for r in res.data]))
    return {"reviewed_ids": unique_ids}

@app.post("/requests/{request_id}/corrections")
async def save_corrections(request_id: str, payload: list[dict]):
    if not supabase:
        raise HTTPException(status_code=500, detail="Supabase not initialized")
        
    # 1. Save the updated results state back to the requests table
    try:
        supabase.table("requests").update({"results": payload}).eq("request_id", request_id).execute()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update request results: {str(e)}")
        
    # 2. Log flagged and corrected entries into the corrections table
    corrections_to_insert = []
    for item in payload:
        status = item.get("status")
        if status in ["flagged", "corrected"]:
            corrections_to_insert.append({
                "request_id": request_id,
                "original_text_span": item.get("source_span") or item.get("concept"),
                "model_code": item.get("matched_code"),
                # Explicitly null if just flagged, populated if corrected
                "coder_corrected_code": item.get("corrected_code") if status == "corrected" else None
            })
            
    inserted_count = 0
    if corrections_to_insert:
        try:
            res = supabase.table("corrections").insert(corrections_to_insert).execute()
            inserted_count = len(res.data)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to insert corrections: {str(e)}")
            
    return {"status": "success", "inserted": inserted_count}

