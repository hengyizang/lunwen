"""Real OOXML insertions/deletions with verified accept/reject round trips.

Text edits retain unchanged fields, equations and images; unchanged fields and
equations may move. Body and table-cell additions/removals use paragraph marks.
Resources, styles, section boundaries and table topology cannot be revised by
this bounded workflow. Complex objects are never converted to plain text.
"""
from __future__ import annotations

import copy
import csv
import json
import shutil
import zipfile
from collections import Counter
from difflib import SequenceMatcher
from datetime import datetime, timezone
from pathlib import Path
from lxml import etree as ET

try:
    from scripts.research_artifacts import sha, read, write, record, path_in
except ImportError:
    from research_artifacts import sha, read, write, record, path_in  # type: ignore

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
M = "{http://schemas.openxmlformats.org/officeDocument/2006/math}"
DOCUMENT = "word/document.xml"


def package(path: Path) -> dict[str, bytes]:
    with zipfile.ZipFile(path) as archive:
        if len(archive.namelist()) != len(set(archive.namelist())) or sum(i.file_size for i in archive.infolist()) > 50_000_000:
            raise ValueError("duplicate or oversized OOXML package")
        return {name: archive.read(name) for name in archive.namelist()}


def canonical(element: ET.Element):
    # An empty pPr/rPr has no Word formatting effect. Paragraph-mark tracking
    # may create these neutral containers, which Word itself also preserves.
    return (element.tag, tuple(sorted(element.attrib.items())), element.text or "", element.tail or "",
            tuple(canonical(child) for child in element if not neutral_property(child)))


def neutral_property(element: ET.Element) -> bool:
    return (element.tag in {W + "pPr", W + "rPr"} and not element.attrib
            and not (element.text or "").strip() and all(neutral_property(child) for child in element))


def document_xml(payload: bytes) -> ET.Element:
    return ET.fromstring(payload, parser=ET.XMLParser(resolve_entities=False, no_network=True))


def resolve(root: ET.Element, accept: bool) -> ET.Element:
    result = copy.deepcopy(root)
    # Paragraph marks and inline content are distinct OOXML revisions. Removing
    # a fully inserted/deleted paragraph must also remove its paragraph mark.
    for paragraph in list(result.iter(W + "p")):
        properties = paragraph.find(W + "pPr")
        run_properties = properties.find(W + "rPr") if properties is not None else None
        if run_properties is None:
            continue
        markers = [item for item in run_properties if item.tag in {W + "ins", W + "del"}]
        if not markers:
            continue
        if len(markers) != 1:
            raise ValueError("ambiguous paragraph-mark revision")
        marker = markers[0]
        keep = (marker.tag == W + "ins") == accept
        if not keep:
            paragraph.getparent().remove(paragraph)
            continue
        run_properties.remove(marker)
        if not len(run_properties) and not run_properties.attrib:
            properties.remove(run_properties)
        if not len(properties) and not properties.attrib:
            paragraph.remove(properties)
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
                    for node in item.iter(W + "delInstrText"):
                        node.tag = W + "instrText"
                    parent.insert(position, item)
                    position += 1
    return result


def inline_units(paragraph: ET.Element) -> list[list[ET.Element]]:
    """Treat a multi-run complex field as one indivisible OOXML object."""
    units: list[list[ET.Element]] = []
    pending: list[ET.Element] = []
    depth = 0
    allowed = {W + "r", W + "hyperlink", W + "fldSimple", M + "oMath", M + "oMathPara"}
    for child in paragraph:
        if child.tag == W + "pPr":
            continue
        if child.tag not in allowed:
            # Range markers/content controls cannot safely be duplicated by a
            # deletion/insertion pair. An unchanged paragraph is copied intact.
            raise ValueError("changed paragraph contains unsupported range markers or content controls")
        begins = sum(node.get(W + "fldCharType") == "begin" for node in child.iter(W + "fldChar"))
        ends = sum(node.get(W + "fldCharType") == "end" for node in child.iter(W + "fldChar"))
        if depth or begins:
            pending.append(child)
            depth += begins - ends
            if depth < 0:
                raise ValueError("unbalanced complex Word field")
            if not depth:
                units.append(pending)
                pending = []
        elif ends or any(node.tag == W + "instrText" for node in child.iter()):
            raise ValueError("field instruction or end lacks its begin marker")
        else:
            units.append([child])
    if pending or depth:
        raise ValueError("field crosses paragraph boundaries or is unterminated")
    return units


def unit_key(unit: list[ET.Element]):
    return tuple(canonical(item) for item in unit)


def complex_unit(unit: list[ET.Element]) -> bool:
    simple = {W + "r", W + "rPr", W + "t", W + "tab", W + "br", W + "cr"}
    return any(node.tag not in simple and node.getparent().tag != W + "rPr"
               for item in unit for node in item.iter())


