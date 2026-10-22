"""Owner-reviewed recovery of primary experiments; never retries or approves science itself."""
from __future__ import annotations

import hashlib
import json
import math
import re
import shutil
from pathlib import Path

CONTROL = "state/primary-recovery"
HISTORY = "experiments/history"


class RecoveryError(ValueError):
    pass


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def path_in(project, relative):
    from scripts.cloud_checkpoint import relative as safe_relative
    safe_relative(relative)
    target = project / relative
    if any(p.is_symlink() for p in (target, *target.parents)) or project.resolve() not in target.resolve().parents:
        raise RecoveryError("recovery paths must be ordinary files inside the project")
    return target


def records(project):
    path = project / "experiments/registry.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()] if path.exists() else []


def receipt(project, item):
    attempt = item.get("attempt_id", "")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,110}", attempt):
        raise RecoveryError("invalid executor attempt")
    path = path_in(project, f"experiments/runs/{attempt}/run.json")
    if not path.is_file() or read(path) != item:
        raise RecoveryError("attempt has no unchanged executor receipt")
    return path


def _approval(project, item):
    path = project / CONTROL / "retries" / (item["attempt_id"] + ".json")
    if not path.exists():
        return None
    approval = read(path)
    if (approval.get("failed_receipt_sha256") != sha(receipt(project, item))
            or approval.get("plan_sha256") != item.get("approved_plan_sha256")
            or approval.get("plan_sha256") != sha(project / "experiments/plan.json")
            or not approval.get("cloud_review_sha256") or not approval.get("actor")):
        raise RecoveryError("primary retry authorization is stale")
    for row in approval["preserved_outputs"]:
        target = path_in(project, row["preserved_path"])
        if not target.is_file() or sha(target) != row["sha256"]:
            raise RecoveryError("preserved failed output changed")
    return approval


def preserved_output(project, item, output):
    """A failed result overwritten by an authorized retry remains independently readable."""
    approval = _approval(project, item)
    if not approval:
        return path_in(project, output["path"])
    matches = [r for r in approval["preserved_outputs"] if r["path"] == output["path"] and r["sha256"] == output["sha256"]]
    if len(matches) != 1:
        raise RecoveryError("failed output is absent from the reviewed recovery archive")
    return path_in(project, matches[0]["preserved_path"])


def selected_attempt(project, run_id, rows, *, plan_sha256=None):
    attempts = [r for r in rows if r.get("run_id") == run_id]
    if not attempts:
        raise RecoveryError("run has no executor attempt")
    if len({r.get("attempt_id") for r in attempts}) != len(attempts):
        raise RecoveryError("duplicate executor attempts")
    # Preserve compatibility for ordinary receipts; callers still validate their contents.
    if len(attempts) == 1:
        item = attempts[0]
    else:
        for index, failed in enumerate(attempts[:-1]):
            if failed.get("status") not in {"failed", "timed_out"}:
                raise RecoveryError("successful runs cannot be rerun to select a better result")
            approval = _approval(project, failed)
            if not approval or approval["next_attempt_number"] != index + 2:
                raise RecoveryError("each repeated attempt requires its own exact human approval")
            if attempts[index + 1].get("attempt_id") != f"{run_id}-attempt-{index + 2:03d}":
                raise RecoveryError("retry did not use its reviewed next attempt")
        item = attempts[-1]
    if item.get("status") != "succeeded" or (plan_sha256 and item.get("approved_plan_sha256") != plan_sha256):
        raise RecoveryError("run has no current successful approved attempt")
    return item


def require_next_attempt(project, run_id, rows, plan_sha256):
    attempts = [r for r in rows if r.get("run_id") == run_id]
    if not attempts:
        return
    if any(r.get("status") == "succeeded" for r in attempts):
        raise RecoveryError("successful primary runs cannot be rerun")
    for index, item in enumerate(attempts):
        receipt(project, item)
        authorization = _approval(project, item)
        if (not authorization or item.get("approved_plan_sha256") != plan_sha256
                or authorization["next_attempt_number"] != index + 2):
            raise RecoveryError("failed primary attempt needs exact owner authorization before retry")


