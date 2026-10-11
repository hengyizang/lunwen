"""Bounded question-scoped source packets; no model calls or hidden truncation."""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from scripts.research_artifacts import path_in, read, record, sha, write

PLAN = "program/context-plan.json"
OUTPUT = "reports/research-extensions/context.json"


def safe_text(project, relative, redact):
    from scripts.api_orchestrator import SNAPSHOT_SUFFIXES, SNAPSHOT_SKIPPED_PARTS
    parts = Path(relative).parts
    lowered = tuple(p.lower() for p in parts)
    if (any(p.startswith(".") or p in SNAPSHOT_SKIPPED_PARTS for p in lowered)
            or "reviews" in lowered or "review-packets" in lowered
            or any(x in Path(relative).name.lower() for x in ("api_key", "apikey", "credential", "password", "secret", "token"))
            or Path(relative).suffix.lower() not in SNAPSHOT_SUFFIXES):
        raise ValueError("context input is private, a prior review, or unsupported: " + relative)
    target = path_in(project, relative)
    if target.stat().st_size > 4_000_000:
        raise ValueError("context source exceeds 4 MB; prepare a traceable extract")
    content = target.read_text(encoding="utf-8")
    return redact(content), sha(target)


def build(project: Path, stage: str, *, redact=lambda text: text, max_bytes=600_000, task=None) -> dict:
    plan = read(path_in(project, PLAN))
    if plan.get("schema_version") != "1.0":
        raise ValueError("unsupported context plan schema")
    spec = plan.get("stages", {}).get(stage)
    if isinstance(spec, dict):
        task = task if task is not None else spec.get("active_task")
    chapter_target = None
    if task is not None:
        if not isinstance(task, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", task):
            raise ValueError("context task needs an exact safe ID")
        selected = spec.get("tasks", {}).get(task) if isinstance(spec, dict) else None
        if not isinstance(selected, dict):
            raise ValueError("context task is absent from this stage")
        chapter_target = selected.get("target")
        if not isinstance(chapter_target, str) or not chapter_target.strip() or len(chapter_target) > 1000:
            raise ValueError("task context needs an explicit paper/chapter target")
        spec = {**selected,
                "items": spec.get("items", []) + selected.get("items", []),
                "dependencies": spec.get("dependencies", []) + selected.get("dependencies", [])}
    if not isinstance(spec, dict) or not isinstance(spec.get("question"), str) or not 1 <= len(spec["question"].strip()) <= 4000:
        raise ValueError("context plan needs the current stage and its question")
    items = spec.get("items")
    if not isinstance(items, list) or not 1 <= len(items) <= 200:
        raise ValueError("context plan needs 1-200 explicit source selections")
    # Contracts remain complete even when a task selects a narrow evidence slice.
    mandatory = [name for name in ("state/run.json", "intake/constraints.json", "program/core-thesis.json",
                 "program/extension-thesis.json", "program/hypothesis-register.json",
                 "program/research-increments.json", "reports/research-increments/audit.json") if (project / name).is_file()]
    mandatory.extend(p.relative_to(project).as_posix() for p in sorted(project.glob("papers/P[0-9][0-9]/paper-contract.json")))
    selections = [{"path": name, "reason": "mandatory research constraints", "stance": "constraint"}
                  for name in mandatory] + items
    blocks, bindings, covered, total = [], [], set(), 0
    for item in selections:
        relative = item["path"]
        content, digest = safe_text(project, relative, redact)
        if item.get("expected_sha256", digest) != digest:
            raise ValueError("frozen context input changed: " + relative)
        if not isinstance(item.get("reason"), str) or not item["reason"].strip():
            raise ValueError("context selection needs a reason")
        if item.get("stance") not in {"supports", "contradicts", "mixed", "neutral", "constraint"}:
            raise ValueError("context selection needs an explicit evidence stance")
        lines = content.splitlines(keepends=True)
        first, last = item.get("start_line", 1), item.get("end_line", max(1, len(lines)))
        if type(first) is not int or type(last) is not int or not 1 <= first <= last <= max(1, len(lines)):
            raise ValueError("context line range is invalid")
        snippet = "".join(lines[first - 1:last])
        block = f"--- FILE {relative} sha256={digest} lines={first}-{last} stance={item['stance']} ---\n{snippet}\n--- END FILE ---"
        total += len(block.encode("utf-8"))
        if total > max_bytes:
            raise ValueError("required context exceeds the budget; select smaller explicit ranges, never silently omit evidence")
        blocks.append(block)
        bindings.append({"path": relative, "sha256": digest, "start_line": first, "end_line": last,
                         "snippet_sha256": hashlib.sha256(snippet.encode()).hexdigest(), "reason": item["reason"], "stance": item["stance"]})
        bindings[-1]["complete_source"] = first == 1 and last == max(1, len(lines))
        covered.add(relative)
    # An active conflict cannot be left out of a task packet by changing its stance.
    notebook_path = project / "program/research-notebook.json"
    if notebook_path.is_file():
        for question in read(notebook_path).get("questions", []):
            for entry in question.get("evidence", []):
                if entry.get("stance") in {"contradicts", "mixed"}:
                    bound = entry["source"]
                    matches = [b for b in bindings if b["path"] == bound["path"] and b["sha256"] == bound["sha256"]
                               and b["stance"] in {"contradicts", "mixed"} and b["complete_source"]]
                    if not matches:
                        raise ValueError("context omits current counterevidence: " + entry["id"])
    dependencies = []
    if not isinstance(spec.get("dependencies", []), list) or len(spec.get("dependencies", [])) > 200:
        raise ValueError("at most 200 explicit dependencies are allowed")
    for dependency in spec.get("dependencies", []):
        target = path_in(project, dependency["path"])
        dependencies.append({"path": dependency["path"], "sha256": sha(target)})
    payload = {"stage": stage, "task": task, "target": chapter_target, "question": spec["question"], "bindings": bindings,
               "dependencies": dependencies, "plan_sha256": sha(project / PLAN),
               "implementation_sha256": sha(Path(__file__))}
    fingerprint = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
    eligible = {p.relative_to(project).as_posix() for p in project.rglob("*") if p.is_file() and not p.is_symlink()}
    omitted = sorted(p for p in eligible - covered if p.startswith(("papers/", "program/", "literature/", "evidence/"))
                     and not any(x in p.lower() for x in ("secret", "credential", "private", "review", "token", "password")))
    return {**payload, "fingerprint": fingerprint, "bytes": total, "omitted_paths": omitted[:200],
            "omitted_count": len(omitted), "omission_inventory_truncated": len(omitted) > 200,
            "context": "Question: " + spec["question"] + "\n\n" + "\n\n".join(blocks),
            "omissions_are_not_irrelevant": True, "scientific_completeness_verified": False}


def refresh(project: Path, stage: str, *, task=None) -> dict:
    from scripts.api_orchestrator import redact
    value = build(project, stage, redact=redact, task=task)
    output = OUTPUT if value["task"] is None else "reports/research-extensions/context-" + value["task"] + ".json"
    target = path_in(project, output, exists=False)
    previous = read(target) if target.is_file() else {}
    value["dependency_changes"] = sorted({item["path"] for item in value["bindings"] + value["dependencies"]
        if (item["path"], item["sha256"]) not in {(b["path"], b["sha256"]) for b in previous.get("bindings", []) + previous.get("dependencies", [])}})
    value["reusable"] = previous.get("fingerprint") == value["fingerprint"]
    value["removed_dependencies"] = sorted({b["path"] for b in previous.get("bindings", []) + previous.get("dependencies", [])}
        - {b["path"] for b in value["bindings"] + value["dependencies"]})
    # Save bindings, not another duplicated manuscript/context copy.
    value.pop("context")
    write(target, value)
    record(project, [target], "scripts/evidence_context.py")
    return value
