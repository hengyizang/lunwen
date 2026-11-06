"""Honest pending research decisions for software-only controller fixtures."""
from scripts.research_artifacts import write


def pending_decision(project, stage, run_id, paper_id=None):
    decision = {"id": "fixture-decision", "cycle_id": str(run_id), "stage": stage, "paper_id": paper_id,
        "phase": "planned", "outcome": "pending", "evidence_ids": [],
        "discriminating_test": "Compare a matched ablation against the competing mechanism under the same inputs.",
        "decision": "Keep the mechanism claim provisional while the matched observations are missing.",
        "rationale": "This software fixture supplies no scientific observations or actual independent review.",
        "next_action": "Collect the authorized matched observations before changing the mechanism claim.",
        "failure_condition": "The intervention cannot distinguish the two proposed mechanisms.",
        "stop_rule": "Stop this mechanism test if its stated discriminating observation is not measurable."}
    question = {"id": "fixture-question", "question": "Which observation distinguishes the two proposed mechanisms?",
        "evidence": [], "missing_evidence": ["Actual matched observations remain unavailable."], "decisions": [decision]}
    value = {"questions": [question]}
    write(project/"program/research-notebook.json", value)
    return value