def prepare(project, source, actor, operation):
    from scripts import experiment_runner as runner
    state = read(project / "state/run.json")
    if state.get("gate") != "G4" or state.get("status") != "awaiting_work":
        raise RecoveryError("primary recovery requires the open G4 stage")
    runner.approved_plan(project, project / "experiments/plan.json", project / "experiments/budget.json")
    proposal = read(path_in(project, source))
    if (not actor or proposal.get("schema_version") != "1.0" or proposal.get("operation") != operation
            or proposal.get("plan_sha256") != sha(project / "experiments/plan.json")
            or proposal.get("budget_sha256") != sha(project / "experiments/budget.json")
            or not isinstance(proposal.get("reason"), str) or len(proposal["reason"].strip()) < 20):
        raise RecoveryError("recovery needs an exact plan/budget-bound proposal and substantive reason")
    rows = records(project)
    for item in rows:
        receipt(project, item)
    failed = [r for r in rows if r.get("status") in {"failed", "timed_out"}]
    if not failed:
        raise RecoveryError("primary recovery needs retained failed executor evidence")
    if operation == "approve_primary_retry":
        matches = [r for r in rows if r.get("attempt_id") == proposal.get("failed_attempt_id")]
        if len(matches) != 1 or matches[0] not in failed or proposal.get("failure_category") not in {"infrastructure", "transient_environment"}:
            raise RecoveryError("unchanged retry is only for an inspected infrastructure failure")
        item = matches[0]
        attempts = [r for r in rows if r.get("run_id") == item["run_id"]]
        if (attempts[-1] != item or any(r.get("status") == "succeeded" for r in attempts)
                or (project / CONTROL / "retries" / (item["attempt_id"] + ".json")).exists()
                or not item.get("input_integrity", {}).get("passed")):
            raise RecoveryError("retry must name the latest unchanged failed attempt, once")
        for output in item.get("outputs", []):
            target = path_in(project, output["path"])
            if not target.is_file() or sha(target) != output["sha256"]:
                raise RecoveryError("failed outputs must be preserved before retry authorization")
        return {"proposal": proposal, "failed": item, "next_attempt_number": len(attempts) + 1}
    if operation != "retire_primary_plan":
        raise RecoveryError("unsupported primary recovery operation")
    version = proposal.get("version", "")
    if not re.fullmatch(r"v[0-9]{3}", version) or (project / HISTORY / version).exists():
        raise RecoveryError("choose a new immutable vNNN protocol history version")
    if proposal.get("prior_outcomes_seen") is not True or proposal.get("new_analysis_phase") not in {"exploratory", "prospective_followup"}:
        raise RecoveryError("amended protocols must disclose observed prior outcomes and the new analysis phase")
    return {"proposal": proposal, "state": state, "rows": rows}


def apply(project, source, actor, operation, review_sha256, run_id, note):
    prepared = prepare(project, source, actor, operation)
    proposal = prepared["proposal"]
    authority = {"actor": actor, "cloud_review_sha256": review_sha256, "source_run_id": str(run_id),
                 "note": note, "source": source, "source_sha256": sha(project / source), "proposal": proposal}
    if operation == "approve_primary_retry":
        item = prepared["failed"]
        preserved = []
        for output in item.get("outputs", []):
            relative = f"experiments/recovery-artifacts/{item['attempt_id']}/{output['sha256']}{Path(output['path']).suffix}"
            target = path_in(project, relative)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(project / output["path"], target)
            preserved.append({**output, "preserved_path": relative})
        value = {**authority, "plan_sha256": proposal["plan_sha256"],
                 "failed_receipt_sha256": sha(receipt(project, item)),
                 "next_attempt_number": prepared["next_attempt_number"], "preserved_outputs": preserved}
        write(project / CONTROL / "retries" / (item["attempt_id"] + ".json"), value)
        return
    version = proposal["version"]
    folder = project / HISTORY / version
    frozen = {"experiments/plan.json", "experiments/budget.json", "experiments/registry.jsonl", "state/run.json"}
    preregs = list((project / "papers").glob("P[0-9][0-9]/preregistration.json"))
    for path in preregs:
        frozen.add(path.relative_to(project).as_posix())
        frozen.update(r["path"] for r in read(path).get("files", []))
    files = []
    for relative in sorted(frozen):
        target = path_in(project, relative)
        if not target.is_file():
            raise RecoveryError("original frozen input is missing")
        # Raw/private files remain in the sealed acquisition store, never copied into public history.
        archived = None
        from scripts.cloud_checkpoint import excluded
        if not excluded(relative):
            archived = f"{HISTORY}/{version}/files/{relative}"
            copy = project / archived
            copy.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(target, copy)
        files.append({"path": relative, "sha256": sha(target), "archive": archived})
    plan = read(project / "experiments/plan.json")
    manifest = {**authority, "version": version, "files": files,
                "run_ids": [r["run_id"] for r in plan["runs"]],
                "output_paths": [p for r in plan["runs"] for p in r["expected_outputs"]],
                "compute_ceiling_usd": read(project / "experiments/budget.json")["hard_ceiling_usd"],
                "cost_usd": sum(float(r["estimated_cost_usd"]) for r in prepared["rows"]),
                "attempt_receipts": [{"path": f"experiments/runs/{r['attempt_id']}/run.json", "sha256": sha(receipt(project, r))} for r in prepared["rows"]]}
    write(folder / "manifest.json", manifest)
    write(project / CONTROL / "versions" / (version + ".json"), {"manifest_sha256": sha(folder / "manifest.json")})
    # This owner decision withdraws old execution authority; it grants no new execution authority.
    state = prepared["state"]
    state["approved_gates"] = [g for g in state.get("approved_gates", []) if g not in {"G3", "G4"} and not g.startswith("G5")]
    state.update(stage_index=3, stage="experiment-design", gate="G3", status="awaiting_work")
    for key in ("ready_gate", "ready_artifact_sha256"):
        state.pop(key, None)
    state.setdefault("history", []).append({"event": "primary_protocol_retired", "version": version,
                                             "actor": actor, "source_run_id": str(run_id), "cloud_review_sha256": review_sha256})
    write(project / "state/run.json", state)
    (project / "experiments/registry.jsonl").write_text("", encoding="utf-8")
    for path in preregs:
        path.unlink()


