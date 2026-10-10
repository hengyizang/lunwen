"""Hash-bound, complete scientific revision ledger; no semantic verdict or model calls.

TeX source sentences and Word paragraphs are mechanical source units, not a
linguistic assertion. The author supplies reasons, claim IDs and exact evidence
quotes. A passing ledger proves correspondence and coverage, never equivalence.
"""
from __future__ import annotations

import csv
import hashlib
import json
import re
import zipfile
from collections import Counter
from datetime import datetime, timezone
from difflib import SequenceMatcher
from itertools import zip_longest
from pathlib import Path
from xml.etree import ElementTree as ET

from scripts.citation_audit import manuscript_digest, tex_source_paths
from scripts.ref_verify_adapter import canonical_manuscript
from scripts.research_artifacts import path_in, read, record, sha, write
from scripts.scientific_editing import NUMBER, PROTECTED, SI_UNITS, signatures

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
M = "{http://schemas.openxmlformats.org/officeDocument/2006/math}"
R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
CITE = re.compile(r"\\(?:cite|citep|citet|parencite|textcite|autocite)\*?(?:\[[^]]*\])*\{([^}]*)\}")
FORMULA = re.compile(r"(?<!\\)\$\$[\s\S]*?(?<!\\)\$\$|(?<![\\$])\$(?!\$)[\s\S]*?(?<![\\$])\$(?!\$)|\\\[[\s\S]*?\\\]|\\\([\s\S]*?\\\)|\\begin\{(equation\*?|align\*?|gather\*?|multline\*?|math|displaymath)\}[\s\S]*?\\end\{\1\}")


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _json(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _xml(node) -> str:
    """Expanded namespace names avoid prefix-only differences and retain content."""
    return _json([node.tag, sorted(node.attrib.items()), node.text or "", node.tail or "",
                  [json.loads(_xml(child)) for child in node]])


def _paper(project: Path, paper_id: str) -> Path:
    if not re.fullmatch(r"P[0-9]{2}", paper_id):
        raise ValueError("invalid paper ID")
    paper = project / "papers" / paper_id
    if not paper.is_dir() or paper.is_symlink():
        raise ValueError("paper is absent or unsafe")
    return paper


def _baseline(paper: Path, current: Path) -> Path:
    preferred = paper / "reviews/revision-base" / current.name
    legacy = paper / "reviews" / ("revision-base" + current.suffix)
    base = preferred if preferred.is_file() else legacy
    if not base.is_file() or base.is_symlink():
        raise ValueError("canonical revision baseline is required")
    return base


def _sentences(text: str) -> list[tuple[int, int]]:
    """Conservative source spans; do not split decimals, braces or inline math.

    Blank paragraphs always delimit units. This intentionally keeps an ambiguous
    abbreviation or display environment together rather than inventing syntax.
    """
    spans, start, depth, math, index = [], 0, 0, None, 0
    while index < len(text):
        char = text[index]
        escaped = index > 0 and (len(text[:index]) - len(text[:index].rstrip("\\"))) % 2 == 1
        if char == "$" and not escaped:
            token = "$$" if text[index:index + 2] == "$$" else "$"
            if math is None:
                math = token
            elif math == token:
                math = None
            index += len(token)
            continue
        if not math and not escaped:
            if char == "{":
                depth += 1
            elif char == "}":
                depth = max(0, depth - 1)
        blank = char == "\n" and re.match(r"\n[ \t]*\n", text[index:])
        sentence = (char in ".!?" and not math and depth == 0
                    and index + 1 < len(text) and text[index + 1].isspace()
                    and not (char == "." and index and text[index - 1].isdigit())
                    and not (char == "." and re.search(r"\b(?:e\.g|i\.e|Dr|Fig|Eq|et al)$", text[start:index], re.I)))
        if blank or sentence:
            end = index + 1
            if text[start:end].strip():
                left = start + len(text[start:end]) - len(text[start:end].lstrip())
                right = end - len(text[start:end]) + len(text[start:end].rstrip())
                spans.append((left, right))
            start = end
        index += 1
    if text[start:].strip():
        spans.append((start + len(text[start:]) - len(text[start:].lstrip()), len(text.rstrip())))
    return spans


def _facts(text: str, *, formulas=None, citations=None) -> dict:
    clean = re.sub(r"(?m)(?<!\\)%.*$", "", text)
    values = {
        "numeric": NUMBER.findall(clean),
        "citation": citations if citations is not None else [key.strip() for match in CITE.finditer(clean)
                                                               for key in match.group(1).split(",") if key.strip()],
        "qualifier": [match.group(0).casefold() for match in PROTECTED.finditer(clean)
                      if match.group(0) not in SI_UNITS],
        "unit": re.findall(r"(?<!\w)(?:" + "|".join(sorted(map(re.escape, SI_UNITS), key=len, reverse=True)) + r")(?!\w)", clean)
                + re.findall(r"\\mu\b|μ|µ", clean),
        "formula": formulas if formulas is not None else [re.sub(r"\s+", " ", match.group(0)).strip() for match in FORMULA.finditer(clean)],
        "contextual": signatures(clean),
    }
    return {key: sorted(value) for key, value in values.items()}


def _unit(project: Path, source: Path, kind: str, location: str, text: str, identity: str,
          index: int, *, source_sha256: str, formulas=None, citations=None) -> dict:
    return {"path": source.relative_to(project).as_posix(), "source_sha256": source_sha256, "kind": kind,
            "location": location, "index": index, "sha256": _hash(identity), "text": text,
            "protected_facts": _facts(text, formulas=formulas, citations=citations)}


def source_snapshot(project: Path, canonical: Path) -> dict:
    """Read the complete canonical tree, including TeX includes and OOXML parts."""
    path_in(project, canonical.relative_to(project).as_posix())
    units, sources = [], []
    if canonical.suffix == ".tex":
        for source in sorted(tex_source_paths(canonical)):
            path_in(project, source.relative_to(project).as_posix())
            source_sha256 = sha(source)
            sources.append({"path": source.relative_to(project).as_posix(), "sha256": source_sha256})
            text = source.read_text(encoding="utf-8")
            for index, (start, end) in enumerate(_sentences(text), 1):
                span = text[start:end]
                units.append(_unit(project, source, "tex-source-sentence", f"characters:{start}:{end}", span, span, index,
                                   source_sha256=source_sha256))
    elif canonical.suffix == ".docx":
        source_sha256 = sha(canonical)
        sources.append({"path": canonical.relative_to(project).as_posix(), "sha256": source_sha256})
        with zipfile.ZipFile(canonical) as archive:
            names = archive.namelist()
            if len(names) != len(set(names)) or sum(info.file_size for info in archive.infolist()) > 50_000_000:
                raise ValueError("duplicate or oversized Word package")
            parts = {name: archive.read(name) for name in names}
        root = ET.fromstring(parts["word/document.xml"])
        if any(node.tag in {W + "ins", W + "del", W + "moveFrom", W + "moveTo"} for node in root.iter()):
            raise ValueError("resolve existing Word revisions before ledger comparison")
        relations = {}
        if "word/_rels/document.xml.rels" in parts:
            relations = {node.get("Id"): node.get("Target", "") for node in ET.fromstring(parts["word/_rels/document.xml.rels"])}
        paragraphs = list(root.iter(W + "p"))
        for index, paragraph in enumerate(paragraphs, 1):
            text = "".join(node.text or "" for node in paragraph.iter() if node.tag in {W + "t", M + "t"})
            instructions = "".join(node.text or "" for node in paragraph.iter(W + "instrText"))
            citations = ([re.sub(r"\s+", " ", instructions).strip()] if re.search(r"CITATION|ZOTERO|CSL_CITATION|EN\.CITE", instructions, re.I) else [])
            citations += [node.get(W + "instr", "") for node in paragraph.iter(W + "fldSimple")
                          if re.search(r"CITATION|ZOTERO|CSL_CITATION|EN\.CITE", node.get(W + "instr", ""), re.I)]
            citations += [relations.get(node.get(R + "id"), "") for node in paragraph.iter(W + "hyperlink")
                          if re.search(r"doi\.org/|pubmed\.ncbi\.nlm\.nih\.gov/", relations.get(node.get(R + "id"), ""), re.I)]
            citations += re.findall(r"\([^()\n]*[A-Za-z][^()\n]*\b(?:19|20)\d{2}[a-z]?[^()\n]*\)", text)
            formulas = [_xml(node) for node in paragraph.iter(M + "oMath")]
            units.append(_unit(project, canonical, "docx-paragraph", f"word/document.xml/paragraph:{index}", text,
                               _xml(paragraph), index, source_sha256=source_sha256, formulas=formulas, citations=citations))
        # The skeleton covers section/table/container properties outside paragraphs.
        for parent in root.iter():
            for child in list(parent):
                if child.tag == W + "p":
                    parent.remove(child)
        units.append(_unit(project, canonical, "docx-structure", "word/document.xml/non-paragraph-structure",
                           "OOXML document structure", _xml(root), len(units) + 1, source_sha256=source_sha256, formulas=[], citations=[]))
        for name, payload in sorted(parts.items()):
            if name == "word/document.xml":
                continue
            digest = hashlib.sha256(payload).hexdigest()
            unit = _unit(project, canonical, "docx-package-part", name, f"OOXML part {name}: sha256 {digest}",
                         digest, len(units) + 1, source_sha256=source_sha256, formulas=[], citations=[])
            unit["protected_facts"] = {key: [] for key in unit["protected_facts"]}
            units.append(unit)
    else:
        raise ValueError("canonical manuscript must be TeX or Word")
    return {"path": canonical.relative_to(project).as_posix(), "sha256": manuscript_digest(canonical),
            "sources": sources, "units": units}


def _delta(before: dict, after: dict) -> dict:
    return {key: {"removed": sorted((Counter(before[key]) - Counter(after[key])).elements()),
                  "added": sorted((Counter(after[key]) - Counter(before[key])).elements())} for key in before}


def _aggregate(units: list[dict]) -> dict:
    return {key: sorted(value for unit in units for value in unit["protected_facts"][key])
            for key in ("numeric", "citation", "qualifier", "unit", "formula", "contextual")}


def change_manifest(project: Path, paper_id: str) -> dict:
    """Draft author input with exact anchors; reasons/evidence are never fabricated."""
    paper = _paper(project, paper_id)
    current = canonical_manuscript(paper)
    old, new = source_snapshot(project, _baseline(paper, current)), source_snapshot(project, current)
    # Relative paths within each tree align includes while allowing distinct roots.
    def key(unit, snapshot):
        root = Path(snapshot["path"]).parent
        return (str(Path(unit["path"]).relative_to(root)), unit["kind"], unit["sha256"])
    changes = []
    matcher = SequenceMatcher(None, [key(unit, old) for unit in old["units"]], [key(unit, new) for unit in new["units"]], autojunk=False)
    for operation, left, end_left, right, end_right in matcher.get_opcodes():
        if operation == "equal":
            continue
        # Each changed source unit gets its own reason and evidence. Positional
        # pairing inside a replace hunk is mechanical, not semantic equivalence.
        for previous, revised in zip_longest(old["units"][left:end_left], new["units"][right:end_right]):
            before, after = ([previous] if previous else []), ([revised] if revised else [])
            unit_operation = "replace" if before and after else "delete" if before else "insert"
            protected = {"before": _aggregate(before), "after": _aggregate(after)}
            delta = _delta(protected["before"], protected["after"])
            changes.append({"change_id": _hash(_json([unit_operation, before, after])), "operation": unit_operation,
                            "before": before, "after": after, "protected_facts": protected, "protected_changes": delta,
                            "kind": "scientific" if any(item[side] for item in delta.values() for side in ("removed", "added")) else "editorial",
                            "claim_ids": [], "evidence": [], "reason": ""})
    return {"schema_version": "1.0", "base": {key: value for key, value in old.items() if key != "units"},
            "current": {key: value for key, value in new.items() if key != "units"}, "changes": changes}


def needs_ledger(project: Path, paper_id: str) -> bool:
    paper = _paper(project, paper_id)
    current = canonical_manuscript(paper)
    try:
        base = _baseline(paper, current)
    except ValueError:
        return False
    return manuscript_digest(base) != manuscript_digest(current)


def _claims(project: Path, paper_id: str) -> tuple[dict, dict]:
    path = path_in(project, "claims/claim-evidence.csv")
    claims = {}
    with path.open(encoding="utf-8", newline="") as handle:
        rows = csv.DictReader(handle)
        if not {"claim_id", "paper_id", "claim"}.issubset(rows.fieldnames or []):
            raise ValueError("claim evidence registry needs claim_id, paper_id and claim columns")
        for row in rows:
            identifier = (row.get("claim_id") or "").strip()
            if not identifier or identifier in claims:
                raise ValueError("claim registry contains empty or duplicate claim IDs")
            claims[identifier] = row
    return {identifier: row for identifier, row in claims.items() if row["paper_id"] == paper_id}, {"path": "claims/claim-evidence.csv", "sha256": sha(path)}


def _evidence(project: Path, anchor: dict, forbidden: set[str]) -> dict:
    if not isinstance(anchor, dict):
        raise ValueError("evidence anchor must be an object")
    source = path_in(project, anchor.get("path", ""))
    if anchor["path"] in forbidden:
        raise ValueError("evidence must be independent of the ledger and manuscript revisions")
    if source.suffix.lower() not in {".txt", ".md", ".csv", ".json", ".jsonl", ".tex", ".yaml", ".yml", ".log"}:
        raise ValueError("evidence needs an inspectable text source; preserve a source-bound extract for binary evidence")
    quote = anchor.get("quote")
    if not isinstance(quote, str) or not quote.strip() or not str(anchor.get("locator", "")).strip():
        raise ValueError("evidence needs an exact quote and source locator")
    content = source.read_text(encoding="utf-8")
    if anchor.get("sha256") != sha(source):
        raise ValueError("evidence source hash is stale")
    if content.count(quote) != 1:
        raise ValueError("evidence quote must occur exactly once in its actual source")
    start = content.index(quote)
    if "start" in anchor and anchor["start"] != start:
        raise ValueError("evidence character position does not match the exact quote")
    if "end" in anchor and anchor["end"] != start + len(quote):
        raise ValueError("evidence character end does not match the exact quote")
    return {"path": anchor["path"], "sha256": sha(source), "locator": anchor["locator"], "quote": quote,
            "start": start, "end": start + len(quote)}


def audit(project: Path, paper_id: str) -> dict:
    paper = _paper(project, paper_id)
    expected = change_manifest(project, paper_id)
    input_path = paper / "reviews/revision-ledger.json"
    errors, entries, source_bindings = [], [], {}
    claim_binding = None
    if not input_path.is_file():
        if expected["changes"]:
            errors.append("changed source units require an author revision ledger")
        value = {**expected, "changes": []}
    else:
        input_path = path_in(project, input_path.relative_to(project).as_posix())
        value = read(input_path)
    if value.get("schema_version") != "1.0":
        errors.append("revision ledger must use schema_version 1.0")
    for key in ("base", "current"):
        if value.get(key) != expected[key]:
            errors.append(f"revision ledger is stale or mismatched for {key}")
    supplied = value.get("changes")
    if not isinstance(supplied, list) or any(not isinstance(row, dict) for row in supplied):
        errors.append("revision ledger changes must be a list of objects")
        supplied = []
    identifiers = [row.get("change_id") for row in supplied]
    expected_ids = [row["change_id"] for row in expected["changes"]]
    if Counter(str(item) for item in identifiers) != Counter(expected_ids):
        errors.append("every deterministic change must be covered exactly once, with no extra or duplicate changes")
    canonical = {row["change_id"]: row for row in expected["changes"]}
    claims = {}
    if any(row.get("claim_ids") or row.get("kind") == "scientific" for row in supplied):
        try:
            claims, claim_binding = _claims(project, paper_id)
        except (OSError, ValueError) as exc:
            errors.append(str(exc))
    forbidden = {source["path"] for tree in (expected["base"], expected["current"]) for source in tree["sources"]}
    forbidden.update({input_path.relative_to(project).as_posix(), (paper / "reviews/revision-ledger-report.json").relative_to(project).as_posix()})
    for row in supplied:
        identifier = row.get("change_id")
        if not isinstance(identifier, str) or identifier not in canonical:
            continue
        actual = canonical[identifier]
        for key in ("operation", "before", "after", "protected_facts", "protected_changes"):
            if row.get(key) != actual[key]:
                errors.append(f"{identifier}: {key} does not match actual source units")
        if not isinstance(row.get("reason"), str) or not row["reason"].strip():
            errors.append(f"{identifier}: explicit revision reason is required")
        if row.get("kind") not in {"scientific", "editorial"}:
            errors.append(f"{identifier}: kind must be scientific or editorial")
        if row.get("kind") == "editorial" and actual["kind"] == "scientific":
            errors.append(f"{identifier}: editorial classification cannot override protected scientific changes")
        claim_ids = row.get("claim_ids")
        if not isinstance(claim_ids, list) or any(not isinstance(item, str) for item in claim_ids):
            errors.append(f"{identifier}: claim_ids must be a list of strings")
            claim_ids = []
        if len(set(claim_ids)) != len(claim_ids) or any(item not in claims for item in claim_ids):
            errors.append(f"{identifier}: claim IDs must be unique registered claims of this paper")
        anchors = row.get("evidence")
        if not isinstance(anchors, list):
            errors.append(f"{identifier}: evidence must be a list")
            anchors = []
        if row.get("kind") == "scientific" and (not claim_ids or not anchors):
            errors.append(f"{identifier}: scientific revisions need registered claim IDs and independent evidence anchors")
        bound = []
        for anchor in anchors:
            try:
                result = _evidence(project, anchor, forbidden)
                bound.append(result)
                source_bindings[result["path"]] = result["sha256"]
            except (OSError, UnicodeError, ValueError, TypeError, KeyError) as exc:
                errors.append(f"{identifier}: {exc}")
        entries.append({**actual, "reason": row.get("reason"), "kind": row.get("kind"),
                        "claim_ids": claim_ids, "evidence": bound,
                        "claim_records": [claims[item] for item in claim_ids if item in claims]})
    # The existing independent authorization check is never replaced by this ledger.
    from scripts.revision_integrity import audit as integrity_audit
    integrity = integrity_audit(paper, include_ledger=False)
    errors.extend("revision integrity: " + error for error in integrity["errors"])
    return {"schema_version": "1.0", "created_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
            "status": "pass" if not errors else "fail", "base": expected["base"], "current": expected["current"],
            "input": {"path": input_path.relative_to(project).as_posix(), "sha256": sha(input_path)} if input_path.is_file() else None,
            "claim_registry": claim_binding, "evidence_sources": [{"path": path, "sha256": digest} for path, digest in sorted(source_bindings.items())],
            "authorization": integrity["authorization"], "changes": entries, "change_count": len(expected["changes"]),
            "errors": errors, "coverage_complete": not any("covered exactly once" in error or "does not match actual source units" in error for error in errors),
            "semantic_equivalence_proven": False, "evidence_entailment_verified": False, "human_scientific_review_required": True,
            "scope": "TeX source sentences/includes; Word paragraphs, document structure and package parts",
            "alignment": "exact equal units; positional pairing of changed units; no semantic correspondence claim"}


def refresh(project: Path, paper_id: str) -> dict:
    result = audit(project, paper_id)
    output = _paper(project, paper_id) / "reviews/revision-ledger-report.json"
    write(output, result)
    record(project, [output], "scripts/revision_ledger.py")
    return result


def validate_saved_report(project: Path, paper_id: str, *, require_when_changed: bool = False) -> list[str]:
    paper = _paper(project, paper_id)
    input_path, output = paper / "reviews/revision-ledger.json", paper / "reviews/revision-ledger-report.json"
    if not input_path.exists() and not output.exists():
        try:
            return ["changed canonical manuscript requires reviews/revision-ledger.json and its protected report"] if require_when_changed and needs_ledger(project, paper_id) else []
        except (OSError, ValueError, RuntimeError) as exc:
            return [f"cannot check revision ledger requirement: {exc}"]
    try:
        saved = read(path_in(project, output.relative_to(project).as_posix()))
        current = audit(project, paper_id)
        errors = list(current["errors"])
        if saved.get("schema_version") != "1.0" or saved.get("status") != "pass":
            errors.append("revision ledger report must pass")
        if {key: value for key, value in saved.items() if key != "created_at"} != {key: value for key, value in current.items() if key != "created_at"}:
            errors.append("revision ledger report differs from a clean rerun")
        return errors
    except (OSError, ValueError, KeyError, TypeError, RuntimeError, zipfile.BadZipFile, ET.ParseError) as exc:
        return [f"cannot validate revision ledger: {exc}"]
