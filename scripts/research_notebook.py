"""Incremental question-centred evidence and decision views; never invent evidence."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from scripts.research_artifacts import path_in, read, write, bound_source, record

PHASES = {"idea", "planned", "running", "exploratory", "confirmatory", "failed", "stopped"}
STANCES = {"supports", "contradicts", "mixed", "unknown"}


def build(project: Path) -> dict:
    inputs = read(path_in(project, "program/research-notebook.json"))
    questions, errors, seen = [], [], set()
    for question in inputs.get("questions", []):
        try:
            identifier = question["id"]
            if identifier in seen or not identifier or not question.get("question"):
                raise ValueError("question needs a unique ID and text")
            seen.add(identifier)
            evidence, evidence_ids, decisions = [], set(), []
            for entry in question.get("evidence", []):
                if entry.get("id") in evidence_ids or not entry.get("id") or entry.get("stance") not in STANCES:
                    raise ValueError("evidence needs a unique ID and an explicit stance")
                evidence_ids.add(entry["id"])
                source = bound_source(project, entry["source"])
                if not entry.get("observation") or entry.get("read_scope") not in {"metadata", "abstract", "fulltext", "experiment"}:
                    raise ValueError("evidence needs an observation and honest reading scope")
                evidence.append({**entry, "source": source, "interpretation_verified": False})
            for decision in question.get("decisions", []):
                if decision.get("phase") not in PHASES or not decision.get("decision") or not decision.get("rationale"):
                    raise ValueError("decision needs phase, rationale and decision text")
                links = decision.get("evidence_ids", [])
                if not links or not set(links).issubset(evidence_ids):
                    raise ValueError("decision must link actual evidence, including contrary evidence where present")
                contrary = {e["id"] for e in evidence if e["stance"] in {"contradicts", "mixed"}}
                if contrary - set(links) and not decision.get("contrary_evidence_rationale"):
                    raise ValueError("omitted contrary evidence needs an explicit rationale")
                if not decision.get("failure_condition") or not decision.get("stop_rule"):
                    raise ValueError("decision needs a failure condition and stop rule")
                decisions.append(decision)
            questions.append({"id": identifier, "question": question["question"], "evidence": evidence,
                              "conflict_present": any(e["stance"] in {"contradicts", "mixed"} for e in evidence),
                              "decisions": decisions, "missing_evidence": question.get("missing_evidence", [])})
        except (OSError, ValueError, KeyError, TypeError) as exc:
            errors.append(str(exc))
    fingerprint = hashlib.sha256(json.dumps({"inputs": inputs, "questions": questions}, sort_keys=True).encode()).hexdigest()
    return {"schema_version": "1.0", "input_fingerprint": fingerprint, "questions": questions,
            "status": "needs_scientific_review" if not errors else "blocked", "errors": errors,
            "gate_approved": False, "scientific_completion_verified": False}


def refresh(project: Path) -> dict:
    result = build(project)
    output = project / "reports/research-notebook.json"
    previous = read(output) if output.is_file() else {}
    if previous == result:
        return {**result, "changed": False}
    write(output, result)
    journal = project / "reports/research-notebook-history.jsonl"
    journal.parent.mkdir(parents=True, exist_ok=True)
    with journal.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(result, ensure_ascii=False, sort_keys=True) + "\n")
    text = ["# Research evidence and decisions", "", "Interpretations require scientific review; no gate is approved here.", ""]
    for question in result["questions"]:
        text.extend([f"## {question['id']}: {question['question']}", ""])
        for e in question["evidence"]:
            text.append(f"- {e['id']} [{e['stance']}; {e['read_scope']}]: {e['observation']} — {e['source']['path']} ({e['source']['locator']})")
        for d in question["decisions"]:
            text.append(f"- Decision [{d['phase']}]: {d['decision']} | reason: {d['rationale']} | fail: {d['failure_condition']} | stop: {d['stop_rule']}")
        text.append("")
    summary = project / "reports/research-notebook.md"
    summary.write_text("\n".join(text), encoding="utf-8")
    record(project, [output, journal, summary], "scripts/research_notebook.py")
    return {**result, "changed": True}
