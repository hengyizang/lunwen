"""Explicitly synthetic scope setup for temporary cloud acceptance fixtures.

Not a production migration or approval API. Real project directories are refused.
"""
import os
from pathlib import Path
from unittest.mock import patch

from scripts import scientific_scope
from scripts.research_artifacts import read, write, sha

def prepare_scope(project, state):
    project = Path(project)
    production = Path(__file__).resolve().parents[1] / "projects"
    if project.resolve().is_relative_to(production.resolve()):
        raise ValueError("synthetic acceptance scopes cannot approve a real repository project")
    state["synthetic_acceptance_only"] = True
    state.setdefault("paper_count", 1)
    state.setdefault("active_paper", "P01")
    if (project / "state/scientific-scope/G2.json").is_file():
        errors = scientific_scope.validate(project, "G3")
        if errors:
            raise ValueError("changed synthetic scope needs a new fixture: " + "; ".join(errors))
        return
    count = state.get("paper_count", 1)
    ids = [f"P{n:02d}" for n in range(1, count + 1)]
    core = {"theme_id": "A", "doctoral_question": "Synthetic fixture doctoral question?",
            "distinct_contribution": "Fixture scope only; no scientific finding.", "planned_paper_ids": ids,
            "falsification_conditions": ["Synthetic scope condition"]}
    extension = {**core, "theme_id": "B", "mechanism_or_rationale": "Synthetic extension scope",
                 "independent_evidence_plan": ["Synthetic separate evidence"], "boundary_conditions": ["Fixture only"],
                 "relationship_to_core": {"shared_foundation": ["Synthetic common question"], "independent_question": True}}
    write(project / "program/core-thesis.json", core)
    write(project / "program/extension-thesis.json", extension)
    rows = []
    for pid in ids:
        path = project / f"papers/{pid}/paper-contract.json"
        contract = read(path) if path.is_file() else {}
        contract.update(paper_id=pid, research_question="Synthetic independent question for " + pid,
            distinct_contribution="Synthetic bounded contribution for " + pid, relationship_to_core="Synthetic common thesis",
            relationship_to_extension="Synthetic extension link", falsification_conditions=["Fixture falsification"],
            dependencies=[], target_jcr_quartile="Q1")
        write(path, contract)
        rows.append({"paper_id": pid, "theme_id": "A", "target_jcr_quartile": "Q1",
                     "portfolio_role": "Synthetic role " + pid, "distinct_contribution": contract["distinct_contribution"],
                     "unique_claim_ids": ["SYNTHETIC_" + pid], "shared_assets": [], "dependencies": []})
    write(project / "program/paper-map.json", {"schema_version": "2.0", "status": "ready_for_review",
        "papers": rows, "pairwise_distinctness": [], "thesis_synthesis": {"core_thesis": "Synthetic thesis", "extension_thesis": "Synthetic extension",
        "cumulative_progression": "Synthetic sequence", "integrated_contribution": "Fixture only", "dependency_logic": "Synthetic independent papers"}})
    state.setdefault("approvals", [])
    state.setdefault("approved_gates", [])
    with patch.dict(os.environ, {"DR_OS_CLOUD_EXECUTOR": "1"}):
        for gate in ("G1", "G2"):
            approval = {"gate": gate, "actor": "Synthetic fixture human", "artifact_sha256": sha(project / "program" / ("core-thesis.json" if gate == "G1" else "paper-map.json"))}
            state["approvals"].append(approval)
            if gate not in state["approved_gates"]:
                state["approved_gates"].append(gate)
            write(project / "state/run.json", state)
            scientific_scope.seal_approval(project, gate, approval["actor"], approval)
    write(project / "state/run.json", state)


