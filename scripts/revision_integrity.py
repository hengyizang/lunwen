#!/usr/bin/env python3
"""Detect unapproved numeric, citation and claim-strength drift between revisions."""

from __future__ import annotations

import json
import hashlib
import io
import re
import sys
import unicodedata
import zipfile
from collections import Counter
from functools import cached_property
from pathlib import Path
from typing import Any
from xml.etree.ElementTree import ParseError
from xml.etree import ElementTree as ET

try:
    from scripts.research_artifacts import write as atomic_json, paper_audit_cli, utc_now as now, sha as sha256_file, changed_fields
    from scripts.citation_audit import manuscript_digest, tex_source_paths
    from scripts.manuscript_language import extract_text
    from scripts.ref_verify_adapter import canonical_manuscript
except ImportError:  # Direct execution from scripts/.
    from research_artifacts import write as atomic_json, paper_audit_cli, utc_now as now, sha as sha256_file, changed_fields
    from citation_audit import manuscript_digest, tex_source_paths  # type: ignore
    from manuscript_language import extract_text  # type: ignore
    from ref_verify_adapter import canonical_manuscript  # type: ignore


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
PROJECTS_ROOT = ROOT / "projects"
NUMBER_RE = re.compile(r"(?<![A-Za-z0-9])[-+]?\d+(?:[.,]\d+)*(?:[eE][-+]?\d+)?%?")
SIGNAL_RE = re.compile(
    r"\b(?:may|might|could|suggests?|indicates?|associated|correlat(?:e|es|ed|ion)|"
    r"causes?|caused|drives?|demonstrates?|proves?|establishes?|confirms?)\b",
    re.I,
)

NUMBER = re.compile(r"(?<![A-Za-z])[-+]?\d+(?:[.,]\d+)*(?:[eE][-+]?\d+)?%?")
WORD = re.compile(r"[A-Za-z][A-Za-z0-9_-]*|[-+]?\d+(?:[.,]\d+)*(?:[eE][-+]?\d+)?%?")
PROTECTED = re.compile(
    r"\b(?:not|no|never|without|unless|only|except|excluding|excluded|"
    r"may|might|could|causal|causality|associated|correlation|significant|"
    r"nonsignificant|non-significant|independent|paired|unpaired|randomized|"
    r"observational|exploratory|confirmatory|negative|null|failed|failure|SD|SE|SEM|CI|"
    r"mm|cm|m|km|ms|s|mg|g|kg|ml|mL|mol|Hz|kHz|MPa|Pa)\b", re.I)
FILLER = {"the", "a", "an", "and", "or", "of", "in", "on", "to", "for", "by",
          "with", "was", "were", "is", "are", "has", "have", "it", "this", "that"}
SI_UNITS = {"mm", "cm", "m", "km", "ms", "s", "mg", "g", "kg", "ml", "mL", "mol", "Hz", "kHz", "MPa", "Pa", "M", "mM"}
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def word_package(path, *, members=None, _payload=None):
    with zipfile.ZipFile(path if _payload is None else io.BytesIO(_payload)) as archive:
        if len(archive.namelist()) != len(set(archive.namelist())) or sum(i.file_size for i in archive.infolist()) > 50_000_000:
            raise ValueError("duplicate or oversized OOXML package")
        return {name: archive.read(name) for name in archive.namelist() if members is None or name in members}


class WordSource:
    """One read-only Word source within a single inspection; never a global cache."""
    def __init__(self, path, *, complete=False):
        self.path = Path(path).resolve()
        with self.path.open("rb") as handle:
            payload = handle.read(64 * 1024 * 1024 + 1)
        if len(payload) > 64 * 1024 * 1024:
            raise ValueError("OOXML source exceeds the 64 MiB compressed-package limit")
        self.payload = payload
        self.sha256 = hashlib.sha256(payload).hexdigest()
        self.parts = word_package(path, members=None if complete else {"word/document.xml", "word/_rels/document.xml.rels"}, _payload=payload)
        self.root = ET.fromstring(self.parts["word/document.xml"])
        self.text = " ".join(node.text or "" for node in self.root.iter() if node.tag.endswith("}t"))

    @cached_property
    def citations(self):
        return _word_citations(self)


