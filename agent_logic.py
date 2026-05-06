"""LangGraph agent loop for proposing and critiquing room design changes."""

from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Literal, TypedDict

from langgraph.graph import END, START, StateGraph

from knowledge_base import SafetyConstraintResult, query_safety_rules
from models import ModificationProposal, RoomScene


TRACE_FILE = Path("reasoning_trace.json")
MAX_ITERATIONS = 5
FLAMMABLE_MATERIALS = {
    "fabric",
    "cotton",
    "linen",
    "silk",
    "polyester",
    "wood",
    "paper",
    "foam",
    "curtain",
}
HEAT_SOURCE_KEYWORDS = {"stove", "radiator", "heater", "fireplace", "oven", "cooktop"}


class AgentState(TypedDict):
    room_scene: RoomScene
    safety_results: List[SafetyConstraintResult]
    proposals: List[ModificationProposal]
    status: Literal["PENDING", "REJECT", "APPROVED"]
    failure_trace: List[str]
    critic_notes: List[str]
    iteration: int
    max_iterations: int


def _json_safe(value: Any) -> Any:
    if is_dataclass(value):
        return {k: _json_safe(v) for k, v in asdict(value).items()}
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    return value


def _append_reasoning_trace(node: str, state: AgentState, message: str, extra: Dict[str, Any] | None = None) -> None:
    trace_payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "node": node,
        "message": message,
        "status": state["status"],
        "iteration": state["iteration"],
        "failure_trace": state["failure_trace"],
        "critic_notes": state["critic_notes"],
        "proposals": [_json_safe(p) for p in state["proposals"]],
    }
    if extra:
        trace_payload["extra"] = _json_safe(extra)

    if TRACE_FILE.exists():
        try:
            current = json.loads(TRACE_FILE.read_text(encoding="utf-8"))
            if not isinstance(current, list):
                current = []
        except json.JSONDecodeError:
            current = []
    else:
        current = []

    current.append(trace_payload)
    TRACE_FILE.write_text(json.dumps(current, ensure_ascii=False, indent=2), encoding="utf-8")


def _is_flammable(material: str) -> bool:
    lowered = material.lower()
    return any(term in lowered for term in FLAMMABLE_MATERIALS)


def _is_heat_source(name: str) -> bool:
    lowered = name.lower()
    return any(term in lowered for term in HEAT_SOURCE_KEYWORDS)


def proposer_node(state: AgentState) -> AgentState:
    """Propose design changes from RoomScene + safety retrieval context."""
    new_state = dict(state)
    proposals: List[ModificationProposal] = []
    notes: List[str] = []

    # Obvious hazard heuristic: flammable material near known heat-source objects.
    heat_objects = [obj for obj in state["room_scene"].furniture if _is_heat_source(obj.name)]
    for obj in state["room_scene"].furniture:
        if not _is_flammable(obj.material):
            continue
        for heat_obj in heat_objects:
            dx = obj.position.x - heat_obj.position.x
            dy = obj.position.y - heat_obj.position.y
            horizontal_distance = (dx * dx + dy * dy) ** 0.5
            if horizontal_distance < 1.2:
                proposals.append(
                    ModificationProposal(
                        original_object_id=obj.name,
                        action="move",
                        new_parameters={
                            "x": obj.position.x + 1.2,
                            "y": obj.position.y,
                            "z": obj.position.z,
                            "reason": f"Increase separation from heat source '{heat_obj.name}'.",
                        },
                        reasoning=(
                            f"Detected potentially flammable '{obj.name}' ({obj.material}) "
                            f"within {horizontal_distance:.2f}m of '{heat_obj.name}'. "
                            "Propose moving object to improve fire safety margin."
                        ),
                    )
                )
                notes.append(
                    f"Proposed move for '{obj.name}' away from heat source '{heat_obj.name}' "
                    f"(distance {horizontal_distance:.2f}m)."
                )
                break

    # If no targeted action found, propose a conservative inspection-oriented move.
    if not proposals:
        for obj in state["room_scene"].furniture[:1]:
            proposals.append(
                ModificationProposal(
                    original_object_id=obj.name,
                    action="move",
                    new_parameters={
                        "x": obj.position.x + 0.3,
                        "y": obj.position.y + 0.3,
                        "z": obj.position.z,
                        "reason": "Improve circulation clearance conservatively pending rule checks.",
                    },
                    reasoning=(
                        "No explicit high-risk conflict detected from geometry alone; propose a small "
                        "clearance-improving adjustment to reduce potential obstruction risk."
                    ),
                )
            )
            notes.append(f"Proposed conservative clearance adjustment for '{obj.name}'.")

    new_state["proposals"] = proposals
    new_state["status"] = "PENDING"
    new_state["iteration"] = state["iteration"] + 1

    _append_reasoning_trace(
        node="proposer",
        state=new_state,  # type: ignore[arg-type]
        message="Generated candidate modification proposals.",
        extra={"notes": notes},
    )
    return new_state  # type: ignore[return-value]


