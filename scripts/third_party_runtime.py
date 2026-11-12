#!/usr/bin/env python3
"""Owner-authorized third-party runtime registry and advisory run receipts.

Deterministic local tooling only. This module registers and runs third-party
tools; it never produces a scientific artifact, approves a gate, writes stage
state, or substitutes for scripts/experiment_runner.py. See
docs/THIRD-PARTY-RUNTIME-POLICY.md.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "integrations" / "third-party-runtime.json"
REPORTS = ROOT / "reports" / "third-party"
TIERS = ("local-readonly", "network-no-credentials", "credentials-or-paid")
ID_RE = re.compile(r"[a-z][a-z0-9-]{1,79}")
SAFE_ENV = ("PATH", "HOME", "LANG", "LC_ALL", "TMPDIR", "TEMP", "TMP",
            "SYSTEMROOT", "USERPROFILE", "PYTHONPATH")


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _display(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def _load() -> dict:
    value = json.loads(REGISTRY.read_text(encoding="utf-8"))
    if value.get("schema_version") != "1.0" or not isinstance(value.get("tools"), list):
        raise ValueError("unsupported third-party runtime registry")
    return value


def _save(value: dict) -> None:
    REGISTRY.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8")


def _sha_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sha_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8", "replace")).hexdigest()


def _inside(raw: str) -> Path:
    path = Path(raw)
    if not path.is_absolute():
        path = ROOT / path
    resolved = path.resolve()
    resolved.relative_to(ROOT.resolve())
    if path.is_symlink():
        raise ValueError("symlinked paths are not accepted: " + raw)
    return resolved


def _find(value: dict, identity: str) -> dict:
    for row in value["tools"]:
        if row.get("id") == identity:
            return row
    raise ValueError("tool is not registered: " + identity)


def _receipt(name: str, payload: dict) -> Path:
    folder = REPORTS / "receipts"
    folder.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    target = folder / f"{name}-{stamp}-{_sha_text(json.dumps(payload, sort_keys=True))[:12]}.json"
    body = {
        "schema_version": "1.0",
        "recorded_at": _now(),
        "advisory_only": True,
        "gate_authority": False,
        "registered_experiment": False,
        "scientific_evidence": False,
        "policy": "docs/THIRD-PARTY-RUNTIME-POLICY.md",
        **payload,
    }
    target.write_text(json.dumps(body, ensure_ascii=False, indent=2) + "\n",
                      encoding="utf-8")
    return target


def cmd_register(args: argparse.Namespace) -> int:
    if not ID_RE.fullmatch(args.id):
        raise ValueError("id must be lowercase letters, digits and hyphens")
    if not args.repo.startswith("https://"):
        raise ValueError("repository must use an HTTPS URL")
    if args.tier not in TIERS:
        raise ValueError("unknown risk tier: " + args.tier)
    value = _load()
    if any(row.get("id") == args.id for row in value["tools"]):
        raise ValueError("tool id is already registered: " + args.id)
    row = {
        "id": args.id,
        "repository": args.repo,
        "ref": args.ref,
        "license": args.license,
        "license_source_url": args.license_url or "",
        "access_date": args.access_date or _now()[:10],
        "risk_tier": args.tier,
        "capabilities": list(args.capability or []),
        "endpoints": list(args.endpoint or []),
        "note": args.note or "",
        "registered_at": _now(),
        "deployment_authorized": True,
        "standalone_runtime_deployed": False,
        "last_run_at": None,
        "authorization": "docs/OWNER-DECISION-2026-11-09.md",
    }
    value["tools"].append(row)
    _save(value)
    print(f"registered {args.id} (tier={args.tier}, ref={args.ref})")
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    value = _load()
    rows = value["tools"]
    if not rows:
        print("no third-party runtimes registered yet")
        return 0
    for row in rows:
        print("{id:22} {tier:24} authorized={auth} deployed={dep} ref={ref}".format(
            id=row["id"], tier=row["risk_tier"],
            auth=str(row.get("deployment_authorized", False)).lower(),
            dep=str(row.get("standalone_runtime_deployed", False)).lower(),
            ref=row.get("ref", "")))
    return 0


def cmd_mark_deployed(args: argparse.Namespace) -> int:
    value = _load()
    row = _find(value, args.id)
    row["standalone_runtime_deployed"] = args.deployed
    row["deployment_observed_at"] = _now() if args.deployed else None
    _save(value)
    print(f"{args.id}: standalone_runtime_deployed={args.deployed}")
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    value = _load()
    row = _find(value, args.id)
    if not row.get("deployment_authorized", False):
        raise ValueError("deployment is not authorized for " + args.id)
    argv = [part for part in args.argv if part != "--"]
    if not argv:
        raise ValueError("provide a command after --")
    cwd = str(_inside(args.cwd)) if args.cwd else str(ROOT)
    env = {key: os.environ[key] for key in SAFE_ENV if key in os.environ}
    plan = {
        "tool_id": args.id,
        "repository": row["repository"],
        "ref": row["ref"],
        "risk_tier": row["risk_tier"],
        "argv": argv,
        "cwd": cwd,
        "env_keys": sorted(env),
        "timeout_seconds": args.timeout,
        "mode": "executed" if args.execute else "dry_run",
        "warning": "No repository credentials are passed. Output is advisory and is not a registered experiment.",
    }
    if not args.execute:
        print(json.dumps(plan, ensure_ascii=False, indent=2))
        print("dry run only; add --execute to actually start the tool")
        if "--execute" in argv:
            print("note: --execute after -- belongs to the tool; put it before -- to run",
                  file=sys.stderr)
        return 0
    result = subprocess.run(argv, cwd=cwd, env=env, shell=False,
                            capture_output=True, text=True,
                            timeout=args.timeout, check=False)
    plan.update({
        "exit_code": result.returncode,
        "stdout_sha256": _sha_text(result.stdout or ""),
        "stderr_sha256": _sha_text(result.stderr or ""),
        "stdout_preview": (result.stdout or "")[:400],
        "stderr_preview": (result.stderr or "")[:400],
    })
    receipt = _receipt(f"run-{args.id}", plan)
    row["last_run_at"] = _now()
    _save(value)
    print(json.dumps({"exit_code": result.returncode,
                      "receipt": _display(receipt),
                      "advisory_only": True}, ensure_ascii=False, indent=2))
    if result.stdout:
        print(result.stdout[:2000])
    if result.stderr:
        print(result.stderr[:2000], file=sys.stderr)
    return 0


def cmd_bind_output(args: argparse.Namespace) -> int:
    value = _load()
    row = _find(value, args.id)
    path = _inside(args.file)
    if not path.is_file():
        raise ValueError("output file does not exist: " + args.file)
    payload = {
        "kind": "output_binding",
        "tool_id": args.id,
        "repository": row["repository"],
        "ref": row["ref"],
        "path": str(path.relative_to(ROOT)),
        "sha256": _sha_file(path),
        "size_bytes": path.stat().st_size,
        "note": "Hash binding only. Scientific use still requires primary-source verification and a claim-evidence link.",
    }
    receipt = _receipt(f"output-{args.id}", payload)
    print(json.dumps({"receipt": _display(receipt),
                      "sha256": payload["sha256"],
                      "advisory_only": True}, ensure_ascii=False, indent=2))
    return 0


ADAPTATION_KINDS = ("launch", "wrapper", "fork")
PLACEHOLDER_RE = re.compile(r"\{[a-z_]+\}")
PLACEHOLDERS = ("{tool_root}", "{input}", "{output}")
OUTPUT_PREFIX = "reports/third-party/"


def _adapter_dir(identity: str) -> Path:
    if not ID_RE.fullmatch(identity):
        raise ValueError("invalid tool id")
    return ROOT / "adapters" / identity


def _launch_config(identity: str, config_path: str = "") -> tuple[dict, Path]:
    path = Path(config_path) if config_path else _adapter_dir(identity) / "launch.json"
    if not path.is_absolute():
        path = ROOT / path
    path = path.resolve()
    if not path.is_file():
        raise ValueError("adapter config is missing; run scaffold first: " + str(path))
    config = json.loads(path.read_text(encoding="utf-8"))
    if config.get("schema_version") != "1.0" or config.get("id") != identity:
        raise ValueError("adapter config has an unsupported schema or mismatched id")
    if config.get("adaptation") not in ADAPTATION_KINDS:
        raise ValueError("unknown adaptation kind")
    argv = config.get("argv")
    if not isinstance(argv, list) or not argv or not all(isinstance(x, str) and x for x in argv):
        raise ValueError("adapter argv must be a nonempty list of strings")
    output = str(config.get("output_path", ""))
    if not output.startswith(OUTPUT_PREFIX) or ".." in Path(output).parts:
        raise ValueError("output_path must stay under " + OUTPUT_PREFIX)
    return config, path


def _expand(argv: list[str], tool_root: Path, input_path: Path, output_path: Path) -> list[str]:
    values = {"{tool_root}": str(tool_root), "{input}": str(input_path),
              "{output}": str(output_path)}
    expanded = []
    for part in argv:
        for key, value in values.items():
            part = part.replace(key, value)
        leftover = PLACEHOLDER_RE.findall(part)
        if leftover:
            raise ValueError("unknown adapter placeholder: " + ", ".join(leftover))
        expanded.append(part)
    return expanded


def cmd_scaffold(args: argparse.Namespace) -> int:
    _find(_load(), args.id)
    folder = _adapter_dir(args.id)
    config_path = folder / "launch.json"
    if config_path.exists() and not args.force:
        raise ValueError("adapter already exists; use --force to overwrite: " + str(config_path))
    folder.mkdir(parents=True, exist_ok=True)
    config = {
        "schema_version": "1.0",
        "id": args.id,
        "adaptation": args.kind,
        "tool_root": f"third_party/{args.id}",
        "argv": ["python3", "{tool_root}/cli.py", "--input", "{input}",
                 "--out", "{output}"],
        "output_path": f"{OUTPUT_PREFIX}{args.id}/result.json",
        "timeout_seconds": 900,
        "env_keys": ["PATH", "HOME", "LANG", "PYTHONPATH"],
        "disabled_upstream_behaviors": [
            "auto_submit", "gate_approval", "favorable_result_selection",
            "provenance_rewrite"],
        "notes": "Describe exactly what you changed in the upstream and why.",
    }
    config_path.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n",
                           encoding="utf-8")
    guidance = {
        "launch": "Do not edit upstream source. Supply the missing runtime: install dependencies, start its service, and point argv at its real entry point.",
        "wrapper": "Do not edit upstream source. Add a thin adapter that translates project inputs to upstream arguments and normalizes its output. Disable the upstream's automatic approval, submission and result-selection defaults via flags or config.",
        "fork": "You are changing upstream source. Keep the original license, record every patch in PATCHES.md, and check the license obligations in docs/THIRD-PARTY-ADAPTATION.md before redistributing.",
    }
    (folder / "README.md").write_text(
        f"# Adapter for {args.id}\n\n"
        f"Kind: `{args.kind}`\n\n{guidance[args.kind]}\n\n"
        "Edit `launch.json`, then run:\n\n"
        f"```\npython3 scripts/third_party_runtime.py wrap --id {args.id} "
        "--input path/to/input.json --execute\n```\n\n"
        "Outputs stay under `reports/third-party/` and are advisory only.\n",
        encoding="utf-8")
    if args.kind == "fork":
        (folder / "PATCHES.md").write_text(
            f"# Upstream patches for {args.id}\n\n"
            "- Base repository / ref:\n- License and notice retained:\n"
            "- Files changed and reason:\n- Upstream behaviors removed:\n"
            "- Rebase/upgrade plan:\n", encoding="utf-8")
    print(f"scaffolded {args.kind} adapter at {_display(folder)}")
    return 0


def cmd_wrap(args: argparse.Namespace) -> int:
    value = _load()
    row = _find(value, args.id)
    if not row.get("deployment_authorized", False):
        raise ValueError("deployment is not authorized for " + args.id)
    config, config_path = _launch_config(args.id, args.config)
    tool_root = Path(str(config.get("tool_root", "")))
    if not tool_root.is_absolute():
        tool_root = ROOT / tool_root
    tool_root = tool_root.resolve()
    input_path = _inside(args.input)
    if not input_path.is_file():
        raise ValueError("input file does not exist: " + args.input)
    output_path = _inside(str(config["output_path"]))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    argv = _expand(list(config["argv"]), tool_root, input_path, output_path)
    allowed = set(SAFE_ENV) & set(config.get("env_keys", []))
    env = {key: os.environ[key] for key in allowed if key in os.environ}
    cwd = str(tool_root) if tool_root.is_dir() else str(ROOT)
    plan = {
        "kind": "adapted_run",
        "tool_id": args.id,
        "adaptation": config["adaptation"],
        "repository": row["repository"],
        "ref": row["ref"],
        "license": row["license"],
        "adapter_config": _display(config_path),
        "adapter_config_sha256": _sha_file(config_path),
        "tool_root": str(tool_root),
        "tool_root_exists": tool_root.is_dir(),
        "argv": argv,
        "cwd": cwd,
        "env_keys": sorted(env),
        "input": _display(input_path),
        "input_sha256": _sha_file(input_path),
        "output": _display(output_path),
        "timeout_seconds": int(config.get("timeout_seconds", 900)),
        "declared_disabled_upstream_behaviors": config.get("disabled_upstream_behaviors", []),
        "mode": "executed" if args.execute else "dry_run",
        "note": "Adapted upstream output is advisory. It is not a registered experiment, a gate decision, or scientific evidence.",
    }
    if not args.execute:
        print(json.dumps(plan, ensure_ascii=False, indent=2))
        print("dry run only; add --execute to actually call the adapted tool")
        return 0
    result = subprocess.run(argv, cwd=cwd, env=env, shell=False,
                            capture_output=True, text=True,
                            timeout=plan["timeout_seconds"], check=False)
    plan.update({
        "exit_code": result.returncode,
        "stdout_sha256": _sha_text(result.stdout or ""),
        "stderr_sha256": _sha_text(result.stderr or ""),
        "stdout_preview": (result.stdout or "")[:400],
        "stderr_preview": (result.stderr or "")[:400],
        "output_exists": output_path.is_file(),
        "output_sha256": _sha_file(output_path) if output_path.is_file() else None,
    })
    receipt = _receipt(f"adapt-{args.id}", plan)
    row["last_adapted_at"] = _now()
    _save(value)
    print(json.dumps({"exit_code": result.returncode,
                      "output_sha256": plan["output_sha256"],
                      "receipt": _display(receipt),
                      "advisory_only": True}, ensure_ascii=False, indent=2))
    if result.stdout:
        print(result.stdout[:2000])
    if result.stderr:
        print(result.stderr[:2000], file=sys.stderr)
    return 0


def cmd_promote(args: argparse.Namespace) -> int:
    value = _load()
    row = _find(value, args.id)
    path = _inside(args.receipt)
    if not path.is_file():
        raise ValueError("receipt does not exist: " + args.receipt)
    body = json.loads(path.read_text(encoding="utf-8"))
    if body.get("advisory_only") is not True or not body.get("recorded_at"):
        raise ValueError("only hash-bound tool receipts can be promoted")
    if not any(key.endswith("sha256") and body[key] for key in body):
        raise ValueError("receipt has no hash binding")
    if not str(args.authorized_by).strip():
        raise ValueError("explicit owner authorization is required")
    digest = _sha_file(path)
    record = {
        "schema_version": "1.0",
        "status": "candidate_unverified",
        "recorded_at": _now(),
        "authorized_by": args.authorized_by,
        "authorization": "docs/OWNER-DECISION-2026-11-09-EFFECT-FIRST.md",
        "tool_id": args.id,
        "repository": row["repository"],
        "ref": row["ref"],
        "source_receipt": _display(path),
        "source_receipt_sha256": digest,
        "output_sha256": body.get("output_sha256"),
        "source_verified": False,
        "claim_linked": False,
        "note": "Candidate material only. Primary-source verification and a claim-evidence link are still required before any scientific claim.",
    }
    folder = ROOT / "evidence" / "candidates"
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / f"{args.id}-{digest[:16]}.json"
    target.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n",
                      encoding="utf-8")
    print(json.dumps({"candidate": _display(target), "status": record["status"],
                      "source_verified": False}, ensure_ascii=False, indent=2))
    return 0


def cmd_compare(args: argparse.Namespace) -> int:
    value = _load()
    if len(args.receipt) < 2:
        raise ValueError("compare needs at least two receipts on the same input")
    rows = []
    seen_tools: list[str] = []
    for raw in args.receipt:
        path = _inside(raw)
        if not path.is_file():
            raise ValueError("receipt does not exist: " + raw)
        body = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(body, dict) or not body.get("recorded_at"):
            raise ValueError("not a tool receipt: " + raw)
        tool_id = str(body.get("tool_id") or "unknown")
        if tool_id != "unknown":
            _find(value, tool_id)
        seen_tools.append(tool_id)
        rows.append({
            "tool_id": tool_id,
            "path": _display(path),
            "sha256": _sha_file(path),
            "input_sha256": body.get("input_sha256"),
            "output_sha256": body.get("output_sha256"),
            "exit_code": body.get("exit_code"),
        })
    inputs = {row["input_sha256"] for row in rows if row["input_sha256"]}
    same_input = len(inputs) == 1 and bool(inputs)
    groups: dict[str, list[str]] = {}
    for row in rows:
        groups.setdefault(str(row["output_sha256"] or "none"), []).append(row["tool_id"])
    report = {
        "schema_version": "1.0",
        "kind": "tool_comparison",
        "recorded_at": _now(),
        "decision": args.decision,
        "stage": args.stage,
        "same_input": same_input,
        "input_sha256": next(iter(inputs)) if same_input else None,
        "tools": seen_tools,
        "receipts": rows,
        "output_groups": [{"output_sha256": key, "tools": names}
                          for key, names in groups.items()],
        "agreement_count": sum(1 for names in groups.values() if len(names) > 1),
        "distinct_output_count": len(groups),
        "adoption": "pending",
        "advisory_only": True,
        "gate_authority": False,
        "note": "Disagreements are preserved. No vote, averaging, or automatic adoption. A difference is a lead to inspect, not a scientific conclusion.",
    }
    folder = ROOT / "reports" / "third-party" / "comparisons"
    folder.mkdir(parents=True, exist_ok=True)
    digest = _sha_text(json.dumps(report, sort_keys=True, default=str))
    target = folder / f"compare-{digest[:16]}.json"
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                      encoding="utf-8")
    print(json.dumps({"comparison": _display(target),
                      "same_input": same_input,
                      "distinct_output_count": len(groups),
                      "adoption": "pending"}, ensure_ascii=False, indent=2))
    return 0


def cmd_adopt(args: argparse.Namespace) -> int:
    path = _inside(args.comparison)
    if not path.is_file():
        raise ValueError("comparison does not exist: " + args.comparison)
    body = json.loads(path.read_text(encoding="utf-8"))
    if body.get("kind") != "tool_comparison" or not isinstance(body.get("tools"), list):
        raise ValueError("not a tool comparison report")
    if args.tool_id not in body["tools"]:
        raise ValueError("tool is not part of this comparison: " + args.tool_id)
    if not str(args.reason).strip() or not str(args.by).strip():
        raise ValueError("an explicit reason and owner actor are required")
    record = {
        "schema_version": "1.0",
        "kind": "tool_adoption",
        "recorded_at": _now(),
        "comparison": _display(path),
        "comparison_sha256": _sha_file(path),
        "decision": body.get("decision"),
        "tool_id": args.tool_id,
        "verdict": args.verdict,
        "reason": args.reason,
        "recorded_by": args.by,
        "note": "Adoption records whether a tool changed a research decision. It does not create evidence or approve a gate.",
    }
    folder = ROOT / "reports" / "third-party" / "adoptions"
    folder.mkdir(parents=True, exist_ok=True)
    digest = _sha_text(json.dumps(record, sort_keys=True, default=str))
    target = folder / f"{args.tool_id}-{digest[:12]}.json"
    target.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n",
                      encoding="utf-8")
    print(json.dumps({"adoption": _display(target), "tool_id": args.tool_id,
                      "verdict": args.verdict}, ensure_ascii=False, indent=2))
    return 0


def cmd_free(args: argparse.Namespace) -> int:
    argv = [part for part in args.argv if part != "--"]
    if not argv:
        raise ValueError("provide a command after --")
    cwd = str(_inside(args.cwd)) if args.cwd else str(ROOT)
    env = {key: os.environ[key] for key in SAFE_ENV if key in os.environ}
    plan = {
        "kind": "free_call",
        "source": args.source,
        "argv": argv,
        "cwd": cwd,
        "env_keys": sorted(env),
        "timeout_seconds": args.timeout,
        "mode": "executed" if args.execute else "dry_run",
        "no_registry_entry": True,
        "note": "No registration, decision point, adapter, comparison or output field required. The caller chooses where outputs go; project state and claim records stay under the control plane.",
    }
    if not args.execute:
        print(json.dumps(plan, ensure_ascii=False, indent=2))
        print("dry run only; add --execute to run")
        if "--execute" in argv:
            print("note: --execute after -- belongs to the tool; put it before -- to run",
                  file=sys.stderr)
        return 0
    result = subprocess.run(argv, cwd=cwd, env=env, shell=False,
                            capture_output=True, text=True,
                            timeout=args.timeout, check=False)
    plan.update({
        "exit_code": result.returncode,
        "stdout_sha256": _sha_text(result.stdout or ""),
        "stderr_sha256": _sha_text(result.stderr or ""),
        "stdout_preview": (result.stdout or "")[:400],
        "stderr_preview": (result.stderr or "")[:400],
    })
    receipt = None if args.no_receipt else _receipt("free", plan)
    print(json.dumps({"exit_code": result.returncode,
                      "receipt": _display(receipt) if receipt else None,
                      "advisory_only": True}, ensure_ascii=False, indent=2))
    if result.stdout:
        print(result.stdout[:2000])
    if result.stderr:
        print(result.stderr[:2000], file=sys.stderr)
    return 0


def _adapter_errors() -> list[str]:
    errors: list[str] = []
    folder = ROOT / "adapters"
    if not folder.is_dir():
        return errors
    for config_path in sorted(folder.glob("*/launch.json")):
        identity = config_path.parent.name
        try:
            config, _ = _launch_config(identity, str(config_path))
            _expand(list(config["argv"]), ROOT, ROOT / "input.json",
                    ROOT / OUTPUT_PREFIX / "result.json")
        except (OSError, ValueError, KeyError, TypeError) as exc:
            errors.append(f"adapter {identity}: {exc}")
    return errors


def cmd_verify(args: argparse.Namespace) -> int:
    value = _load()
    errors: list[str] = []
    seen: set[str] = set()
    for row in value["tools"]:
        identity = str(row.get("id", ""))
        if not ID_RE.fullmatch(identity) or identity in seen:
            errors.append("invalid or duplicate id: " + identity)
        seen.add(identity)
        if not str(row.get("repository", "")).startswith("https://"):
            errors.append(identity + ": repository must be an HTTPS URL")
        for key in ("ref", "license", "access_date"):
            if not str(row.get(key, "")).strip():
                errors.append(identity + ": missing " + key)
        if row.get("risk_tier") not in TIERS:
            errors.append(identity + ": invalid risk tier")
        if not isinstance(row.get("capabilities", []), list):
            errors.append(identity + ": capabilities must be an array")
        if row.get("standalone_runtime_deployed") and not row.get("deployment_authorized"):
            errors.append(identity + ": deployed without authorization")
    errors.extend(_adapter_errors())
    if errors:
        for line in errors:
            print("ERROR " + line, file=sys.stderr)
        return 1
    print(f"ok: {len(seen)} registered third-party runtime(s); authorization and deployment fields are consistent")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("register", help="register a third-party tool")
    p.add_argument("--id", required=True)
    p.add_argument("--repo", required=True, help="HTTPS repository URL")
    p.add_argument("--ref", default="HEAD", help="branch, tag or commit")
    p.add_argument("--tier", choices=TIERS, default="local-readonly")
    p.add_argument("--license", default="unknown", help="license identifier or unknown")
    p.add_argument("--license-url", default="")
    p.add_argument("--access-date", default="", help="YYYY-MM-DD; defaults to today")
    p.add_argument("--capability", action="append")
    p.add_argument("--endpoint", action="append", help="network endpoint the tool contacts")
    p.add_argument("--note", default="")
    p.set_defaults(func=cmd_register)

    p = sub.add_parser("list", help="list registered tools")
    p.set_defaults(func=cmd_list)

    p = sub.add_parser("mark-deployed", help="record the observed deployment state")
    p.add_argument("--id", required=True)
    p.add_argument("--deployed", choices=("true", "false"), required=True)
    p.set_defaults(func=lambda a: cmd_mark_deployed(
        argparse.Namespace(id=a.id, deployed=a.deployed == "true")))

    p = sub.add_parser("run", help="run a registered tool (dry run by default)")
    p.add_argument("--id", required=True)
    p.add_argument("--cwd", default="", help="working directory inside this repository")
    p.add_argument("--timeout", type=int, default=900)
    p.add_argument("--execute", action="store_true", help="actually start the tool")
    p.add_argument("argv", nargs=argparse.REMAINDER)
    p.set_defaults(func=cmd_run)

    p = sub.add_parser("bind-output", help="hash-bind a local tool output")
    p.add_argument("--id", required=True)
    p.add_argument("--file", required=True)
    p.set_defaults(func=cmd_bind_output)

    p = sub.add_parser("scaffold", help="create an adaptation config for a registered tool")
    p.add_argument("--id", required=True)
    p.add_argument("--kind", choices=ADAPTATION_KINDS, default="launch")
    p.add_argument("--force", action="store_true", help="overwrite an existing adapter")
    p.set_defaults(func=cmd_scaffold)

    p = sub.add_parser("wrap", help="call an adapted tool through its launch config")
    p.add_argument("--id", required=True)
    p.add_argument("--config", default="", help="override path to launch.json")
    p.add_argument("--input", required=True, help="project-owned input file")
    p.add_argument("--execute", action="store_true", help="actually call the tool")
    p.set_defaults(func=cmd_wrap)

    p = sub.add_parser("promote", help="put a hash-bound tool receipt into the candidate-evidence queue")
    p.add_argument("--id", required=True)
    p.add_argument("--receipt", required=True, help="path to a tool run/output receipt")
    p.add_argument("--authorized-by", required=True, help="explicit owner actor")
    p.set_defaults(func=cmd_promote)

    p = sub.add_parser("free", help="run any project/skill/command directly, no registration required")
    p.add_argument("--source", default="", help="optional GitHub URL, local path or skill name; recorded only")
    p.add_argument("--cwd", default="", help="working directory inside this repository")
    p.add_argument("--timeout", type=int, default=900)
    p.add_argument("--execute", action="store_true", help="actually run it")
    p.add_argument("--no-receipt", action="store_true", help="skip the optional receipt")
    p.add_argument("argv", nargs=argparse.REMAINDER)
    p.set_defaults(func=cmd_free)

    p = sub.add_parser("compare", help="compare tool receipts on the same input, preserving disagreement")
    p.add_argument("--receipt", action="append", required=True, help="repeat for each tool")
    p.add_argument("--decision", default="", help="which research decision this comparison serves")
    p.add_argument("--stage", default="", help="G0-G5 or a named decision point")
    p.set_defaults(func=cmd_compare)

    p = sub.add_parser("adopt", help="record whether a tool actually changed a decision")
    p.add_argument("--comparison", required=True)
    p.add_argument("--tool-id", required=True)
    p.add_argument("--verdict", choices=("adopted", "rejected"), required=True)
    p.add_argument("--reason", required=True)
    p.add_argument("--by", required=True, help="explicit owner actor")
    p.set_defaults(func=cmd_adopt)

    p = sub.add_parser("verify", help="check registry consistency")
    p.set_defaults(func=cmd_verify)

    args = parser.parse_args()
    try:
        return int(args.func(args))
    except (OSError, ValueError, KeyError, subprocess.TimeoutExpired) as exc:
        print("ERROR " + str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
