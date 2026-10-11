"""Automatic cloud Unicode hygiene, with preserved originals and honest scope.

The pinned remover handles character carriers in editable prose. Statistical
watermarks, authorship and image pixels are not inferred from this audit.
"""
from __future__ import annotations

import json
import csv
import io
import os
import re
import tempfile
import uuid
import zipfile
from pathlib import Path

from scripts import artifact_ownership, output_provenance, watermark_cleanup as cleaner
from scripts.research_artifacts import path_in, read, sha, write

ROOT = Path(__file__).resolve().parents[1]
PREFIX = "reports/manuscript-hygiene"
PROVIDER = "deterministic-manuscript-hygiene"
EDITABLE = {".txt", ".md", ".tex", ".docx"}
READ_ONLY = {".json", ".csv", ".tsv", ".bib", ".svg", ".pdf"}
MAX_FILES = 300
MAX_TOTAL_BYTES = 40_000_000
MAX_HISTORY = 200
LIMITS = {"statistical_watermarks": "not_assessed", "image_watermarks": "not_assessed",
          "watermark_absence_verified": False, "ai_authorship_verified": False,
          "scientific_equivalence_proven": False, "paid_calls": 0,
          "synonym_rotation": False, "random_sentence_shuffling": False,
          "ai_disclosure_preserved": True, "human_scientific_review_required": True}


def _cloud() -> None:
    if os.environ.get("GITHUB_ACTIONS", "").lower() != "true" and os.environ.get("DR_OS_CLOUD_EXECUTOR") != "1":
        raise ValueError("automatic manuscript hygiene requires cloud execution")


def _paper(project: Path, paper_id: str) -> Path:
    if not re.fullmatch(r"P[0-9]{2}", str(paper_id)):
        raise ValueError("invalid hygiene paper ID")
    paper = path_in(project, f"papers/{paper_id}", exists=False)
    if not paper.is_dir():
        raise ValueError("hygiene paper directory is missing")
    return paper


def inventory(project: Path, paper_id: str) -> list[Path]:
    """Include drafts, TeX includes, tables, supplements and upload prose."""
    paper = _paper(project, paper_id)
    files = []
    total = 0
    for name in ("manuscript", "figures", "tables", "supplement", "submission-materials"):
        directory = path_in(project, f"papers/{paper_id}/{name}", exists=False)
        if not directory.exists():
            continue
        if not directory.is_dir():
            raise ValueError("hygiene input root must be a directory")
        for root, dirs, names in os.walk(directory, followlinks=False):
            for child in dirs + names:
                target = Path(root) / child
                path_in(project, target.relative_to(project).as_posix(), exists=False)
            for child in names:
                target = Path(root) / child
                if target.name == "figure-provenance.json" or target.name.endswith(".image-source.json"):
                    continue
                if target.suffix.lower() in EDITABLE | READ_ONLY:
                    if not target.is_file() or target.stat().st_size > cleaner.MAX_SOURCE_BYTES:
                        raise ValueError("hygiene source is missing, irregular or oversized")
                    total += target.stat().st_size
                    files.append(target)
    for relative in ("disclosures.json", "reviews/response-matrix.csv"):
        target = path_in(project, f"papers/{paper_id}/{relative}", exists=False)
        if target.is_file():
            total += target.stat().st_size
            files.append(target)
    if not files or not any(p.parent == paper / "manuscript" for p in files):
        raise ValueError("hygiene requires manuscript sources")
    if len(files) > MAX_FILES or total > MAX_TOTAL_BYTES:
        raise ValueError("complete hygiene inventory exceeds its cloud audit bound")
    return sorted(set(files))


def _implementation() -> dict:
    _, upstream = cleaner._upstream()
    return {"upstream": upstream, "files": [{"path": name, "sha256": sha(ROOT / name)} for name in (
        "scripts/manuscript_hygiene.py", "scripts/watermark_cleanup.py", "scripts/artifact_ownership.py")]}


