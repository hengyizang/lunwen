"""Small deterministic artifact helpers. No model calls or experiment execution."""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from functools import lru_cache


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def path_in(project: Path, relative: str, *, exists: bool = True) -> Path:
    candidate = Path(relative)
    if not relative or candidate.is_absolute() or ".." in candidate.parts or "\\" in relative or ":" in relative:
        raise ValueError("artifact needs a project-relative path")
    target = project / candidate
    if any(p.is_symlink() for p in (target, *target.parents)) or not target.resolve().is_relative_to(project.resolve()):
        raise ValueError("symlink or escaped artifact is forbidden")
    if exists and not target.is_file():
        raise ValueError(f"artifact is missing: {relative}")
    return target


def regular_file(project: Path, relative: str, error_type, *, invalid: str, missing: str) -> Path:
    value = Path(relative)
    if value.is_absolute() or not value.parts or ".." in value.parts:
        raise error_type(invalid)
    path = (project / value).resolve()
    if project.resolve() not in path.parents or not path.is_file() or path.is_symlink():
        raise error_type(f"{missing}: {relative}")
    return path


def read(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("artifact must be a JSON object")
    return value


def strict_json(value, *, duplicate_error: str, nonfinite_error: str | None = None, error_type=ValueError):
    def unique(pairs):
        result = dict(pairs)
        if len(result) != len(pairs):
            raise error_type(duplicate_error)
        return result
    def nonfinite(_):
        raise error_type(nonfinite_error)
    return json.loads(value, object_pairs_hook=unique,
                      **({"parse_constant": nonfinite} if nonfinite_error is not None else {}))


def write(path: Path, value: dict, *, indent=2, sort_keys=False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
        json.dump(value, handle, ensure_ascii=False, indent=indent, sort_keys=sort_keys)
        handle.write("\n")
        temporary = handle.name
    os.replace(temporary, path)


def record(project: Path, paths: list[Path], module: str) -> None:
    from scripts.output_provenance import record_model_writes
    record_model_writes(project, paths, family="other", provider="deterministic-control-plane",
                        model=module, role="artifact-builder", run_id="quality-refresh")


def matches_origin(project: Path, path: Path, **expected) -> bool:
    from scripts.output_provenance import current_origin
    origin = current_origin(project, path)
    return origin.get("status") == "tracked" and all(origin.get(key) == value for key, value in expected.items())


def seal_manifest(project: Path, paths: list[Path], manifest: Path, module: str,
                  metadata: dict, *, files_key="outputs", record_outputs=True) -> None:
    """Bind existing outputs; callers retain their report and execution policies."""
    write(manifest, {**metadata, "implementation_sha256": sha(Path(__file__).resolve().parents[1] / module),
                    files_key: [{"path": path.relative_to(project).as_posix(), "sha256": sha(path)} for path in paths]})
    record(project, [*(paths if record_outputs else []), manifest], module)


def paper_audit_cli(description, projects_root, audit, report_name, error_type) -> int:
    import argparse
    import re
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("--project", required=True)
    parser.add_argument("--paper", required=True)
    args = parser.parse_args()
    paper = projects_root / args.project / "papers" / args.paper
    try:
        if not paper.is_dir() or not re.fullmatch(r"P[0-9]{2}", args.paper):
            raise error_type("project/paper does not exist")
        report = audit(paper)
        write(paper / "reviews" / report_name, report)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report["status"] == "pass" else 1
    except error_type as exc:
        print(f"error: {exc}")
        return 2


def bound_source(project: Path, value: dict) -> dict:
    target = path_in(project, value["path"])
    actual = sha(target)
    if value.get("sha256") != actual or not str(value.get("locator", "")).strip():
        raise ValueError("source needs its current hash and a page/section/record locator")
    return {"path": value["path"], "sha256": actual, "locator": value["locator"]}


@lru_cache(maxsize=64)
def _schema_validator(source: bytes):
    import math
    from jsonschema import Draft202012Validator, ValidationError, validators
    def number(checker, value):
        try:
            return type(value) in (int, float) and math.isfinite(value)
        except OverflowError:
            return False
    def nonblank(validator, minimum, value, schema):
        if isinstance(value, str) and len(value.strip()) < minimum:
            yield ValidationError("string is empty or shorter than its declared minimum")
    def unique(validator, required, value, schema):
        normalized = [item.strip() if isinstance(item, str) else item for item in value] if isinstance(value, list) else value
        yield from Draft202012Validator.VALIDATORS["uniqueItems"](validator, required, normalized, schema)
    types = Draft202012Validator.TYPE_CHECKER.redefine_many({
        "number": number, "integer": lambda checker, value: type(value) is int})
    cls = validators.extend(Draft202012Validator, {"minLength": nonblank, "uniqueItems": unique}, type_checker=types)
    return cls(json.loads(source))


def _schema_source(name: str) -> bytes:
    if Path(name).name != name or not name.endswith(".schema.json"):
        raise ValueError("an exact repository schema name is required")
    return (Path(__file__).resolve().parents[1] / "schemas" / name).read_bytes()


def schema_contract(name: str) -> dict:
    """Derive compact writer navigation from the same schema as validation."""
    source = _schema_source(name)
    document, required, conditions = json.loads(source), {}, {}
    def visit(node, path):
        if not isinstance(node, dict):
            return
        if node.get("required"):
            required[path or "root"] = node["required"]
        for key, child in node.get("properties", {}).items():
            visit(child, (path + "." if path else "") + key)
        if isinstance(node.get("items"), dict):
            visit(node["items"], path + "[]")
        for clause in node.get("allOf", []):
            if "if" in clause:
                conditions.setdefault(path or "root", []).append({"if": clause["if"], "required": clause.get("then", {}).get("required", [])})
    visit(document, "")
    root_values = []
    for key, node in document.get("properties", {}).items():
        values = node.get("enum", [node["const"]] if "const" in node else [])
        if values:
            root_values.append(key + "=" + "|".join(value if isinstance(value, str) else json.dumps(value) for value in values))
    return {"schema": "schemas/" + name, "sha256": hashlib.sha256(source).hexdigest(),
        "required_fields": required, "conditional_required_fields": conditions,
        "root_values": root_values,
        "optional_root_fields": sorted(set(document.get("properties", {})) - set(document.get("required", []))),
        "scope": "field navigation; exact type/value and conditional rules remain in the referenced schema"}



def schema_errors(value, name: str) -> list[str]:
    """Use repository schemas once; scientific cross-record checks stay local.

    Cache by current schema bytes, not a clock. Diagnostics never echo input
    values, which can contain private research text.
    """
    validator = _schema_validator(_schema_source(name))
    errors = []
    for error in validator.iter_errors(value):
        path = "".join(f"[{key}]" if isinstance(key, int) else ("." if index else "") + key
                       for index, key in enumerate(error.absolute_path))
        kind, expected = error.validator, error.validator_value
        if kind == "required":
            key = next((key for key in expected if f"{key!r} is a required property" == error.message), "required_field")
            path += ("." if path else "") + key
            message = "must be provided"
        elif kind == "const": message = "must be " + str(expected)
        elif kind == "enum":
            message = "must be one of " + ", ".join(map(str, expected))
            if None in expected:
                message += " when supplied"
        elif kind == "minItems": message = f"must contain at least {expected} item(s)"
        elif kind == "minLength": message = "must be a non-empty string"
        elif kind == "uniqueItems": message = "must not contain duplicates"
        elif kind == "type": message = "must have type " + str(expected)
        elif kind == "pattern" and expected == "^https://": message = "must use an HTTPS primary-source URL"
        else: message = str(kind) + " constraint failed"
        errors.append(f"{path or name}: {message}")
    return list(dict.fromkeys(errors))
