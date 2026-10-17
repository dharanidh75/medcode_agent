from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
import faiss
import pickle
import numpy as np
import os
from sentence_transformers import SentenceTransformer
from contextlib import asynccontextmanager

INDEX_DIR = "data"
MODEL_NAME = "abhinand/MedEmbed-large-v0.1"

# Globals to hold models and indexes
model = None
indexes = {
    "diagnoses": {"faiss": None, "metadata": None},
    "procedures": {"faiss": None, "metadata": None},
    "medications": {"faiss": None, "metadata": None}
}

class SearchItem(BaseModel):
    concept: str
    category: str

class SearchRequest(BaseModel):
    queries: List[SearchItem]

class Candidate(BaseModel):
    code: str
    description: str
    score: float

class ConceptResult(BaseModel):
    concept: str
    matched_code: str
    matched_description: str
    confidence_score: float
    candidates: List[Candidate]

def load_index(domain: str):
    domain_path = os.path.join(INDEX_DIR, domain)
    if not os.path.exists(domain_path):
        print(f"Warning: Index for {domain} not found at {domain_path}")
        return False
        
    faiss_path = os.path.join(domain_path, "faiss_index.bin")
    metadata_path = os.path.join(domain_path, "metadata.pkl")
    
    if os.path.exists(faiss_path) and os.path.exists(metadata_path):
        indexes[domain]["faiss"] = faiss.read_index(faiss_path)
        with open(metadata_path, "rb") as f:
            indexes[domain]["metadata"] = pickle.load(f)
        return True
    return False

@asynccontextmanager
async def lifespan(app: FastAPI):
    global model
    print("Loading models into memory...")
    try:
        model = SentenceTransformer(MODEL_NAME)
        load_index("diagnoses")
        load_index("procedures")
        load_index("medications")
        print("Models loaded successfully.")
    except Exception as e:
        print(f"Warning: Failed to load models on startup: {e}")
    yield

app = FastAPI(title="Local Model Service (MedEmbed-large-v0.1 + FAISS Multi-Domain)", lifespan=lifespan)

@app.get("/health")
async def health_check():
    if model is None:
        return {"status": "degraded", "message": "Embedding model not loaded"}
    loaded = {k: v["faiss"] is not None for k, v in indexes.items()}
    return {"status": "ok", "service": "local_model", "indexes": loaded}

def compute_rrf(dense_results: List[int], sparse_results: List[int], k: int = 60) -> Dict[int, float]:
    rrf_scores = {}
    for rank, doc_id in enumerate(dense_results):
        rrf_scores[doc_id] = rrf_scores.get(doc_id, 0.0) + 1.0 / (k + rank + 1)
    for rank, doc_id in enumerate(sparse_results):
        rrf_scores[doc_id] = rrf_scores.get(doc_id, 0.0) + 1.0 / (k + rank + 1)
    return rrf_scores

@app.post("/search", response_model=List[ConceptResult])
async def search(request: SearchRequest):
    if model is None:
        raise HTTPException(status_code=503, detail="Model not loaded.")
        
    results = []
    
    for item in request.queries:
        concept = item.concept
        category = item.category.lower()
        
        # Route symptoms to diagnoses index
        if category == "symptoms":
            domain = "diagnoses"
        else:
            domain = category
            
        if domain not in indexes or indexes[domain]["faiss"] is None:
            # Fallback to diagnoses if specific domain isn't indexed yet
            domain = "diagnoses"
            
        domain_idx = indexes.get(domain)
        if not domain_idx or domain_idx["faiss"] is None:
            continue
            
        faiss_index = domain_idx["faiss"]
        metadata = domain_idx["metadata"]
        codes = metadata["codes"]
        descriptions = metadata["descriptions"]
        bm25 = metadata["bm25"]
        
        # Dense search
        concept_emb = model.encode([concept], convert_to_numpy=True)
        faiss.normalize_L2(concept_emb)
        D, I = faiss_index.search(concept_emb, k=20)
        dense_results = I[0].tolist()
        
        # Sparse search (BM25)
        tokenized_query = concept.lower().split(" ")
        bm25_scores = bm25.get_scores(tokenized_query)
        sparse_results = np.argsort(bm25_scores)[::-1][:20].tolist()
        
        # RRF
        rrf_scores = compute_rrf(dense_results, sparse_results)
        
        # Sort by RRF score
        ranked_indices = sorted(rrf_scores.keys(), key=lambda x: rrf_scores[x], reverse=True)
        
        if not ranked_indices:
            continue
            
        top_indices = ranked_indices[:6]
        candidates = []
        for doc_id in top_indices:
            raw_score = rrf_scores[doc_id]
            confidence = min(raw_score * 30, 1.0)
            candidates.append(Candidate(
                code=codes[doc_id],
                description=descriptions[doc_id],
                score=round(confidence, 4)
            ))
            
        if not candidates:
            continue
            
        top_match = candidates[0]
        results.append(ConceptResult(
            concept=concept,
            matched_code=top_match.code,
            matched_description=top_match.description,
            confidence_score=top_match.score,
            candidates=candidates[1:]
        ))
        
    return results
