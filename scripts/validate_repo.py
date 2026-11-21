#!/usr/bin/env python3
"""Validate core manifests and discovery entries; optional installations are explicit."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
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
    if jcr.get("quartile") in {"Q1", "Q2"} and jcr.get("evidence_status") not in {
        "direct-clarivate",
        "publisher-reported",
        "institutional-jcr-export",
    }:
        errors.append(f"{path.relative_to(ROOT)}: Q1/Q2 needs identified JCR evidence")
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


def validate_academic_style_rules(
    path: Path, upstream_path: Path, errors: list[str]
) -> None:
    value = load_json(path, errors)
    upstreams = load_json(upstream_path, errors)
    if not isinstance(value, dict) or not isinstance(upstreams, dict):
        return
    if value.get("schema_version") != "1.0":
        errors.append(f"{path.relative_to(ROOT)}: schema_version must be 1.0")
    upstream_map = {
        item.get("id"): item
        for item in upstreams.get("sources", [])
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }
    configured_sources = value.get("sources")
    if not isinstance(configured_sources, list) or not configured_sources:
        errors.append(f"{path.relative_to(ROOT)}: configured sources must be a nonempty array")
        return
    configured_ids: set[str] = set()
    for source in configured_sources:
        if not isinstance(source, dict):
            errors.append(f"{path.relative_to(ROOT)}: every source must be an object")
            continue
        source_id = source.get("id")
        configured_ids.add(str(source_id))
        upstream = upstream_map.get(source_id)
        if not upstream:
            errors.append(f"{path.relative_to(ROOT)}: unknown upstream source {source_id!r}")
        elif source.get("commit") != upstream.get("commit"):
            errors.append(f"{path.relative_to(ROOT)}: {source_id} commit differs from upstream lock")
    rules = value.get("rules")
    if not isinstance(rules, list) or not rules:
        errors.append(f"{path.relative_to(ROOT)}: rules must be a non-empty array")
        return
    rule_ids: set[str] = set()
    for rule in rules:
        if not isinstance(rule, dict):
            errors.append(f"{path.relative_to(ROOT)}: every rule must be an object")
            continue
        rule_id = rule.get("id")
        if not isinstance(rule_id, str) or not NAME_RE.fullmatch(rule_id):
            errors.append(f"{path.relative_to(ROOT)}: invalid rule id {rule_id!r}")
        elif rule_id in rule_ids:
            errors.append(f"{path.relative_to(ROOT)}: duplicate rule id {rule_id}")
        else:
            rule_ids.add(rule_id)
        if rule.get("confidence") not in {"high", "moderate"}:
            errors.append(f"{path.relative_to(ROOT)}: invalid confidence for {rule_id}")
        source_ids = rule.get("source_ids")
        if not isinstance(source_ids, list) or not source_ids or any(
            source_id not in configured_ids for source_id in source_ids
        ):
            errors.append(f"{path.relative_to(ROOT)}: invalid source_ids for {rule_id}")
        try:
            re.compile(str(rule.get("pattern", "")), re.I | re.M)
        except re.error as exc:
            errors.append(f"{path.relative_to(ROOT)}: invalid regex for {rule_id}: {exc}")


def validate_stage_config(path: Path, errors: list[str]) -> None:
    value = load_json(path, errors)
    stages = value.get("stages") if isinstance(value, dict) else None
    if not isinstance(stages, dict):
        errors.append(f"{path.relative_to(ROOT)}: stages must be an object")
        return
    for name, stage in stages.items():
        if not isinstance(stage, dict):
            errors.append(f"{path.relative_to(ROOT)}: {name} must be an object")
            continue
        gate = EXPECTED_STAGES.get(name)
        if gate and stage.get("gate", gate) != gate:
            errors.append(f"{path.relative_to(ROOT)}: legacy label {name} must map to {gate}")
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


def validate_editorial_integration(errors: list[str]) -> None:
    lock = load_json(ROOT / "integrations/editorial-upstreams.lock.json", errors)
    if not isinstance(lock, dict):
        return
    sources = lock.get("sources", [])
    if not isinstance(sources, list) or any(not isinstance(row, dict) for row in sources):
        errors.append("editorial sources must be an array of objects")
        return
    for source in sources:
        if not source.get("license") or not SHA_RE.fullmatch(source.get("commit", "")):
            errors.append("editorial source license or commit is missing")
        for item in source.get("files", []):
            relative = Path(item.get("path", ""))
            if relative.is_absolute() or ".." in relative.parts or not relative.as_posix().startswith(f"third_party/{source['id']}/"):
                errors.append("editorial vendored path escapes its source directory")
                continue
            try:
                value = (ROOT / relative).read_bytes().replace(b"\r\n", b"\n")
                if hashlib.sha256(value).hexdigest() != item.get("canonical_lf_sha256"):
                    errors.append(f"editorial vendored source hash mismatch: {relative}")
            except OSError as exc:
                errors.append(f"editorial vendored source unavailable: {exc}")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--integrations", action="store_true", help="Also verify installed optional tool resources; this may require prior installation.")
    args = parser.parse_args(argv)
    errors: list[str] = []

    for path in sorted((ROOT / "schemas").glob("*.json")):
        load_json(path, errors)
    from scripts.cloud_job import job_schema
    if load_json(ROOT / "schemas/cloud-job.schema.json", errors) != job_schema():
        errors.append("cloud-job schema is stale; regenerate with python -m scripts.cloud_job schema")
    for path in sorted((ROOT / "venues").glob("*/venue.json")):
        validate_venue(path, errors)
    upstream_path = ROOT / "integrations" / "upstreams.lock.json"
    validate_upstreams(upstream_path, errors)
    validate_academic_style_rules(
        ROOT / "config" / "academic-style-rules.json", upstream_path, errors
    )
    validate_stage_config(ROOT / "config" / "stages.json", errors)
    validate_editorial_integration(errors)
    if args.integrations:
        from scripts.research_methods import installation_errors
        from scripts.ccfa_runtime import installation_errors as ccfa_installation_errors
        from scripts.research_toolkit import installation_errors as toolkit_installation_errors
        from scripts.literaturectl import installation_errors as literature_installation_errors
        for check in (installation_errors, ccfa_installation_errors, toolkit_installation_errors, literature_installation_errors):
            errors.extend(check(ROOT))

    plugin = load_json(ROOT / ".claude-plugin" / "plugin.json", errors)
    if isinstance(plugin, dict) and plugin.get("name") != "doctoral-research-os":
        errors.append(".claude-plugin/plugin.json: unexpected plugin name")
    version = project_version(ROOT / "pyproject.toml", errors)
    if isinstance(plugin, dict) and version and plugin.get("version") != version:
        errors.append("Plugin version must match pyproject.toml")
    mcp = load_json(ROOT / ".mcp.json", errors)
    if isinstance(mcp, dict):
        servers = mcp.get("mcpServers", {})
        if not isinstance(servers, dict):
            errors.append(".mcp.json: mcpServers must be an object")
        else:
            for name, server in servers.items():
                if not isinstance(server, dict) or not (server.get("command") or server.get("url")):
                    errors.append(f".mcp.json: {name} needs a command or URL")

    for relative in ("AGENTS.md", "README.md", "references/workflow.md", "references/stage-contracts.md",
                     "scripts/researchctl.py", "scripts/autopilot.py", "skills/start/SKILL.md", "skills/continue/SKILL.md"):
        if not (ROOT / relative).is_file():
            errors.append(f"{relative} is required by the documented entry points")

    skill_names: dict[str, Path] = {}
    skill_paths = list((ROOT / "skills").glob("*/SKILL.md"))
    skill_paths += list((ROOT / ".agents" / "skills").glob("*/SKILL.md"))
    for path in sorted(skill_paths):
        name = validate_skill(path, errors)
        if name in skill_names:
            first = skill_names[name]
            try:
                identical = first.read_bytes() == path.read_bytes()
                from scripts.skill_discovery import current
                pair = {first.relative_to(ROOT).as_posix(), path.relative_to(ROOT).as_posix()}
                generated = pair == {f"skills/{path.parent.name}/SKILL.md", f".agents/skills/{path.parent.name}/SKILL.md"} and current(ROOT, path.parent.name)
            except (OSError, ValueError):
                identical = False
                generated = False
            if not identical and not generated:
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
