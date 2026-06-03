"""
ChromaDB vector store layer.
Two persistent collections:
  - icd10_codes: ICD-10 diagnosis codes + clinical descriptions
  - cpt_codes:   CPT procedure codes + procedure descriptions

Embeddings are generated via sentence-transformers (all-MiniLM-L6-v2)
running fully local — no API calls for embeddings.
"""
import chromadb
from chromadb.api import ClientAPI  # Import the official client interface type
from chromadb.utils import embedding_functions
from core.config import settings  # Fixed path to include app reference prefix
import logging

logger = logging.getLogger(__name__)

# --- Singleton Variable Configuration ---
# Changed hint from chromadb.PersistentClient to ClientAPI to resolve the runtime union pipe exception
_chroma_client: ClientAPI | None = None


def get_chroma_client() -> ClientAPI:
    global _chroma_client
    if _chroma_client is None:
        _chroma_client = chromadb.PersistentClient(path=settings.CHROMA_PERSIST_DIR)
        logger.info(f"ChromaDB PersistentClient initialized at: {settings.CHROMA_PERSIST_DIR}")
    return _chroma_client


def get_embedding_function():
    """Local sentence-transformer embeddings — no external API dependency."""
    return embedding_functions.SentenceTransformerEmbeddingFunction(
        model_name="all-MiniLM-L6-v2"
    )


def get_icd10_collection() -> chromadb.Collection:
    client = get_chroma_client()
    return client.get_or_create_collection(
        name="icd10_codes",
        embedding_function=get_embedding_function(),
        metadata={"hnsw:space": "cosine"},
    )


def get_cpt_collection() -> chromadb.Collection:
    client = get_chroma_client()
    return client.get_or_create_collection(
        name="cpt_codes",
        embedding_function=get_embedding_function(),
        metadata={"hnsw:space": "cosine"},
    )


def semantic_search_icd10(query: str, n_results: int = 5) -> list[dict]:
    """
    Embed the query and retrieve the top-n closest ICD-10 entries.
    Returns a list of dicts: {code, description, distance}
    """
    collection = get_icd10_collection()
    results = collection.query(
        query_texts=[query],
        n_results=n_results,
        include=["documents", "metadatas", "distances"],
    )
    output = []
    if results["ids"] and results["ids"][0]:
        for i, doc_id in enumerate(results["ids"][0]):
            output.append({
                "code": results["metadatas"][0][i].get("code", doc_id),
                "description": results["documents"][0][i],
                "distance": round(results["distances"][0][i], 4),
            })
    return output


def semantic_search_cpt(query: str, n_results: int = 5) -> list[dict]:
    """
    Embed the query and retrieve the top-n closest CPT entries.
    Returns a list of dicts: {code, description, distance}
    """
    collection = get_cpt_collection()
    results = collection.query(
        query_texts=[query],
        n_results=n_results,
        include=["documents", "metadatas", "distances"],
    )
    output = []
    if results["ids"] and results["ids"][0]:
        for i, doc_id in enumerate(results["ids"][0]):
            output.append({
                "code": results["metadatas"][0][i].get("code", doc_id),
                "description": results["documents"][0][i],
                "distance": round(results["distances"][0][i], 4),
            })
    return output