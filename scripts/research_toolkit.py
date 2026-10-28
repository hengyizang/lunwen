"""Task-selected research-tool guidance; no upstream runtime or provider calls."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re

from scripts.research_artifacts import path_in, read, record, sha, write

ROOT = Path(__file__).resolve().parents[1]
CATALOG = "integrations/research-automation-tools.json"
MODULE = "scripts/research_toolkit.py"
OUTPUT = "reports/research-toolkit"
STAGES = {"intake", "topic-intelligence", "paper-architecture", "experiment-design",
          "experiment-execution", "writing-and-review"}
MARKER = "RESEARCH_TOOLKIT_PACKET="


def _digest(value: dict) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _text(value, label, maximum=4000):
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise ValueError(label + " must be bounded nonempty text")
    return value


def catalog(root: Path = ROOT) -> dict:
    value = read(path_in(root, CATALOG))
    rows = value.get("tools")
    if value.get("schema_version") != "1.0" or not isinstance(rows, list) or not rows:
        raise ValueError("research-tool catalog is empty or unsupported")
    checked = {}
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("research-tool entry must be an object")
        identity = row.get("id")
        if not isinstance(identity, str) or not re.fullmatch(r"[a-z][a-z0-9-]{1,79}", identity) or identity in checked:
            raise ValueError("research-tool IDs must be distinct lowercase names")
        if not isinstance(row.get("repository"), str) or not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", row["repository"]):
            raise ValueError("research tool needs its upstream repository")
        if not isinstance(row.get("commit"), str) or not re.fullmatch(r"[0-9a-f]{40}", row["commit"]):
            raise ValueError("research tool needs a full pinned commit")
        recipe = row.get("recipe_path")
        if recipe != row.get("skill_path") or not isinstance(recipe, str) or not recipe.startswith("integrations/codex-research-tools/skills/"):
            raise ValueError("research-tool recipe must be its installed adapter skill")
        if sha(path_in(root, recipe)) != row.get("recipe_sha256"):
            raise ValueError("research-tool recipe changed: " + identity)
        stages, operations = row.get("stages"), row.get("native_operations")
        if (not isinstance(stages, list) or not stages or any(not isinstance(s, str) or s not in STAGES for s in stages)
                or not isinstance(operations, list) or any(not isinstance(op, str) or not op for op in operations)):
            raise ValueError("research tool has invalid native stages or operations")
        checked[identity] = row
    return checked


def installation_errors(root: Path = ROOT) -> list[str]:
    try:
        catalog(root)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return ["invalid research-tool installation: " + str(exc)]
    return []


def _binding(project: Path, value: dict) -> dict:
    if not isinstance(value, dict) or set(value) != {"path", "sha256"}:
        raise ValueError("research-tool input needs exactly path and sha256")
    relative = value["path"]
    if not isinstance(relative, str) or not relative.startswith(("program/", "papers/", "evidence/", "literature/", "reports/", "experiments/", "data/")):
        raise ValueError("research-tool input must be an existing research artifact")
    target = path_in(project, relative)
    if sha(target) != value["sha256"]:
        raise ValueError("research-tool input changed: " + relative)
    return {"path": relative, "sha256": value["sha256"]}


def _prepare(project: Path, relative: str, root: Path) -> dict:
    if not relative.startswith("program/") or not relative.endswith(".json"):
        raise ValueError("research-tool request belongs under program/*.json")
    request_path = path_in(project, relative)
    if request_path.stat().st_size > 64000:
        raise ValueError("research-tool request exceeds 64 KB")
    request = read(request_path)
    required = {"id", "stage", "tool_ids", "task", "input_bindings"}
    if set(request) - required - {"paper_id"} or required - set(request):
        raise ValueError("research-tool request has missing or unsupported fields")
    identity = request["id"]
    if not isinstance(identity, str) or not re.fullmatch(r"[a-z][a-z0-9-]{1,79}", identity):
        raise ValueError("research-tool task ID must be a lowercase name")
    stage = request["stage"]
    if not isinstance(stage, str) or stage not in STAGES:
        raise ValueError("unsupported research-tool stage")
    _text(request["task"], "research task")
    if "paper_id" in request and (not isinstance(request["paper_id"], str) or not re.fullmatch(r"P[0-9]{2}", request["paper_id"])):
        raise ValueError("paper_id must identify one existing paper")
    if "paper_id" in request and not (project / "papers" / request["paper_id"]).is_dir():
        raise ValueError("selected paper does not exist")
    selected = request["tool_ids"]
    if (not isinstance(selected, list) or not 1 <= len(selected) <= 10
            or any(not isinstance(item, str) for item in selected) or len(selected) != len(set(selected))):
        raise ValueError("select one to ten distinct research tools for the actual task")
    available = catalog(root)
    recipes = []
    for name in selected:
        if name not in available or stage not in available[name]["stages"]:
            raise ValueError("research tool is unknown or unsuitable for this stage: " + name)
        row = available[name]
        recipes.append({key: row[key] for key in ("id", "repository", "commit", "recipe_path", "recipe_sha256", "native_operations")})
    inputs = request["input_bindings"]
    if not isinstance(inputs, list) or not 1 <= len(inputs) <= 40:
        raise ValueError("research-tool task needs one to forty current input bindings")
    bindings = [_binding(project, value) for value in inputs]
    if len({row["path"] for row in bindings}) != len(bindings):
        raise ValueError("duplicate research-tool input binding")
    authority = []
    for name in ("state/run.json", "intake/constraints.json"):
        path = project / name
        if path.is_file():
            path = path_in(project, name)
            if name == "state/run.json" and read(path).get("stage") != stage:
                raise ValueError("research-tool stage differs from the current project stage")
            authority.append({"path": name, "sha256": sha(path)})
    return {"schema_version": "1.0", "status": "prepared_not_executed", "request": request,
            "request_binding": {"path": relative, "sha256": sha(request_path)},
            "input_bindings": bindings, "authority_bindings": authority, "recipes": recipes,
            "catalog_sha256": sha(path_in(root, CATALOG)), "builder_sha256": sha(path_in(root, MODULE)),
            "paid_calls": 0, "upstream_runtime_executed": False, "scientific_validation": "not_assessed",
            "execution_authority": "Existing cloud controls, approved G3 runner and G0-G5 human gates remain required."}


def refresh(project: Path, relative: str, *, root: Path = ROOT) -> dict:
    from scripts.literaturectl import require_cloud
    require_cloud()
    payload = _prepare(project, relative, root)
    identity = _digest(payload)
    result = {**payload, "packet_sha256": identity,
              "packet_path": f"{OUTPUT}/{payload['request']['id']}-{identity}.json"}
    target = path_in(project, result["packet_path"], exists=False)
    if target.exists():
        from scripts.output_provenance import current_origin
        origin = current_origin(project, target)
        if read(target) != result or origin.get("status") != "tracked" or origin.get("model") != MODULE:
            raise ValueError("existing research-tool packet changed or lacks executor provenance")
    else:
        write(target, result)
        record(project, [target], MODULE)
    return result


def task_context(project: Path | None, stage: str, role: str, context: str, *, root: Path = ROOT) -> str:
    """Read only an explicit packet marker; never turn selection into execution."""
    markers = [line[len(MARKER):] for line in context.splitlines() if line.startswith(MARKER)]
    if not markers:
        return ""
    if len(markers) != 1 or project is None:
        raise ValueError("one research-tool packet marker and its project are required")
    relative = markers[0]
    if not re.fullmatch(re.escape(OUTPUT) + r"/[a-z][a-z0-9-]{1,79}-[a-f0-9]{64}\.json", relative):
        raise ValueError("research-tool packet must identify its immutable report")
    target = path_in(project, relative)
    packet = read(target)
    payload = _prepare(project, packet.get("request_binding", {}).get("path", ""), root)
    identity = _digest(payload)
    expected = {**payload, "packet_sha256": identity,
                "packet_path": f"{OUTPUT}/{payload['request']['id']}-{identity}.json"}
    from scripts.output_provenance import current_origin
    origin = current_origin(project, target)
    if (packet != expected or relative != expected["packet_path"] or origin.get("status") != "tracked"
            or origin.get("model") != MODULE or packet["request"]["stage"] != stage):
        raise ValueError("research-tool packet changed, is stale, or belongs to another stage")
    boundary = {"planner": "Read-only semantic planning; no final scientific files.",
                "critic": "Independent source-based assessment; do not infer another role's verdict.",
                "writer": "OpenAI independently writes artifacts; guidance cannot self-approve science.",
                "remediator": "OpenAI resolves recorded findings without hiding failed or adverse evidence."}.get(role)
    if boundary is None:
        raise ValueError("unsupported research-tool model role")
    task = ("Independently assess the bound research inputs; the requesting author's task narrative is omitted."
            if role == "critic" else "Task: " + packet["request"]["task"])
    blocks = ["Task-selected research-tool guidance (prepared only; no upstream agent execution).", boundary, task,
              "Bound input paths and hashes: " + json.dumps(packet["input_bindings"], ensure_ascii=False),
              "Hashes identify inputs; they do not mean their contents were read or verified. Use the existing stage-scoped source snapshot or explicit program/context-plan.json selections. Request a controlled text extract for unavailable or oversized sources before drawing conclusions."]
    for row in packet["recipes"]:
        blocks.append(f"Reviewed adapter {row['id']} from {row['repository']}@{row['commit']} "
                      f"(SHA-256 {row['recipe_sha256']}):\n" + path_in(root, row["recipe_path"]).read_text(encoding="utf-8"))
    return "\n\n".join(blocks)