def _findings(details: dict) -> tuple[list[dict], list[dict]]:
    changed, retained = [], []
    for item in details.get("paragraphs", [details]):
        locator = {"paragraph": item["paragraph"]} if "paragraph" in item else {}
        changed.extend({**row, **locator} for row in item.get("changes", []))
        retained.extend({**row, **locator} for row in item.get("retained_findings", []))
    return changed, retained


def _scan(payload: bytes, suffix: str, *, allow_image_only: bool = False) -> tuple[bytes, dict, str, str]:
    if suffix in EDITABLE:
        derived, details, before, after = cleaner._process(payload, suffix)
        changes, retained = _findings(details)
        auxiliary = []
        if suffix == ".docx":
            # Body/table cleaning deliberately leaves header/footer/notes and
            # package metadata unchanged. Inspect their text without editing.
            from lxml import etree as ET
            with zipfile.ZipFile(io.BytesIO(payload)) as archive:
                for name in sorted(archive.namelist()):
                    if (name != cleaner.DOCUMENT and name.startswith("word/") and name.endswith(".xml")
                            and re.match(r"word/(?:header|footer|footnotes|endnotes|comments)", name)):
                        content = archive.read(name)
                        if len(content) > cleaner.MAX_TEXT_BYTES * 3:
                            raise ValueError("DOCX auxiliary text exceeds the audit bound")
                        try:
                            root = ET.fromstring(content, parser=ET.XMLParser(resolve_entities=False, no_network=True))
                        except ET.XMLSyntaxError as exc:
                            raise ValueError("invalid DOCX auxiliary XML") from exc
                        if root.getroottree().docinfo.doctype:
                            raise ValueError("DOCX auxiliary entities/DTD are unsupported")
                        text = "\n".join(node.text or "" for node in root.iter() if node.tag in {cleaner.W + "t", cleaner.M + "t"})
                        _, audit = cleaner.clean_text_candidate(text)
                        auxiliary.append({"part": name, "removed_count": audit["removed_count"],
                                          "changes": audit["changes"], "retained_findings": audit["retained_findings"]})
        return derived, {"remaining_count": len(changes), "changes": changes, "retained_findings": retained,
                         "auxiliary": auxiliary, "scope": "supported prose; protected spans retained"}, before, after
    if suffix == ".pdf":
        import fitz
        with fitz.open(stream=payload, filetype="pdf") as document:
            if document.needs_pass or document.page_count > 300:
                raise ValueError("PDF is encrypted or exceeds the 300-page audit bound")
            text = "\n".join(page.get_text(sort=True) for page in document)
        if not text.strip():
            if allow_image_only:
                return payload, {"remaining_count": 0, "changes": [], "retained_findings": [], "auxiliary": [],
                    "scope": "image-only figure PDF; no text to inspect; image watermarks not assessed"}, "", ""
            raise ValueError("PDF has no extractable text; source/render review is required")
        scope = "PDF extracted text only; image pixels and invisible PDF objects not assessed"
    else:
        text = payload.decode("utf-8")
        if suffix == ".json":
            def strings(value):
                if isinstance(value, str):
                    return [value]
                if isinstance(value, list):
                    return [item for child in value for item in strings(child)]
                if isinstance(value, dict):
                    return [item for key, child in value.items() for item in [str(key), *strings(child)]]
                return []
            text = "\n".join(strings(json.loads(text)))
        elif suffix in {".csv", ".tsv"}:
            text = "\n".join(cell for row in csv.reader(io.StringIO(text), delimiter="\t" if suffix == ".tsv" else ",") for cell in row)
        elif suffix == ".svg":
            from lxml import etree as ET
            try:
                root = ET.fromstring(payload, parser=ET.XMLParser(resolve_entities=False, no_network=True))
            except ET.XMLSyntaxError as exc:
                raise ValueError("invalid SVG text XML") from exc
            if root.getroottree().docinfo.doctype:
                raise ValueError("SVG entities/DTD are unsupported")
            text = "\n".join(root.itertext())
        scope = "read-only decoded text or metadata; no automatic normalization"
    _, details = cleaner.clean_text_candidate(text, "txt")
    return payload, {"remaining_count": details["removed_count"], "changes": details["changes"],
                     "retained_findings": details["retained_findings"], "auxiliary": [], "scope": scope}, text, text


