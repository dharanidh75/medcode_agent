"""
agents/graph.py
────────────────
LangGraph Orchestrator: Builds and compiles the MedCode state graph.

Fix: route_after_validation must return updated state dict with incremented
retry_count — LangGraph conditional edge functions that mutate a local object
don't persist. State is passed as dict and must be returned explicitly.
"""
import logging
from typing import Literal
from langgraph.graph import StateGraph, END
from core.config import settings

logger = logging.getLogger(__name__)


def extractor_node(state: dict) -> dict:
    from agents.extractor import extractor_node as _extractor
    from schemas.medcode import MedCodeAgentState
    return _extractor(MedCodeAgentState(**state)).dict()


def coder_node(state: dict) -> dict:
    from agents.coder import coder_node as _coder
    from schemas.medcode import MedCodeAgentState
    return _coder(MedCodeAgentState(**state)).dict()


def validator_node(state: dict) -> dict:
    from agents.validator import validator_node as _validator
    from schemas.medcode import MedCodeAgentState
    return _validator(MedCodeAgentState(**state)).dict()


def accept_node(state: dict) -> dict:
    state = dict(state)
    state["final_status"] = "accepted"
    logger.info(
        f"[Orchestrator] Case accepted. ICD-10: {state.get('proposed_icd10')} | CPT: {state.get('proposed_cpt')}"
    )
    return state


def pending_node(state: dict) -> dict:
    state = dict(state)
    state["final_status"] = "pending"
    logger.warning(
        f"[Orchestrator] Case sent to manual review after {state.get('retry_count')} retries."
    )
    return state


def route_after_validation(state: dict) -> Literal["retry_coder", "accept", "pending"]:
    """
    Routing function for conditional edges.
    NOTE: This function cannot mutate state — it only reads it.
    retry_count is incremented inside a dedicated increment_retry node instead.
    """
    if state.get("validation_passed"):
        logger.info("[Orchestrator] Routing: ACCEPT")
        return "accept"

    retry_count = state.get("retry_count", 0)
    max_retries = state.get("max_retries", 3)

    # retry_count is already post-increment when router runs (increment_retry → coder → validator → route)
    # So stop when retry_count >= max_retries
    if retry_count < max_retries:
        logger.info(f"[Orchestrator] Routing: RETRY (attempt {retry_count}/{max_retries})")
        return "retry_coder"

    logger.warning(f"[Orchestrator] Routing: PENDING — reached max {max_retries} retries.")
    return "pending"


def increment_retry_node(state: dict) -> dict:
    """
    Dedicated node to increment retry_count before going back to coder.
    This is the correct LangGraph pattern — state mutation must happen
    inside a node, not inside a routing function.
    """
    state = dict(state)
    state["retry_count"] = state.get("retry_count", 0) + 1
    logger.info(f"[Orchestrator] Retry count incremented to {state['retry_count']}")
    return state


def build_medcode_graph():
    builder = StateGraph(dict)

    builder.add_node("extractor",      extractor_node)
    builder.add_node("coder",          coder_node)
    builder.add_node("validator",      validator_node)
    builder.add_node("increment_retry", increment_retry_node)
    builder.add_node("accept",         accept_node)
    builder.add_node("pending",        pending_node)

    builder.set_entry_point("extractor")
    builder.add_edge("extractor", "coder")
    builder.add_edge("coder", "validator")

    builder.add_conditional_edges(
        "validator",
        route_after_validation,
        {
            "retry_coder": "increment_retry",
            "accept":      "accept",
            "pending":     "pending",
        },
    )

    # After incrementing retry, go back to coder
    builder.add_edge("increment_retry", "coder")

    builder.add_edge("accept",  END)
    builder.add_edge("pending", END)

    return builder.compile()


medcode_graph = build_medcode_graph()