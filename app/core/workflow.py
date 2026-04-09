from typing import Any, Dict, TypedDict

from langgraph.graph import END, StateGraph

from app.core.services import (
    archive_to_filenet_mock,
    generate_summary,
    parse_document_text,
    score_fields,
    write_audit,
)


class WorkflowState(TypedDict, total=False):
    request_id: str
    correlation_id: str
    customer_id: str
    old_name_requested: str
    new_name_requested: str
    upload_path: str

    old_name_extracted: str
    new_name_extracted: str

    confidence_old_name: float
    confidence_new_name: float
    confidence_authenticity: float

    forgery_check: str
    recommended_action: str

    ai_summary: str
    filenet_reference_id: str


def intake_validation(state: WorkflowState) -> WorkflowState:
    required = ["request_id", "correlation_id", "customer_id", "old_name_requested", "new_name_requested", "upload_path"]
    missing = [key for key in required if not state.get(key)]
    if missing:
        raise ValueError(f"Missing required fields: {', '.join(missing)}")

    write_audit(
        "validation_agent_completed",
        state["correlation_id"],
        {"request_id": state["request_id"]},
    )
    return state


def document_processor(state: WorkflowState) -> WorkflowState:
    extraction = parse_document_text(state["upload_path"])
    state.update(extraction)
    write_audit(
        "document_processor_completed",
        state["correlation_id"],
        {
            "old_name_extracted": state.get("old_name_extracted"),
            "new_name_extracted": state.get("new_name_extracted"),
        },
    )
    return state


def confidence_scorer(state: WorkflowState) -> WorkflowState:
    scores = score_fields(
        state["old_name_requested"],
        state["new_name_requested"],
        state.get("old_name_extracted", ""),
        state.get("new_name_extracted", ""),
        state.get("authenticity_flag", "FLAG"),
    )
    state.update(scores)
    write_audit(
        "confidence_scorer_completed",
        state["correlation_id"],
        {
            "confidence_old_name": state.get("confidence_old_name"),
            "confidence_new_name": state.get("confidence_new_name"),
            "confidence_authenticity": state.get("confidence_authenticity"),
            "recommended_action": state.get("recommended_action"),
        },
    )
    return state


def summary_agent(state: WorkflowState) -> WorkflowState:
    state["ai_summary"] = generate_summary(
        customer_id=state["customer_id"],
        old_requested=state["old_name_requested"],
        new_requested=state["new_name_requested"],
        old_extracted=state.get("old_name_extracted", ""),
        new_extracted=state.get("new_name_extracted", ""),
        score_card=state,
    )
    write_audit(
        "summary_agent_completed",
        state["correlation_id"],
        {"request_id": state["request_id"]},
    )
    return state


def filenet_archiver(state: WorkflowState) -> WorkflowState:
    state["filenet_reference_id"] = archive_to_filenet_mock(
        state["upload_path"], state["correlation_id"]
    )
    write_audit(
        "filenet_archive_completed",
        state["correlation_id"],
        {"filenet_reference_id": state["filenet_reference_id"]},
    )
    return state


def build_workflow() -> Any:
    graph = StateGraph(WorkflowState)
    graph.add_node("intake_validation", intake_validation)
    graph.add_node("document_processor", document_processor)
    graph.add_node("confidence_scorer", confidence_scorer)
    graph.add_node("summary_agent", summary_agent)
    graph.add_node("filenet_archiver", filenet_archiver)

    graph.set_entry_point("intake_validation")
    graph.add_edge("intake_validation", "document_processor")
    graph.add_edge("document_processor", "confidence_scorer")
    graph.add_edge("confidence_scorer", "summary_agent")
    graph.add_edge("summary_agent", "filenet_archiver")
    graph.add_edge("filenet_archiver", END)

    return graph.compile()