def _can_apply(project: Path, path: Path, origin: dict) -> bool:
    return (path.suffix.lower() in EDITABLE
            and not artifact_ownership.executor_owned(project, path.relative_to(project).as_posix())
            and origin.get("status") == "tracked"
            and (origin.get("family") == "openai" or origin.get("provider") == "human-attestation"))


def _record(project: Path, paths: list[Path], run_id: str, *, family: str = "other") -> None:
    output_provenance.record_model_writes(project, paths, family=family, provider=PROVIDER,
        model="pinned-unicode-cleaner", role="unicode-hygiene-not-authorship-attestation", run_id=run_id)


def _apply(project: Path, paper_id: str, target: Path, payload: bytes, derived: bytes,
           analysis: dict, before: str, after: str, implementation: dict) -> str:
    origin = output_provenance.current_origin(project, target)
    if not _can_apply(project, target, origin):
        raise ValueError("automatic cleanup requires a current OpenAI or human-authored editable source")
    if path_in(project, target.relative_to(project).as_posix()).read_bytes() != payload:
        raise ValueError("hygiene source changed before cleanup")
    identifier = uuid.uuid4().hex
    relative = f"{PREFIX}/{paper_id}/changes/{identifier}/receipt.json"
    receipt = path_in(project, relative, exists=False)
    receipt.parent.mkdir(parents=True, exist_ok=False)
    outputs = {"original" + target.suffix: payload, "cleaned" + target.suffix: derived,
               "changes.json": (json.dumps(analysis, ensure_ascii=False, indent=2) + "\n").encode(),
               "diff.txt": cleaner._diff(before, after)}
    for name, content in outputs.items():
        (receipt.parent / name).write_bytes(content)
    value = {"schema_version": "1.0", "paper_id": paper_id, "id": identifier,
             "source": {"path": target.relative_to(project).as_posix(), "sha256": cleaner.digest(payload), "origin": origin},
             "cleaned_sha256": cleaner.digest(derived), "implementation": implementation,
             "removed_count": analysis["remaining_count"], "original_preserved": True,
             "outputs": [{"path": (receipt.parent / name).relative_to(project).as_posix(), "sha256": cleaner.digest(content)}
                         for name, content in outputs.items()], **LIMITS}
    write(receipt, value)
    # A durable, protected original and receipt precede the atomic replacement.
    # The original family survives this deterministic edit, including AI use.
    _record(project, [receipt.parent / name for name in outputs] + [receipt], identifier)
    if path_in(project, target.relative_to(project).as_posix()).read_bytes() != payload:
        raise ValueError("hygiene source changed before atomic replacement")
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(derived)
        if path_in(project, target.relative_to(project).as_posix()).read_bytes() != payload:
            raise ValueError("hygiene source changed before atomic replacement")
        os.replace(temporary, target)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()
    _record(project, [target], identifier, family=origin["family"])
    return relative


def audit(project: Path, paper_id: str) -> dict:
    """Read-only recomputation used at G5 and immediately before packaging."""
    files, errors, warnings = [], [], []
    findings = 0
    for path in inventory(project, paper_id):
        relative = path.relative_to(project).as_posix()
        payload = path.read_bytes()
        try:
            if path.suffix.lower() == ".pdf":
                _, detail, _, _ = _scan(payload, ".pdf", allow_image_only=path.is_relative_to(_paper(project, paper_id) / "figures"))
            else:
                _, detail, _, _ = _scan(payload, path.suffix.lower())
            auxiliary_count = sum(row["removed_count"] for row in detail["auxiliary"])
            findings += detail["remaining_count"] + len(detail["retained_findings"]) + auxiliary_count
            if findings > cleaner.MAX_FINDINGS:
                raise ValueError("complete manuscript findings exceed the audit bound")
            if detail["remaining_count"] or auxiliary_count:
                errors.append(relative + ": removable character artifacts remain; clean editable sources and rebuild generated outputs")
            if detail["retained_findings"] or any(row["retained_findings"] for row in detail["auxiliary"]):
                warnings.append(relative + ": protected/legitimate Unicode retained for contextual human review")
            if detail["scope"].startswith("image-only figure PDF"):
                warnings.append(relative + ": image watermarks not assessed; existing figure provenance and human visual review still apply")
            files.append({"path": relative, "sha256": cleaner.digest(payload),
                          "origin": output_provenance.current_origin(project, path), **detail})
        except (ValueError, OSError, ImportError, RuntimeError, RecursionError, csv.Error, zipfile.BadZipFile) as exc:
            errors.append(relative + ": " + str(exc))
            files.append({"path": relative, "sha256": cleaner.digest(payload), "scan_error": str(exc)})
        if path_in(project, relative).read_bytes() != payload:
            raise ValueError("hygiene source changed during scan")
    return {"schema_version": "1.0", "paper_id": paper_id, "status": "pass" if not errors else "revise",
            "files": files, "errors": errors, "warnings": warnings, "implementation": _implementation(),
            "pass_meaning": "no removable artifacts in the assessed supported prose; retained findings remain visible",
            **LIMITS}


