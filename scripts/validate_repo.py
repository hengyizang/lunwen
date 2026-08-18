#!/usr/bin/env python3
"""Validate repository manifests and extension structure without dependencies."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
EXPECTED_STAGES = {
    "intake": "G0",
    "topic-intelligence": "G1",
    "paper-architecture": "G2",
    "experiment-design": "G3",
    "experiment-execution": "G4",
    "writing-and-review": "G5",
}


def load_json(path: Path, errors: list[str]) -> Any | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"{path.relative_to(ROOT)}: {exc}")
        return None


def frontmatter(path: Path, errors: list[str]) -> dict[str, str]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        errors.append(f"{path.relative_to(ROOT)}: {exc}")
        return {}
    if not lines or lines[0].strip() != "---":
        errors.append(f"{path.relative_to(ROOT)}: missing YAML frontmatter")
        return {}
    try:
        end = lines.index("---", 1)
    except ValueError:
        errors.append(f"{path.relative_to(ROOT)}: unclosed YAML frontmatter")
        return {}
    fields: dict[str, str] = {}
    for line in lines[1:end]:
        if not line.strip() or line.startswith((" ", "\t")):
            continue
        if ":" not in line:
            errors.append(f"{path.relative_to(ROOT)}: invalid frontmatter line {line!r}")
            continue
        key, value = line.split(":", 1)
        fields[key.strip()] = value.strip().strip('"').strip("'")
    return fields


def validate_skill(path: Path, errors: list[str]) -> str | None:
    fields = frontmatter(path, errors)
    name = fields.get("name") or path.parent.name
    if not NAME_RE.fullmatch(name):
        errors.append(f"{path.relative_to(ROOT)}: invalid skill name {name!r}")
    if not fields.get("description"):
        errors.append(f"{path.relative_to(ROOT)}: description is required")
    return name


def validate_agent(path: Path, errors: list[str]) -> str | None:
    fields = frontmatter(path, errors)
    name = fields.get("name")
    if not name or not NAME_RE.fullmatch(name):
        errors.append(f"{path.relative_to(ROOT)}: invalid or missing agent name")
    if not fields.get("description"):
        errors.append(f"{path.relative_to(ROOT)}: description is required")
    return name


def validate_venue(path: Path, errors: list[str]) -> None:
    value = load_json(path, errors)
    if not isinstance(value, dict):
        return
    required = [
        "schema_version",
        "venue_id",
        "name",
        "publisher",
        "issn",
        "scope",
        "jcr",
        "templates",
        "requirements",
        "sources",
        "verified_at",
        "reverification",
    ]
    for key in required:
        if key not in value:
            errors.append(f"{path.relative_to(ROOT)}: missing {key}")
    jcr = value.get("jcr", {})
    if jcr.get("quartile") == "Q1" and jcr.get("evidence_status") not in {
        "direct-clarivate",
        "publisher-reported",
        "institutional-jcr-export",
    }:
        errors.append(f"{path.relative_to(ROOT)}: Q1 needs identified JCR evidence")
    if jcr.get("direct_clarivate_recheck_required") is not True:
        errors.append(f"{path.relative_to(ROOT)}: G5 Clarivate recheck must be required")
    for source in value.get("sources", []):
        if not str(source.get("url", "")).startswith("https://"):
            errors.append(f"{path.relative_to(ROOT)}: source URL must use HTTPS")
        if not source.get("accessed_at"):
            errors.append(f"{path.relative_to(ROOT)}: source access date is required")


def validate_upstreams(path: Path, errors: list[str]) -> None:
    value = load_json(path, errors)
    if not isinstance(value, dict):
        return
    sources = value.get("sources")
    if not isinstance(sources, list) or not sources:
        errors.append(f"{path.relative_to(ROOT)}: sources must be a non-empty array")
        return
    source_ids: set[str] = set()
    for source in sources:
        if not isinstance(source, dict):
            errors.append(f"{path.relative_to(ROOT)}: every source must be an object")
            continue
        source_id = source.get("id")
        if not isinstance(source_id, str) or not NAME_RE.fullmatch(source_id):
            errors.append(f"{path.relative_to(ROOT)}: invalid upstream id {source_id!r}")
        elif source_id in source_ids:
            errors.append(f"{path.relative_to(ROOT)}: duplicate upstream id {source_id}")
        else:
            source_ids.add(source_id)
        if not str(source.get("repository", "")).startswith("https://github.com/"):
            errors.append(f"{path.relative_to(ROOT)}: {source_id} repository must use GitHub HTTPS")
        if not SHA_RE.fullmatch(str(source.get("commit", ""))):
            errors.append(f"{path.relative_to(ROOT)}: {source_id} needs a full commit SHA")
        if not str(source.get("license_source_url", "")).startswith("https://github.com/"):
            errors.append(f"{path.relative_to(ROOT)}: {source_id} needs a GitHub license source")
        if source.get("enabled_by_default") is not False:
            errors.append(f"{path.relative_to(ROOT)}: {source_id} must be opt-in")
        selected = source.get("selected_skills", [])
        if not isinstance(selected, list) or len(selected) != len(set(selected)):
            errors.append(f"{path.relative_to(ROOT)}: {source_id} selected_skills must be unique")
        for skill in selected:
            if not isinstance(skill, str) or not NAME_RE.fullmatch(skill):
                errors.append(f"{path.relative_to(ROOT)}: invalid selected skill {skill!r}")


def validate_stage_config(path: Path, errors: list[str]) -> None:
    value = load_json(path, errors)
    stages = value.get("stages") if isinstance(value, dict) else None
    if not isinstance(stages, dict):
        errors.append(f"{path.relative_to(ROOT)}: stages must be an object")
        return
    if set(stages) != set(EXPECTED_STAGES):
        errors.append(f"{path.relative_to(ROOT)}: stage names do not match G0-G5")
    for name, gate in EXPECTED_STAGES.items():
        stage = stages.get(name)
        if not isinstance(stage, dict):
            continue
        if stage.get("gate") != gate:
            errors.append(f"{path.relative_to(ROOT)}: {name} must map to {gate}")
        if not str(stage.get("author_task", "")).strip():
            errors.append(f"{path.relative_to(ROOT)}: {name} needs author_task")


def project_version(path: Path, errors: list[str]) -> str | None:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        errors.append(f"{path.relative_to(ROOT)}: {exc}")
        return None
    project_match = re.search(r"(?ms)^\[project\]\s*(.*?)(?=^\[|\Z)", text)
    version_match = (
        re.search(r'(?m)^version\s*=\s*"([^"]+)"\s*$', project_match.group(1))
        if project_match
        else None
    )
    if not version_match:
        errors.append(f"{path.relative_to(ROOT)}: project.version is required")
        return None
    return version_match.group(1)


def main() -> int:
    errors: list[str] = []

    for path in sorted((ROOT / "schemas").glob("*.json")):
        load_json(path, errors)
    for path in sorted((ROOT / "venues").glob("*/venue.json")):
        validate_venue(path, errors)
    validate_upstreams(ROOT / "integrations" / "upstreams.lock.json", errors)
    validate_stage_config(ROOT / "config" / "stages.json", errors)

    plugin = load_json(ROOT / ".claude-plugin" / "plugin.json", errors)
    if isinstance(plugin, dict) and plugin.get("name") != "doctoral-research-os":
        errors.append(".claude-plugin/plugin.json: unexpected plugin name")
    version = project_version(ROOT / "pyproject.toml", errors)
    if isinstance(plugin, dict) and version and plugin.get("version") != version:
        errors.append("Plugin version must match pyproject.toml")
    mcp = load_json(ROOT / ".mcp.json", errors)
    codex = (
        mcp.get("mcpServers", {}).get("codex-review", {})
        if isinstance(mcp, dict)
        else {}
    )
    if codex.get("command") != "codex" or codex.get("args") != ["mcp-server"]:
        errors.append(".mcp.json: codex-review must run codex mcp-server")
    try:
        start_script = (ROOT / "scripts" / "start.sh").read_text(encoding="utf-8")
    except OSError as exc:
        errors.append(f"scripts/start.sh: {exc}")
    else:
        if "scripts/autopilot.py start" not in start_script:
            errors.append("scripts/start.sh must invoke the bounded autopilot")
    package_script = ROOT / "scripts" / "submission_package.py"
    if not package_script.is_file():
        errors.append("scripts/submission_package.py is required")
    package_skill = ROOT / "skills" / "package" / "SKILL.md"
    if not package_skill.is_file():
        errors.append("skills/package/SKILL.md is required")

    skill_names: dict[str, Path] = {}
    skill_paths = list((ROOT / "skills").glob("*/SKILL.md"))
    skill_paths += list((ROOT / ".agents" / "skills").glob("*/SKILL.md"))
    for path in sorted(skill_paths):
        name = validate_skill(path, errors)
        if name in skill_names:
            first = skill_names[name]
            try:
                identical = first.read_bytes() == path.read_bytes()
            except OSError:
                identical = False
            if not identical:
                errors.append(f"duplicate skill name with different content: {name}")
        elif name:
            skill_names[name] = path

    agent_names: set[str] = set()
    for path in sorted((ROOT / "agents").glob("*.md")):
        name = validate_agent(path, errors)
        if name in agent_names:
            errors.append(f"duplicate agent name: {name}")
        if name:
            agent_names.add(name)

    if errors:
        print("Repository validation failed:", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 2
    print(
        f"Repository validation passed: {len(skill_names)} skills, "
        f"{len(agent_names)} agents, "
        f"{len(list((ROOT / 'venues').glob('*/venue.json')))} venue(s)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