def word_source(path, documents=None, *, complete=False):
    """Reuse one complete package only within the caller's current operation."""
    if documents is None:
        return WordSource(path, complete=complete)
    key = path.resolve()
    if key not in documents:
        documents[key] = WordSource(path, complete=True)
    return documents[key]


def verify_word_sources(documents):
    """Reject mutation of an operation's sources before publishing its result."""
    for path, source in documents.items():
        if path.is_symlink() or path.resolve() != source.path or source.sha256 != sha256_file(path):
            raise ValueError("Word source changed during the current inspection")


def signatures(text: str) -> list[str]:
    """Bind protected tokens to clauses and local content, catching value swaps.

    Conservative false positives are reviewed, never auto-fixed. Formatting-only
    TeX commands and conjunctions are ignored; material qualifiers are retained.
    """
    text = re.sub(r"\\(?:cite|citep|citet|parencite|textcite|autocite)\*?(?:\[[^]]*\])*\{([^}]*)\}",
                  r" CITATION_\1 ", text)
    text = re.sub(r"\\mu\b|μ|µ", " MICRO ", text)
    text = re.sub(r"\\[A-Za-z]+", " ", text)
    result = []
    for clause in re.split(r"(?<!\d)[.!?;\n]+(?!\d)|\b(?:whereas|while|but)\b", text, flags=re.I):
        tokens = [t if t in SI_UNITS else t.casefold() for t in WORD.findall(clause) if t.casefold() not in FILLER]
        for i, token in enumerate(tokens):
            if NUMBER.fullmatch(token) or PROTECTED.fullmatch(token) or token.startswith("citation_"):
                context = tokens[max(0, i-3):i] + tokens[i+1:i+4]
                result.append(json.dumps([token, context], separators=(",", ":")))
    return result


def context_changes(before: str, after: str) -> dict[str, list[str]]:
    left, right = Counter(signatures(before)), Counter(signatures(after))
    return {"removed": sorted((left-right).elements()), "added": sorted((right-left).elements())}


def docx_citations(path: Path, *, document=None) -> list[str]:
    """Retain Word citation fields, citation hyperlinks and author/year anchors."""
    return (document or WordSource(path)).citations


def _word_citations(source):
    result = []
    document = source.root
    fields = []
    def capture(value):
        if re.search(r"CITATION|ZOTERO|CSL_CITATION|EN\.CITE", value, re.I):
            result.append(re.sub(r"\s+", " ", value).strip())
    for node in document.iter():
        if node.tag == W + "fldChar":
            kind = node.get(W + "fldCharType")
            if kind == "begin":
                fields.append([])
            elif kind == "end" and fields:
                capture("".join(fields.pop()))
        elif node.tag == W + "instrText":
            if fields:
                fields[-1].append(node.text or "")
            else:
                capture(node.text or "")
        elif node.tag == W + "fldSimple":
            capture(node.get(W + "instr", ""))
    if fields:
        raise ValueError("DOCX contains an unterminated citation field")
    for name, payload in source.parts.items():
        if name == "word/_rels/document.xml.rels":
            for node in ET.fromstring(payload):
                target = node.get("Target", "")
                if re.search(r"doi\.org/|pubmed\.ncbi\.nlm\.nih\.gov/", target, re.I):
                    result.append(target)
    text = " ".join(node.text or "" for node in document.iter(W+"t"))
    result.extend(re.findall(r"\([^()\n]*[A-Za-z][^()\n]*\b(?:19|20)\d{2}[a-z]?[^()\n]*\)", text))
    return result


def character_audit(text: str) -> list[dict]:
    """Report invisible/bidirectional controls; preserve originals and all codepoints."""
    return [{"offset": i, "codepoint": f"U+{ord(char):04X}",
             "name": unicodedata.name(char, "UNNAMED"), "action": "inspect_only"}
            for i, char in enumerate(text) if unicodedata.category(char) == "Cf"]


def scientific_text(path: Path, *, document=None) -> str:
    """Language cleanup must not erase equations from scientific drift checks."""
    if path.suffix.lower() == ".tex":
        return "\n".join(re.sub(r"(?m)(?<!\\)%.*$", "", p.read_text(encoding="utf-8"))
                         for p in sorted(tex_source_paths(path)))
    if path.suffix.lower() == ".docx" and document is not None:
        if len(document.parts["word/document.xml"]) > 10 * 1024 * 1024:
            raise ValueError("DOCX document XML exceeds the 10 MiB language-audit limit")
        return document.text
    return extract_text(path)