def _validate_change(project: Path, receipt: Path, implementation: dict) -> None:
    value = read(receipt)
    identifier = receipt.parent.name
    if (not re.fullmatch(r"[0-9a-f]{32}", identifier) or value.get("id") != identifier
            or value.get("implementation") != implementation or value.get("original_preserved") is not True
            or any(value.get(key) != expected for key, expected in LIMITS.items())):
        raise ValueError("hygiene change receipt is stale or makes an unsupported claim")
    origin = output_provenance.current_origin(project, receipt)
    if origin.get("status") != "tracked" or origin.get("provider") != PROVIDER or origin.get("run_id") != identifier:
        raise ValueError("hygiene change lacks protected control-plane provenance")
    source = path_in(project, value["source"]["path"], exists=False)
    if not source.is_relative_to(_paper(project, value["paper_id"])) or source.suffix.lower() not in EDITABLE:
        raise ValueError("hygiene change source escapes its paper")
    old_origin = value["source"]["origin"]
    if old_origin.get("status") != "tracked" or not (old_origin.get("family") == "openai" or old_origin.get("provider") == "human-attestation"):
        raise ValueError("hygiene change cannot conceal unknown or Claude source ancestry")
    original = path_in(project, (receipt.parent / ("original" + source.suffix)).relative_to(project).as_posix())
    payload = original.read_bytes()
    derived, analysis, before, after = _scan(payload, source.suffix.lower())
    expected = {"original" + source.suffix: payload, "cleaned" + source.suffix: derived,
                "changes.json": (json.dumps(analysis, ensure_ascii=False, indent=2) + "\n").encode(),
                "diff.txt": cleaner._diff(before, after)}
    if (cleaner.digest(payload) != value["source"]["sha256"] or cleaner.digest(derived) != value["cleaned_sha256"]
            or value.get("removed_count") != analysis["remaining_count"] or not analysis["remaining_count"]):
        raise ValueError("hygiene change does not reproduce its recorded transformation")
    outputs = value.get("outputs", [])
    if len(outputs) != len(expected) or len({row["path"] for row in outputs}) != len(expected):
        raise ValueError("hygiene change output inventory is incomplete")
    for row in outputs:
        target = path_in(project, row["path"])
        current = output_provenance.current_origin(project, target)
        if (target.parent != receipt.parent or target.name not in expected or target.read_bytes() != expected[target.name]
                or sha(target) != row["sha256"] or current.get("status") != "tracked"
                or current.get("provider") != PROVIDER or current.get("run_id") != identifier):
            raise ValueError("preserved hygiene original, candidate or diff was modified")


