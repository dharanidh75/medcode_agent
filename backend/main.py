"""
main.py
────────
FastAPI application entry point for MedCode backend.

Startup sequence:
  1. Initialize Mysql tables (SQLModel create_all)
  2. Seed ChromaDB if collections are empty
  3. Register all API routers under /api/v1
"""
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from core.config import settings
from db.database import init_db
from api import ocr, pipeline, cases

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown lifecycle."""
    logger.info("═══════════════════════════════════════")
    logger.info("  MedCode Backend — Starting Up")
    logger.info("═══════════════════════════════════════")

    # 1. Create PostgreSQL tables
    logger.info("Initializing Mysql tables...")
    init_db()
    logger.info("✓ Database tables ready.")

    # 2. Seed ChromaDB if needed
    logger.info("Checking ChromaDB vector store...")
    try:
        from db.vector_store import get_icd10_collection, get_cpt_collection
        from scripts.seed_vector_db import ICD10_SEED, CPT_SEED, seed_collection

        seed_collection(get_icd10_collection(), ICD10_SEED, "ICD10")
        seed_collection(get_cpt_collection(), CPT_SEED, "CPT")
        logger.info("✓ ChromaDB vector store ready.")
    except Exception as e:
        logger.warning(f"ChromaDB seed check failed (non-fatal): {e}")

    # 3. Pre-warm LangGraph graph compilation
    logger.info("Compiling LangGraph state machine...")
    from agents.graph import medcode_graph
    logger.info("✓ LangGraph graph compiled and ready.")

    logger.info("═══════════════════════════════════════")
    logger.info(f"  Server running on http://{settings.APP_HOST}:{settings.APP_PORT}")
    logger.info("═══════════════════════════════════════")

    yield

    logger.info("MedCode Backend shutting down.")


app = FastAPI(
    title="MedCode API",
    description="AI-powered medical billing and coding backend — LangGraph + RAG + PaddleOCR",
    version="1.0.0",
    lifespan=lifespan,
)

# ── CORS ──────────────────────────────────────────────────────────────────────
# allow_credentials must be False when allow_origins=["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Type", "Cache-Control", "X-Accel-Buffering"],
)

# ── API Routers ───────────────────────────────────────────────────────────────
PREFIX = "/api/v1"

app.include_router(ocr.router,      prefix=PREFIX, tags=["OCR"])
app.include_router(pipeline.router, prefix=PREFIX, tags=["Pipeline"])
app.include_router(cases.router,    prefix=PREFIX, tags=["Cases"])


# ── Health Check ──────────────────────────────────────────────────────────────
@app.get("/health", tags=["System"])
def health_check():
    return {
        "status": "healthy",
        "service": "MedCode API",
        "version": "1.0.0",
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host=settings.APP_HOST,
        port=settings.APP_PORT,
        reload=settings.APP_ENV == "development",
    )