def formula_tokens(path: Path, *, document=None) -> list[str]:
    if path.suffix.lower() == ".tex":
        text = scientific_text(path)
        patterns = (r"(?<!\\)\$\$[\s\S]*?(?<!\\)\$\$", r"(?<![\\$])\$(?!\$)[\s\S]*?(?<![\\$])\$(?!\$)",
                    r"\\\[[\s\S]*?\\\]", r"\\\([\s\S]*?\\\)",
                    r"\\begin\{(equation\*?|align\*?|gather\*?|multline\*?|math|displaymath)\}[\s\S]*?\\end\{\1\}")
        values = []
        for pattern in patterns:
            matches = list(re.finditer(pattern, text))
            values.extend(re.sub(r"\s+", " ", m.group(0)).strip() for m in matches)
            text = re.sub(pattern, " ", text)
        return values
    if path.suffix.lower() == ".docx":
        root = (document or WordSource(path)).root
        math = "{http://schemas.openxmlformats.org/officeDocument/2006/math}oMath"
        return [ET.tostring(node, encoding="unicode") for node in root.iter(math)]
    return []


class RevisionIntegrityError(RuntimeError):
    pass


def multiset_delta(before: list[str], after: list[str]) -> dict[str, list[str]]:
    left, right = Counter(before), Counter(after)
    return {
        "removed": sorted((left - right).elements()),
        "added": sorted((right - left).elements()),
    }


def citation_tokens(path: Path, *, document=None) -> list[str]:
    if path.suffix.lower() == ".docx":
        return docx_citations(path, document=document)
    if path.suffix.lower() != ".tex":
        return []
    values: list[str] = []
    for source in sorted(tex_source_paths(path)):
        text = re.sub(r"(?m)(?<!\\)%.*$", "", source.read_text(encoding="utf-8"))
        for match in re.finditer(
            r"\\(?:cite|citep|citet|parencite|textcite|autocite)\*?(?:\[[^]]*\])*\{([^}]*)\}",
            text,
        ):
            values.extend(key.strip() for key in match.group(1).split(",") if key.strip())
    return values


def _facts(path: Path, *, documents=None):
    document = None
    if path.suffix.lower() == ".docx":
        try:
            document = word_source(path, documents)
        except (OSError, KeyError, zipfile.BadZipFile) as exc:
            raise ValueError(f"cannot read DOCX manuscript: {exc}") from exc
        except ParseError as exc:
            raise ValueError(f"invalid DOCX document XML: {exc}") from exc
    text = scientific_text(path, document=document)
    return {
        "numeric": NUMBER_RE.findall(text),
        "citation": citation_tokens(path, document=document),
        "claim_language": [match.group(0).casefold() for match in SIGNAL_RE.finditer(text)],
        "formula": formula_tokens(path, document=document),
    }, text


def tokens(path: Path) -> dict[str, list[str]]:
    return _facts(path)[0]