def refresh(project: Path, paper_id: str, *, apply: bool = False) -> dict:
    _cloud()
    project = project.resolve()
    implementation = _implementation()
    if apply:
        for path in inventory(project, paper_id):
            origin = output_provenance.current_origin(project, path)
            if not _can_apply(project, path, origin):
                continue
            payload = path.read_bytes()
            try:
                derived, analysis, before, after = _scan(payload, path.suffix.lower())
            except (ValueError, OSError, ImportError, RuntimeError, zipfile.BadZipFile):
                continue  # The complete audit records this blocker for remediation.
            if derived != payload:
                _apply(project, paper_id, path, payload, derived, analysis, before, after, implementation)
    value = audit(project, paper_id)
    value["changes"] = sorted(p.relative_to(project).as_posix() for p in
        (project / PREFIX / paper_id / "changes").glob("*/receipt.json"))
    if len(value["changes"]) > MAX_HISTORY:
        raise ValueError("hygiene history exceeds its bound; preserve and review before continuing")
    value["execution"] = {"mode": "cloud", "receipt_id": str(os.environ.get("GITHUB_RUN_ID") or
        os.environ.get("DR_OS_CLOUD_EXECUTION_RECEIPT_ID") or "authorized-cloud")}
    latest = path_in(project, f"{PREFIX}/{paper_id}/latest.json", exists=False)
    write(latest, value)
    _record(project, [latest], "scan-" + uuid.uuid4().hex)
    return value


def review_binding(project: Path, paper_id: str) -> dict:
    report = path_in(project, f"{PREFIX}/{paper_id}/latest.json", exists=False)
    return {"path": report.relative_to(project).as_posix(), "sha256": sha(report) if report.is_file() else None,
            "implementation": _implementation()}


def applied_cleanup(project: Path, paper_id: str, source: str, expected_sha256: str) -> str | None:
    """Resolve an older explicit request only against its exact auto-clean receipt."""
    target = cleaner._input(project, paper_id, source)
    origin = output_provenance.current_origin(project, target)
    if origin.get("status") != "tracked" or origin.get("provider") != PROVIDER:
        return None
    identifier = str(origin.get("run_id", ""))
    if not re.fullmatch(r"[0-9a-f]{32}", identifier):
        return None
    relative = f"{PREFIX}/{paper_id}/changes/{identifier}/receipt.json"
    receipt = path_in(project, relative)
    _validate_change(project, receipt, _implementation())
    value = read(receipt)
    if (value["source"]["path"] == source and value["source"]["sha256"] == expected_sha256
            and value["cleaned_sha256"] == sha(target) and value["source"]["origin"]["family"] == origin.get("family")):
        return relative
    return None


def validate_saved_report(project: Path, paper_id: str) -> list[str]:
    try:
        report = path_in(project, f"{PREFIX}/{paper_id}/latest.json")
        value = read(report)
        origin = output_provenance.current_origin(project, report)
        if origin.get("status") != "tracked" or origin.get("provider") != PROVIDER or origin.get("family") != "other":
            raise ValueError("hygiene audit lacks protected control-plane provenance")
        if value.get("execution", {}).get("mode") != "cloud" or not value["execution"].get("receipt_id"):
            raise ValueError("hygiene audit lacks cloud execution identity")
        actual = audit(project, paper_id)
        if any(value.get(key) != expected for key, expected in actual.items()):
            raise ValueError("hygiene audit is stale or differs from complete source recomputation")
        changes = sorted(p.relative_to(project).as_posix() for p in
            (project / PREFIX / paper_id / "changes").glob("*/receipt.json"))
        if len(changes) > MAX_HISTORY or value.get("changes") != changes:
            raise ValueError("hygiene change history is incomplete")
        for relative in changes:
            _validate_change(project, path_in(project, relative), actual["implementation"])
        for row in actual["files"]:
            current = row.get("origin", {})
            if current.get("provider") == PROVIDER:
                relative = f"{PREFIX}/{paper_id}/changes/{current.get('run_id')}/receipt.json"
                if relative not in changes:
                    raise ValueError("cleaned source lacks its preserved original and ancestry")
                change = read(path_in(project, relative))
                if (change["source"]["path"] != row["path"] or change["cleaned_sha256"] != row["sha256"]
                        or change["source"]["origin"]["family"] != current.get("family")):
                    raise ValueError("cleaned source ancestry or hash does not match its receipt")
        return actual["errors"]
    except (ValueError, OSError, KeyError, TypeError, AttributeError, RuntimeError, zipfile.BadZipFile) as exc:
        return [str(exc)]