def histories(project):
    values = []
    controls = project / CONTROL / "versions"
    for control in sorted(controls.glob("v[0-9][0-9][0-9].json")):
        manifest = project / HISTORY / control.stem / "manifest.json"
        if sha(manifest) != read(control)["manifest_sha256"]:
            raise RecoveryError("retired primary protocol seal changed")
        value = read(manifest)
        for row in value["files"]:
            if row["archive"] and sha(path_in(project, row["archive"])) != row["sha256"]:
                raise RecoveryError("retired primary protocol archive changed")
        for row in value["attempt_receipts"]:
            if sha(path_in(project, row["path"])) != row["sha256"]:
                raise RecoveryError("retired executor evidence changed")
        values.append(value)
    return values


def historical_cost(project):
    return sum(v["cost_usd"] for v in histories(project))


def gate_errors(project, gate, paper_id=None):
    if gate not in {"G3", "G4", "G5"}:
        return []
    try:
        versions = histories(project)
        if not versions:
            return []
        plan, budget = read(project / "experiments/plan.json"), read(project / "experiments/budget.json")
        retired_runs = {r for v in versions for r in v["run_ids"]}
        retired_outputs = {p for v in versions for p in v["output_paths"]}
        if any(r["run_id"] in retired_runs or set(r["expected_outputs"]) & retired_outputs for r in plan["runs"]):
            raise RecoveryError("amended primary plans require new run IDs and distinct output paths")
        ceiling = budget.get("hard_ceiling_usd")
        if (type(ceiling) not in (int, float) or not math.isfinite(ceiling)
                or ceiling > min(v["compute_ceiling_usd"] for v in versions)):
            raise RecoveryError("protocol amendment cannot reset or enlarge the original compute allowance")
        phase = "exploratory" if versions[-1]["proposal"]["new_analysis_phase"] == "exploratory" else "confirmatory"
        for paper in {r["paper_id"] for r in plan["runs"]}:
            if paper_id and paper != paper_id:
                continue
            from scripts import study_routes
            route = study_routes.route(project, paper)
            if route == "empirical":
                protocol = read(project / "papers" / paper / "experiment-evidence-plan.json")
                phases = {c["analysis_phase"] for c in protocol["comparisons"]}
            elif route == "meta_analysis":
                protocol = read(study_routes.protocol_path(project, paper))
                phases = {o["analysis_phase"] for o in protocol["outcomes"]}
            else:
                phases = {phase}  # Formal proof checks are not empirical confirmatory tests.
            if phases != {phase}:
                raise RecoveryError("amended analyses must retain their reviewed exploratory/prospective phase")
        return []
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return ["primary recovery: " + str(exc)]


def approved_exploration(project):
    versions = histories(project)
    return bool(versions and versions[-1]["proposal"]["new_analysis_phase"] == "exploratory"
                and not gate_errors(project, "G3"))