def load_authorization(path: Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RevisionIntegrityError(f"cannot read revision authorization: {exc}") from exc
    if not isinstance(value, dict) or value.get("schema_version") not in {"1.0", "1.1"}:
        raise RevisionIntegrityError("revision authorization must use schema_version 1.0")
    if value.get("schema_version") == "1.1":
        from scripts.output_provenance import current_origin
        project = path.parents[3]
        origin = current_origin(project, path)
        if (value.get("decision_kind") != "automated_change_record" or origin.get("status") != "tracked"
                or origin.get("provider") != "deterministic-control-plane" or origin.get("model") != "scripts/revision_integrity.py"):
            raise RevisionIntegrityError("automatic change record lacks controller provenance")
        return value
    if not str(value.get("approved_by", "")).strip() or not str(value.get("approved_at", "")).strip():
        raise RevisionIntegrityError("revision authorization needs approved_by and approved_at")
    return value


def revision_authorization(paper: Path):
    path = paper / "reviews/revision-authorizations.json"
    value = load_authorization(path if path.is_file() else None)
    binding = ({"path": path.relative_to(paper).as_posix(), "sha256": sha256_file(path),
                "approved_by": value.get("approved_by"), "approved_at": value.get("approved_at"),
                "decision_kind": value.get("decision_kind", "human")} if value is not None else None)
    return value, binding


def audit(paper: Path, *, include_ledger: bool = True, _documents=None) -> dict[str, Any]:
    current = canonical_manuscript(paper)
    preferred = paper / "reviews" / "revision-base" / current.name
    legacy = paper / "reviews" / f"revision-base{current.suffix.lower()}"
    base = preferred if preferred.is_file() else legacy
    if not base.is_file() or base.is_symlink():
        raise RevisionIntegrityError(f"reviews/revision-base/{current.name} is required")
    authorization, auth_binding = revision_authorization(paper)
    use_ledger = include_ledger and any((paper / "reviews" / name).exists() for name in ("revision-ledger.json", "revision-ledger-report.json"))
    documents = _documents if _documents is not None else ({} if use_ledger or current.suffix.lower() == ".docx" else None)
    (before, base_text), (after, current_text) = _facts(base, documents=documents), _facts(current, documents=documents)
    digests = {path: documents[path.resolve()].sha256 if documents is not None and path.suffix.lower() == ".docx"
               else manuscript_digest(path) for path in (base, current)}
    changes = {
        key + "_changes": multiset_delta(before[key], after[key])
        for key in ("numeric", "citation", "claim_language", "formula")
    }
    changes["scientific_context_changes"] = context_changes(base_text, current_text)
    has_changes = any(value[side] for value in changes.values() for side in ("removed", "added"))
    errors: list[str] = []
    if has_changes and authorization is None:
        errors.append("protected revision changes need a current source-bound change record and independent review")
    if authorization is not None:
        if authorization.get("schema_version") == "1.1" and (authorization.get("base_sha256") != digests[base]
                or authorization.get("current_sha256") != digests[current]):
            errors.append("automatic change record is stale")
        if authorization.get("schema_version") == "1.1" and authorization.get("revision_ledger_input_sha256") != sha256_file(paper / "reviews/revision-ledger.json"):
            errors.append("automatic change record is stale for the source-bound ledger")
        for key, actual in changes.items():
            expected = authorization.get(key, {"removed": [], "added": []})
            if not isinstance(expected, dict) or actual != {
                "removed": sorted(str(item) for item in expected.get("removed", [])),
                "added": sorted(str(item) for item in expected.get("added", [])),
            }:
                errors.append(f"{key} do not match the exact authorized multiset")
        if changes["claim_language_changes"] != {"removed": [], "added": []} and not str(
            authorization.get("claim_language_rationale", "")
        ).strip():
            errors.append("claim-language changes require an authorization rationale")
        if changes["scientific_context_changes"] != {"removed": [], "added": []} and not str(
            authorization.get("scientific_context_rationale") or authorization.get("claim_language_rationale") or ""
        ).strip():
            errors.append("scientific-context changes require an authorization rationale")
        if changes["formula_changes"] != {"removed": [], "added": []} and not str(
            authorization.get("formula_rationale") or authorization.get("scientific_context_rationale") or authorization.get("claim_language_rationale") or ""
        ).strip():
            errors.append("formula changes require an authorization rationale")
    ledger_binding = None
    if use_ledger:
        try:
            from scripts.revision_ledger import validate_saved_report as ledger_errors
            errors.extend("revision ledger: " + error for error in ledger_errors(paper.parent.parent, paper.name, _documents=documents))
            ledger_path = paper / "reviews/revision-ledger-report.json"
            ledger_binding = {"path": ledger_path.relative_to(paper).as_posix(), "sha256": sha256_file(ledger_path)} if ledger_path.is_file() else None
        except (OSError, ValueError, RuntimeError) as exc:
            errors.append(f"revision ledger: {exc}")
    if documents is not None and _documents is None:
        verify_word_sources(documents)
    return {
        "schema_version": "1.0",
        "created_at": now(),
        "status": "pass" if not errors else "fail",
        "base": {"path": base.relative_to(paper).as_posix(), "sha256": digests[base]},
        "current": {"path": current.relative_to(paper).as_posix(), "sha256": digests[current]},
        "authorization": auth_binding,
        "changes": changes,
        "errors": errors,
        "semantic_equivalence_proven": False,
        "human_scientific_review_required": False,
        "independent_scientific_review_required": True,
        "character_findings": character_audit(current_text if current.suffix.lower() == ".docx" else extract_text(current)),
        **({"revision_ledger": ledger_binding} if ledger_binding is not None else {}),
    }


def record_automated_changes(paper: Path) -> dict:
    """Record exact justified deltas; existing independent critics decide validity."""
    from scripts import revision_ledger
    from scripts.research_artifacts import record, verify_files
    project = paper.parent.parent
    current = canonical_manuscript(paper)
    base = paper / "reviews/revision-base" / current.name
    if not base.is_file():
        raise RevisionIntegrityError("canonical revision baseline is required")
    inputs = [{"path": path.relative_to(project).as_posix(), "sha256": sha256_file(path)}
              for path in (base, current, paper / "reviews/revision-ledger.json")]
    documents = {}
    ledger_errors = revision_ledger.validate_saved_report(project, paper.name, _documents=documents)
    if ledger_errors:
        raise RevisionIntegrityError("source-bound revision ledger required: " + "; ".join(ledger_errors))
    facts = audit(paper, include_ledger=False, _documents=documents)
    verify_files(project, inputs, changed_error="revision sources changed during change-record preparation")
    verify_word_sources(documents)
    reason = "Exact changes and source-bound author reasons are recorded in the current revision ledger; independent scientific audits remain required."
    value = {"schema_version": "1.1", "decision_kind": "automated_change_record", "recorded_at": now(),
             "base_sha256": facts["base"]["sha256"], "current_sha256": facts["current"]["sha256"],
             "revision_ledger_input_sha256": sha256_file(paper / "reviews/revision-ledger.json"),
             "claim_language_rationale": reason, "scientific_context_rationale": reason, "formula_rationale": reason,
             "human_review": False, "scientific_validity_verified": False, **facts["changes"]}
    destination = paper / "reviews/revision-authorizations.json"
    if destination.exists():
        old = load_authorization(destination)
        if old and old.get("decision_kind") != "automated_change_record":
            archive = project / "state/revision-control-history" / paper.name / (sha256_file(destination) + ".json")
            if not archive.exists():
                atomic_json(archive, old)
                record(project, [archive], "scripts/revision_integrity.py")
        if old and {k:v for k,v in old.items() if k!="recorded_at"} == {k:v for k,v in value.items() if k!="recorded_at"}:
            return old
    atomic_json(destination, value)
    record(project, [destination], "scripts/revision_integrity.py")
    revision_ledger.refresh(project, paper.name, _documents=documents)
    verify_files(project, inputs, changed_error="revision sources changed during change-record preparation")
    verify_word_sources(documents)
    return value


def validate_saved_report(paper: Path, *, include_ledger: bool = True, _documents=None) -> list[str]:
    path = paper / "reviews" / "revision-integrity.json"
    if not path.is_file():
        return ["reviews/revision-integrity.json is required"]
    try:
        saved = json.loads(path.read_text(encoding="utf-8"))
        current = audit(paper, include_ledger=include_ledger, _documents=_documents)
    except (OSError, json.JSONDecodeError, RevisionIntegrityError, ValueError) as exc:
        return [f"cannot validate revision integrity: {exc}"]
    errors: list[str] = []
    if saved.get("schema_version") != "1.0" or (include_ledger and saved.get("status") != "pass"):
        errors.append("revision integrity must be a passing schema_version 1.0 report")
    errors.extend(f"revision integrity is stale for {key}" for key in changed_fields(
        saved, current, ("base", "current", "authorization", *(("revision_ledger",) if include_ledger else ()))))
    if saved.get("changes") != current.get("changes"):
        errors.append("revision integrity changes differ from a clean rerun")
    errors.extend(current["errors"])
    return errors


def main() -> int:
    return paper_audit_cli(__doc__, PROJECTS_ROOT, audit, "revision-integrity.json", RevisionIntegrityError)


if __name__ == "__main__":
    raise SystemExit(main())
