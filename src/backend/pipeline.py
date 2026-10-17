import os
from dotenv import load_dotenv
dotenv_path = os.path.join(os.path.dirname(__file__), ".env")
load_dotenv(dotenv_path)
import httpx
from supabase import create_client, Client
from groq_client import structure_clinical_text
from typing import Dict, Any, List

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
LOCAL_MODEL_SERVICE_URL = os.environ.get("LOCAL_MODEL_SERVICE_URL", "").rstrip("/")

# Initialize Supabase client globally
supabase: Client = None
if SUPABASE_URL and SUPABASE_KEY:
    try:
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    except Exception as e:
        print(f"Warning: Supabase client initialization failed: {e}")

async def check_local_model_health() -> bool:
    try:
        headers = {"ngrok-skip-browser-warning": "1"}
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{LOCAL_MODEL_SERVICE_URL}/health", headers=headers)
            return response.status_code == 200 and response.json().get("status") == "ok"
    except Exception as e:
        print(f"Local model health check failed: {e}")
        return False

async def search_local_model(queries: List[Dict[str, str]]) -> List[Dict[str, Any]]:
    if not queries:
        return []
    try:
        headers = {"ngrok-skip-browser-warning": "1"}
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{LOCAL_MODEL_SERVICE_URL}/search",
                json={"queries": queries},
                headers=headers
            )
            response.raise_for_status()
            return response.json()
    except Exception as e:
        print(f"Error calling local model search: {e}")
        return []

async def process_clinical_text(request_id: str, raw_text: str):
    try:
        # Update status to processing
        if supabase:
            supabase.table("requests").update({"status": "processing"}).eq("request_id", request_id).execute()
        
        # 1. Structure the text via Groq
        structured_json = await structure_clinical_text(raw_text)
        
        if supabase:
            supabase.table("requests").update({"structured_text": structured_json}).eq("request_id", request_id).execute()
        
        # 2. Extract concepts for search (excluding negated_findings)
        concepts_to_search = []
        concept_categories = ["diagnoses", "procedures", "symptoms", "medications"]
        concept_metadata = {}
        
        for category in concept_categories:
            items = structured_json.get(category, [])
            for item in items:
                term = item.get("term")
                if term:
                    # IMPLEMENTATION: Anthropic's Contextual Retrieval (Query side)
                    # We prepend the source context to the query to give the dense 
                    # embedding model semantic background!
                    source_context = item.get("source_span", "")
                    contextual_query = f"{source_context} (Concept: {term})"
                    
                    concepts_to_search.append({
                        "concept": contextual_query,
                        "category": category
                    })
                    concept_metadata[contextual_query] = {
                        "category": category,
                        "source_span": source_context,
                        "original_term": term
                    }
        
        # 3. Call local model service via ngrok tunnel
        search_results = await search_local_model(concepts_to_search)
        
        formatted_results = []
        for res in search_results:
            contextual_query = res.get("concept")
            meta = concept_metadata.get(contextual_query, {})
            # merge everything into a single dict for the frontend, restoring the isolated term
            res["concept"] = meta.get("original_term", contextual_query)
            res["category"] = meta.get("category", "unknown")
            res["source_span"] = meta.get("source_span", "")
            res["status"] = "unreviewed"
            res["corrected_code"] = None
            formatted_results.append(res)
            
        # 5. Save results and mark done
        if supabase:
            supabase.table("requests").update({
                "status": "done",
                "results": formatted_results
            }).eq("request_id", request_id).execute()
            
    except Exception as e:
        error_msg = str(e)
        print(f"Error in background pipeline: {error_msg}")
        if supabase:
            supabase.table("requests").update({
                "status": "failed",
                "error_message": error_msg
            }).eq("request_id", request_id).execute()