def critic_node(state: AgentState) -> AgentState:
    """Strict safety officer: reject proposals that conflict with retrieved rules."""
    new_state = dict(state)
    failure_trace: List[str] = []
    critic_notes: List[str] = []

    current_rules = query_safety_rules(state["room_scene"], top_k=8)
    combined_rules = state["safety_results"] + [r for r in current_rules if r not in state["safety_results"]]

    strict_fire_exit_min_width = 0.0
    for rule in combined_rules:
        if rule.constraint.rule_id.startswith("strict_fire_exit_width_"):
            strict_fire_exit_min_width = max(strict_fire_exit_min_width, rule.constraint.minimum_clearance)

    for proposal in state["proposals"]:
        target_lower = proposal.original_object_id.lower()
        proposal_text = f"{proposal.reasoning} {proposal.new_parameters}".lower()

        if strict_fire_exit_min_width > 0 and any(
            term in target_lower for term in ("fire_exit", "fire exit", "exit", "egress", "door")
        ):
            proposed_width = proposal.new_parameters.get("width")
            if proposed_width is not None and float(proposed_width) < strict_fire_exit_min_width:
                failure_trace.append(
                    f"Fire-exit width conflict for '{proposal.original_object_id}': proposed {float(proposed_width):.3f}m "
                    f"is below strict required minimum {strict_fire_exit_min_width:.3f}m (max across GB sources)."
                )
                critic_notes.append(
                    "Rejected by strict multi-regulation rule: must use highest minimum width for fire exits."
                )

        for rule in combined_rules:
            snippet = rule.snippet.lower()
            # Strict match: if rule text mentions target/object material + "distance/clearance/not less than",
            # enforce conservative rejection unless proposal clearly increases clearance.
            mentions_target = target_lower in snippet or target_lower in rule.constraint.material_requirement.lower()
            mentions_clearance_logic = any(
                term in snippet for term in ("clearance", "distance", "separation", "not less than", "minimum")
            )
            likely_conflict = any(term in snippet for term in ("flammable", "combustible", "fire", "heat", "ignition"))

            if mentions_target and (mentions_clearance_logic or likely_conflict):
                if proposal.action != "move":
                    failure_trace.append(
                        f"Rule conflict for '{proposal.original_object_id}': action '{proposal.action}' is not "
                        "accepted for a fire/clearance risk."
                    )
                    critic_notes.append(
                        f"Rejected proposal against {rule.source_file} p.{rule.page_number}: non-move action."
                    )
                    continue

                if "increase separation" not in proposal_text and "clearance" not in proposal_text:
                    failure_trace.append(
                        f"Rule conflict for '{proposal.original_object_id}': insufficient evidence that clearance "
                        "is improved."
                    )
                    critic_notes.append(
                        f"Rejected proposal against {rule.source_file} p.{rule.page_number}: missing clearance intent."
                    )

    if failure_trace:
        new_state["status"] = "REJECT"
        new_state["failure_trace"] = failure_trace
        new_state["critic_notes"] = critic_notes
        _append_reasoning_trace(
            node="critic",
            state=new_state,  # type: ignore[arg-type]
            message="Rejected proposals with failure trace.",
            extra={"grounded_rules_used": [_json_safe(r) for r in combined_rules]},
        )
    else:
        new_state["status"] = "APPROVED"
        new_state["failure_trace"] = []
        new_state["critic_notes"] = ["All checked proposals pass strict safety review."]
        _append_reasoning_trace(
            node="critic",
            state=new_state,  # type: ignore[arg-type]
            message="Approved proposals after strict safety review.",
            extra={"grounded_rules_used": [_json_safe(r) for r in combined_rules]},
        )

    return new_state  # type: ignore[return-value]


def _router(state: AgentState) -> str:
    if state["status"] == "APPROVED":
        _append_reasoning_trace("router", state, "Routing to output node (APPROVED).")
        return "output"

    if state["status"] == "REJECT" and state["iteration"] < state["max_iterations"]:
        _append_reasoning_trace("router", state, "Routing back to proposer (REJECT).")
        return "proposer"

    _append_reasoning_trace(
        "router",
        state,
        "Routing to output node after max iterations with unresolved rejection.",
    )
    return "output"


def output_node(state: AgentState) -> AgentState:
    _append_reasoning_trace("output", state, "Finalized state for downstream use.")
    return state


def build_agent_graph():
    graph = StateGraph(AgentState)
    graph.add_node("proposer", proposer_node)
    graph.add_node("critic", critic_node)
    graph.add_node("output", output_node)

    graph.add_edge(START, "proposer")
    graph.add_edge("proposer", "critic")
    graph.add_conditional_edges("critic", _router, {"proposer": "proposer", "output": "output"})
    graph.add_edge("output", END)
    return graph.compile()


def run_design_agent(room_scene: RoomScene, initial_safety_results: List[SafetyConstraintResult] | None = None) -> AgentState:
    """Execute proposer-critic loop until approved or retry limit reached."""
    if TRACE_FILE.exists():
        # Fresh run for academic evaluation reproducibility.
        TRACE_FILE.unlink()

    app = build_agent_graph()
    initial_state: AgentState = {
        "room_scene": room_scene,
        "safety_results": initial_safety_results or query_safety_rules(room_scene, top_k=8),
        "proposals": [],
        "status": "PENDING",
        "failure_trace": [],
        "critic_notes": [],
        "iteration": 0,
        "max_iterations": MAX_ITERATIONS,
    }
    return app.invoke(initial_state)