def complex_inventory(root: ET.Element) -> Counter:
    inventory: Counter = Counter()
    for paragraph in root.iter(W + "p"):
        try:
            units = inline_units(paragraph)
        except ValueError:
            # The tracking engine will refuse editing this paragraph. Preserve
            # its exact complex markup in the whole-document inventory.
            inventory[canonical(paragraph)] += 1
            continue
        inventory.update(unit_key(unit) for unit in units if complex_unit(unit))
    return inventory


class Tracker:
    def __init__(self, author: str, date: str):
        self.author, self.date, self.revision_id = author, date, 0

    def attributes(self) -> dict[str, str]:
        self.revision_id += 1
        return {W + "id": str(self.revision_id), W + "author": self.author, W + "date": self.date}

    def wrapper(self, tag: str, units: list[list[ET.Element]]) -> ET.Element:
        wrapper = ET.Element(W + tag, self.attributes())
        for unit in units:
            for item in unit:
                item = copy.deepcopy(item)
                if tag == "del":
                    for node in item.iter():
                        if node.tag == W + "t":
                            node.tag = W + "delText"
                        elif node.tag == W + "instrText":
                            node.tag = W + "delInstrText"
                wrapper.append(item)
        return wrapper

    def paragraph(self, before: ET.Element, after: ET.Element) -> ET.Element:
        if canonical(before) == canonical(after):
            return copy.deepcopy(after)
        if Counter(canonical(node) for node in before.iter(W + "drawing")) != Counter(canonical(node) for node in after.iter(W + "drawing")):
            raise ValueError("image moves duplicate drawing IDs in tracked copies; picture edits need an explicit structural Word workflow")
        if before.attrib != after.attrib:
            raise ValueError("paragraph attributes changed; explicit structural review required")
        bprop, aprop = before.find(W + "pPr"), after.find(W + "pPr")
        if (canonical(bprop) if bprop is not None else None) != (canonical(aprop) if aprop is not None else None):
            raise ValueError("paragraph formatting changes need explicit structural tracking")
        old, new = inline_units(before), inline_units(after)
        def formatting(units):
            profiles = []
            for unit in units:
                if complex_unit(unit):
                    continue
                for run in unit:
                    props = run.find(W + "rPr")
                    profile = canonical(props) if props is not None and not neutral_property(props) else None
                    if not profiles or profiles[-1] != profile:
                        profiles.append(profile)
            return profiles or [None]
        if old and new and formatting(old) != formatting(new):
            raise ValueError("run formatting changes need explicit rPrChange tracking")
        # A pure run-format change is not a text revision. The workflow does not
        # implement rPrChange, so it must fail rather than disguise it as prose.
        def text(units):
            return "".join(node.text or "" for unit in units for item in unit for node in item.iter(W + "t"))
        if text(old) == text(new) and Counter(unit_key(u) for u in old) != Counter(unit_key(u) for u in new):
            raise ValueError("run formatting/object changes require an explicit Word revision workflow")
        result = copy.deepcopy(after)
        for item in list(result):
            if item.tag != W + "pPr":
                result.remove(item)
        matcher = SequenceMatcher(None, [unit_key(u) for u in old], [unit_key(u) for u in new], autojunk=False)
        for operation, a, b, c, d in matcher.get_opcodes():
            if operation == "equal":
                for unit in new[c:d]:
                    result.extend(copy.deepcopy(item) for item in unit)
            else:
                if a < b:
                    result.append(self.wrapper("del", old[a:b]))
                if c < d:
                    result.append(self.wrapper("ins", new[c:d]))
        return result

    def added_or_removed(self, paragraph: ET.Element, tag: str) -> ET.Element:
        if paragraph.find(W + "pPr/" + W + "sectPr") is not None:
            raise ValueError("paragraph insertion/removal cannot change section boundaries")
        units = inline_units(paragraph)
        result = copy.deepcopy(paragraph)
        properties = result.find(W + "pPr")
        if properties is None:
            properties = ET.Element(W + "pPr")
            result.insert(0, properties)
        run_properties = properties.find(W + "rPr")
        if run_properties is None:
            run_properties = ET.SubElement(properties, W + "rPr")
        attrs = self.attributes()
        ET.SubElement(run_properties, W + tag, attrs)
        for item in list(result):
            if item.tag != W + "pPr":
                result.remove(item)
        if units:
            result.append(self.wrapper(tag, units))
        return result

    def blocks(self, before: ET.Element, after: ET.Element) -> ET.Element:
        """Only paragraphs may change length; tables retain rows/cells/grid."""
        if before.tag != after.tag or before.attrib != after.attrib:
            raise ValueError("table/container attributes or topology changed")
        left, right = list(before), list(after)
        result = copy.deepcopy(after)
        for item in list(result):
            result.remove(item)
        matcher = SequenceMatcher(None, [canonical(x) for x in left], [canonical(x) for x in right], autojunk=False)
        for operation, a, b, c, d in matcher.get_opcodes():
            if operation == "equal":
                result.extend(copy.deepcopy(x) for x in right[c:d])
                continue
            old, new = left[a:b], right[c:d]
            if len(old) == len(new):
                for previous, current in zip(old, new):
                    if previous.tag != current.tag:
                        raise ValueError("table topology/section boundaries changed")
                    if previous.tag == W + "p":
                        result.append(self.paragraph(previous, current))
                    elif previous.tag in {W + "tbl", W + "tr", W + "tc"}:
                        result.append(self.blocks(previous, current))
                    elif canonical(previous) == canonical(current):
                        result.append(copy.deepcopy(current))
                    else:
                        raise ValueError("table properties, grid, styles or section content changed")
            else:
                if any(x.tag != W + "p" for x in old + new):
                    # Preserve table/section anchors even when adjoining prose
                    # edits and paragraph additions are in one diff block.
                    old_fixed = [i for i, item in enumerate(old) if item.tag != W + "p"]
                    new_fixed = [i for i, item in enumerate(new) if item.tag != W + "p"]
                    if len(old_fixed) != len(new_fixed) or any(old[i].tag != new[j].tag for i, j in zip(old_fixed, new_fixed)):
                        raise ValueError("only paragraph insertion/removal is supported; table topology is frozen")
                    old_start = new_start = 0
                    for i, j in zip(old_fixed + [len(old)], new_fixed + [len(new)]):
                        # A temporary container lets the same bounded diff
                        # process paragraph-only portions without flattening.
                        old_part, new_part = ET.Element(W + "body"), ET.Element(W + "body")
                        old_part.extend(copy.deepcopy(x) for x in old[old_start:i])
                        new_part.extend(copy.deepcopy(x) for x in new[new_start:j])
                        result.extend(self.blocks(old_part, new_part))
                        if i < len(old):
                            previous, current = old[i], new[j]
                            if previous.tag in {W + "tbl", W + "tr", W + "tc"}:
                                result.append(self.blocks(previous, current))
                            elif canonical(previous) == canonical(current):
                                result.append(copy.deepcopy(current))
                            else:
                                raise ValueError("table properties, grid, styles or section content changed")
                        old_start, new_start = i + 1, j + 1
                    continue
                paired = min(len(old), len(new))
                for previous, current in zip(old[:paired], new[:paired]):
                    result.append(self.paragraph(previous, current))
                # Paragraph-mark deletion merges with the following paragraph
                # in Word. To remove an entire paragraph without inventing a
                # trailing blank paragraph there must be a following paragraph.
                if len(old) > paired and (b >= len(left) or left[b].tag != W + "p"):
                    raise ValueError("paragraph removal needs a following paragraph in the same container")
                result.extend(self.added_or_removed(x, "del") for x in old[paired:])
                result.extend(self.added_or_removed(x, "ins") for x in new[paired:])
        return result


