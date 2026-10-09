"""Real OOXML insertions/deletions with verified accept/reject round trips.

Changed text paragraphs are supported. Structural, field, equation, image,
table and resource changes are refused rather than silently flattened.
"""
from __future__ import annotations

import copy
import csv
import json
import shutil
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from lxml import etree as ET

from scripts.research_artifacts import sha, read, write, record, path_in

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
DOCUMENT = "word/document.xml"


def package(path: Path) -> dict[str, bytes]:
    with zipfile.ZipFile(path) as archive:
        if len(archive.namelist()) != len(set(archive.namelist())) or sum(i.file_size for i in archive.infolist()) > 50_000_000:
            raise ValueError("duplicate or oversized OOXML package")
        return {name: archive.read(name) for name in archive.namelist()}


def canonical(element: ET.Element):
    return (element.tag, tuple(sorted(element.attrib.items())), element.text or "", element.tail or "",
            tuple(canonical(child) for child in element))


def resolve(root: ET.Element, accept: bool) -> ET.Element:
    result = copy.deepcopy(root)
    for parent in list(result.iter()):
        for child in list(parent):
            if child.tag not in {W + "ins", W + "del"}:
                continue
            position = list(parent).index(child)
            keep = (child.tag == W + "ins") == accept
            parent.remove(child)
            if keep:
                for item in list(child):
                    for node in item.iter(W + "delText"):
                        node.tag = W + "t"
                    parent.insert(position, item)
                    position += 1
    return result


def track(base: dict[str, bytes], clean: dict[str, bytes], author: str, date: str) -> bytes:
    if set(base) != set(clean) or any(base[k] != clean[k] for k in base if k != DOCUMENT):
        raise ValueError("resource/package changes require a structural Word revision workflow")
    old, new = ET.fromstring(base[DOCUMENT]), ET.fromstring(clean[DOCUMENT])
    if any(e.tag in {W + "ins", W + "del", W + "moveFrom", W + "moveTo"} for root in (old, new) for e in root.iter()):
        raise ValueError("resolve existing revisions explicitly before creating a new tracked version")
    left, right = old.find(W + "body"), new.find(W + "body")
    if left is None or right is None or len(left) != len(right):
        raise ValueError("paragraph insertion/removal requires a structural Word revision workflow")
    if old.attrib != new.attrib:
        raise ValueError("document attributes changed")
    revision_id = 0
    for before, after in zip(left, right):
        if canonical(before) == canonical(after):
            continue
        if before.tag != W + "p" or after.tag != W + "p" or before.attrib != after.attrib:
            raise ValueError("changed tables/sections/paragraph properties are unsupported")
        bprop, aprop = before.find(W + "pPr"), after.find(W + "pPr")
        if (canonical(bprop) if bprop is not None else None) != (canonical(aprop) if aprop is not None else None):
            raise ValueError("paragraph formatting changes need explicit structural tracking")
        for paragraph in (before, after):
            for run in paragraph:
                if run.tag == W + "pPr":
                    continue
                if run.tag != W + "r" or any(node.tag not in {W + "rPr", W + "t", W + "tab", W + "br", W + "cr"} for node in run):
                    raise ValueError("changed fields, hyperlinks, equations and images cannot be flattened")
        clean_runs = [copy.deepcopy(run) for run in after if run.tag != W + "pPr"]
        old_runs = [copy.deepcopy(run) for run in before if run.tag != W + "pPr"]
        for run in list(after):
            if run.tag != W + "pPr":
                after.remove(run)
        for tag, runs in (("del", old_runs), ("ins", clean_runs)):
            if not runs:
                continue
            revision_id += 1
            wrapper = ET.SubElement(after, W + tag, {W + "id": str(revision_id), W + "author": author, W + "date": date})
            for run in runs:
                if tag == "del":
                    for text in run.iter(W + "t"):
                        text.tag = W + "delText"
                wrapper.append(run)
    if canonical(resolve(new, True)) != canonical(ET.fromstring(clean[DOCUMENT])):
        raise ValueError("accepting revisions does not reproduce the clean document")
    if canonical(resolve(new, False)) != canonical(old):
        raise ValueError("rejecting revisions does not reproduce the baseline document")
    return ET.tostring(new, encoding="utf-8", xml_declaration=True)


def build(project: Path, paper_id: str) -> dict:
    from scripts.revision_integrity import audit as integrity_audit
    from scripts.revision_trace import validate_saved_report as trace_errors
    if not __import__("re").fullmatch(r"P[0-9]{2}", paper_id):
        raise ValueError("invalid paper ID")
    paper = project / "papers" / paper_id
    current = path_in(project, f"papers/{paper_id}/manuscript/main.docx")
    baseline = path_in(project, f"papers/{paper_id}/reviews/revision-base/main.docx")
    matrix = path_in(project, f"papers/{paper_id}/reviews/response-matrix.csv")
    errors = integrity_audit(paper)["errors"] + trace_errors(paper)
    if errors:
        raise ValueError("revision controls must pass before building the Word package: " + "; ".join(errors))
    date = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    baseline_parts, clean_parts = package(baseline), package(current)
    tracked_xml = track(baseline_parts, clean_parts, "Doctoral Research OS", date)
    output = paper / "submission-materials/revision"
    output.mkdir(parents=True, exist_ok=True)
    clean, tracked = output / "clean.docx", output / "tracked.docx"
    shutil.copyfile(current, clean)
    with zipfile.ZipFile(tracked, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, payload in sorted(clean_parts.items()):
            archive.writestr(name, tracked_xml if name == DOCUMENT else payload)
    response_copy = output / "response-matrix.csv"
    shutil.copyfile(matrix, response_copy)
    notes = output / "changes.md"
    with matrix.open(newline="", encoding="utf-8") as handle:
        responses = list(csv.DictReader(handle))
    notes.write_text("# Revision package\n\nReal OOXML insertions and deletions. Accept = clean; reject = baseline.\n"
                     "Visual inspection in Word remains required. Response dispositions are preserved below.\n\n"
                     + "\n".join("- " + json.dumps(row, ensure_ascii=False, sort_keys=True) for row in responses) + "\n", encoding="utf-8")
    inputs = [{"path": str(p.relative_to(project).as_posix()), "sha256": sha(p)} for p in (baseline, current, matrix)]
    outputs = [{"path": str(p.relative_to(project).as_posix()), "sha256": sha(p)} for p in (clean, tracked, response_copy, notes)]
    result = {"schema_version": "1.0", "status": "pass", "inputs": inputs, "outputs": outputs,
              "created_at": date, "revision_author": "Doctoral Research OS", "accept_equals_clean": True,
              "reject_equals_baseline": True, "visual_review_required": True,
              "scope": "text paragraphs; unchanged fields, equations, tables and images preserved"}
    report = paper / "reviews/docx-revision.json"
    write(report, result)
    record(project, [clean, tracked, response_copy, notes, report], "scripts/docx_revision.py")
    return result


def validate_saved_report(project: Path, paper_id: str) -> list[str]:
    paper = project / "papers" / paper_id
    report = paper / "reviews/docx-revision.json"
    if not report.is_file():
        return ["tracked revision package lacks a verified manifest"] if (paper / "submission-materials/revision").exists() else []
    try:
        saved = read(report)
        if saved.get("status") != "pass" or saved.get("schema_version") != "1.0":
            raise ValueError("Word revision manifest must pass")
        for item in saved["inputs"] + saved["outputs"]:
            if sha(path_in(project, item["path"])) != item["sha256"]:
                raise ValueError("Word revision, clean manuscript or response matrix changed after packaging")
        base, clean = (package(path_in(project, saved["inputs"][i]["path"])) for i in (0, 1))
        tracked = package(path_in(project, saved["outputs"][1]["path"]))
        if set(clean) != set(tracked) or any(clean[k] != tracked[k] for k in clean if k != DOCUMENT):
            raise ValueError("tracked Word resources differ from the clean manuscript")
        root = ET.fromstring(tracked[DOCUMENT])
        if canonical(resolve(root, True)) != canonical(ET.fromstring(clean[DOCUMENT])) or canonical(resolve(root, False)) != canonical(ET.fromstring(base[DOCUMENT])):
            raise ValueError("Word revision accept/reject round trip failed")
        return []
    except (OSError, ValueError, KeyError, TypeError, ET.XMLSyntaxError, zipfile.BadZipFile) as exc:
        return [str(exc)]