def track(base: dict[str, bytes], clean: dict[str, bytes], author: str, date: str) -> bytes:
    if set(base) != set(clean) or any(base[k] != clean[k] for k in base if k != DOCUMENT):
        raise ValueError("resource/package changes require a structural Word revision workflow")
    old, new = document_xml(base[DOCUMENT]), document_xml(clean[DOCUMENT])
    if any(e.tag in {W + "ins", W + "del", W + "moveFrom", W + "moveTo"} for root in (old, new) for e in root.iter()):
        raise ValueError("resolve existing revisions explicitly before creating a new tracked version")
    left, right = old.find(W + "body"), new.find(W + "body")
    if left is None or right is None:
        raise ValueError("Word document body is missing")
    if old.attrib != new.attrib:
        raise ValueError("document attributes changed")
    if len(old) != len(new) or any(canonical(a) != canonical(b) for a, b in zip(old, new) if a.tag != W + "body"):
        raise ValueError("non-body document content changed")
    if complex_inventory(old) != complex_inventory(new):
        raise ValueError("changed fields, equations, images or range markers cannot be flattened; only unchanged objects may move")
    tracked_body = Tracker(author, date).blocks(left, right)
    new.replace(right, tracked_body)
    # Drawing non-visual IDs are document-unique. Duplicating an image in both
    # deletion and insertion can violate that contract even with equal media.
    drawing_ids = [item.get("id") for item in new.iter("{http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing}docPr")]
    if len(drawing_ids) != len(set(drawing_ids)):
        raise ValueError("image moves duplicate drawing identifiers; use an explicit Word move workflow")
    if canonical(resolve(new, True)) != canonical(document_xml(clean[DOCUMENT])):
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
              "scope": "paragraph/table-cell text, paragraph additions/removals; unchanged fields/math may move; image moves needing duplicate drawing IDs, resources/styles/section/table topology changes are refused"}
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
        root = document_xml(tracked[DOCUMENT])
        if canonical(resolve(root, True)) != canonical(document_xml(clean[DOCUMENT])) or canonical(resolve(root, False)) != canonical(document_xml(base[DOCUMENT])):
            raise ValueError("Word revision accept/reject round trip failed")
        return []
    except (OSError, ValueError, KeyError, TypeError, ET.XMLSyntaxError, zipfile.BadZipFile) as exc:
        return [str(exc)]
