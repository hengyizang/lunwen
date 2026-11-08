#!/usr/bin/env python3
"""Audit reference identity using actual provider evidence or legacy human records."""

from __future__ import annotations

import argparse
from bisect import bisect_right
import hashlib
import json
import re
import sys
import urllib.parse
import zipfile
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Callable

try:
    from scripts.research_artifacts import sha as sha256_file, utc_now as now, path_in, read
except ImportError:  # Direct execution from scripts/.
    from research_artifacts import sha as sha256_file, utc_now as now, path_in, read

try:
    from scripts.network_safety import NetworkSafetyError, fetch_json, validate_https_url
except ModuleNotFoundError:  # Direct execution from scripts/.
    from network_safety import (  # type: ignore[no-redef]
        NetworkSafetyError,
        fetch_json,
        validate_https_url,
    )


ENTRY_RE = re.compile(r"@([A-Za-z]+)\s*\{\s*([^,\s]+)\s*,", re.MULTILINE)
FIELD_RE = re.compile(r"(?s)^\s*([A-Za-z][A-Za-z0-9_-]*)\s*=\s*(.*?)\s*$")
DOI_PREFIX_RE = re.compile(r"^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)", re.IGNORECASE)
CITE_RE = re.compile(r"\\(cite|citep|citet|parencite|textcite|autocite|citeauthor|citeyear|citeyearpar|footcite|footcitetext)\*?(?:\[[^]]*\])*\{([^}]*)\}")
MARKER_RE = re.compile(r"\[[^\]]*?@[^\]]+\]")
DOI_LINK_RE = re.compile(r"https?://(?:dx\.)?doi\.org/\S+", re.IGNORECASE)


class CitationAuditError(RuntimeError):
    pass


def normalize_doi(value: str) -> str:
    return DOI_PREFIX_RE.sub("", value.strip()).rstrip(".}").lower()


def normalize_title(value: str) -> str:
    value = re.sub(r"[{}\\]", "", value).lower()
    return " ".join(re.findall(r"[a-z0-9]+", value))


def title_similarity(left: str, right: str) -> float:
    return SequenceMatcher(None, normalize_title(left), normalize_title(right)).ratio()


def tex_source_paths(path: Path, root: Path | None=None, seen: set[Path] | None=None)->set[Path]:
    try:
        try:from scripts.tex_sources import expand
        except ModuleNotFoundError:from tex_sources import expand
        sources=set(expand(path,root=root).files)
        if seen is not None:seen.update(sources);return seen
        return sources
    except ValueError as exc:raise CitationAuditError(str(exc)) from exc


def manuscript_digest(path: Path) -> str:
    if path.suffix.lower()!=".tex":return sha256_file(path)
    digest=hashlib.sha256();root=path.parent.resolve()
    for source in sorted(tex_source_paths(path),key=lambda item:item.relative_to(root).as_posix()):
        digest.update(source.relative_to(root).as_posix().encode());digest.update(b"\0");digest.update(source.read_bytes());digest.update(b"\0")
    return digest.hexdigest()


def tex_citation_keys(path: Path) -> set[str]:
    return {row["citation_key"] for row in citation_usages(path)}


def citation_prose(value: str, *, tex=False) -> str:
    """Normalize literal citation scopes for matching, never scientific inference."""
    if tex:
        value = CITE_RE.sub("", value)
        # Only presentation wrappers may disappear. Unknown commands, math
        # operators, negation, units and grouping are part of the claim identity.
        formatting = re.compile(r"\\(?:emph|textbf|textit|textrm|textsf|texttt|textnormal|textup|textsl|textsc)\*?\s*\{")
        position = 0
        while match := formatting.search(value, position):
            end, depth = match.end(), 1
            while end < len(value) and depth:
                if value[end] == "\\":
                    end += 2
                    continue
                if value[end] == "{": depth += 1
                elif value[end] == "}": depth -= 1
                end += 1
            if depth:
                position = match.end()
            else:
                value = value[:match.start()] + value[match.end():end - 1] + value[end:]
                position = match.start()
    else:
        value = MARKER_RE.sub("", value)
    return " ".join(value.split()).strip().rstrip(".!?;").strip()


def _citation_scopes(text, matches, source, *, tex=False):
    """Each literal citation occurrence keeps its local prose and source position."""
    if len(matches) > 5000:
        raise CitationAuditError("citation inventory exceeds 5000 explicit occurrences")
    boundaries = [0]
    for boundary in re.finditer(r"\n[ \t]*\n|[.!?;][\"')\]]*\s+(?=[A-Z\\\[])", text):
        if not CITE_RE.match(text, boundary.end()) and not MARKER_RE.match(text, boundary.end()):
            boundaries.append(boundary.end())
    if tex:
        boundaries.extend(m.end() for m in re.finditer(r"\\(?:begin|end)\{[^}]+\}|\\(?:section|subsection|subsubsection|paragraph|title)\*?(?:\[[^]]*\])*\{[^{}]*\}", text))
    boundaries.sort()
    result, previous = [], None
    for ordinal, (start, end, keys, prefix) in enumerate(matches, 1):
        left = boundaries[bisect_right(boundaries, start) - 1]
        if previous and citation_prose(text[previous[1]:start], tex=tex).strip(",:()[]"):
            left = max(left, previous[1])
        right = end
        if prefix or not citation_prose(text[left:start], tex=tex):
            stop = re.search(r"[.!?;](?=\s|$)|\n[ \t]*\n", text[end:])
            right = end + stop.end() if stop else len(text)
        else:
            punctuation = re.match(r"[ \t]*[.!?;]", text[end:])
            if punctuation:
                right += punctuation.end()
        context = text[left:right].strip()
        location = {**source(start), "citation_ordinal": ordinal}
        for key in keys:
            binding = {"citation_key": key, "source": location, "context": context}
            result.append({"usage_id": hashlib.sha256(json.dumps(binding, sort_keys=True).encode()).hexdigest()[:24],
                **binding, "claim_text": citation_prose(context, tex=tex)})
        previous = (start, end)
    return result


def _docx_usage_inventory(path):
    try:
        with zipfile.ZipFile(path) as archive:
            members = [archive.getinfo(name) for name in ("word/document.xml", "word/footnotes.xml", "word/endnotes.xml",
                "word/_rels/document.xml.rels", "word/_rels/footnotes.xml.rels", "word/_rels/endnotes.xml.rels")
                if name in archive.namelist()]
            if not members or members[0].filename != "word/document.xml" or sum(item.file_size for item in members) > 10 * 1024 * 1024:
                raise CitationAuditError("DOCX citation XML exceeds 10 MiB")
            parts = {item.filename: ET.fromstring(archive.read(item)) for item in members}
    except (KeyError, zipfile.BadZipFile, ET.ParseError) as exc:
        raise CitationAuditError("DOCX citation source is not a readable document XML package") from exc
    w = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    math = "{http://schemas.openxmlformats.org/officeDocument/2006/math}"
    result, errors, visible, paragraphs = [], [], [], []
    digest = sha256_file(path)
    notes = {(kind, node.get(w + "id")): node for kind in ("footnote", "endnote")
        for node in parts.get("word/" + kind + "s.xml", ET.Element("empty")).iter(w + kind)}
    pending, seen = [("word/document.xml", None, parts["word/document.xml"])], set()
    def marker(instruction):
        if "CSL_CITATION" in instruction:
            errors.append("unsupported CSL citation keys require an explicit bibliography mapping")
        if re.search(r'\bHYPERLINK\s+"?https?://(?:dx\.)?doi\.org/', instruction, re.I):
            errors.append("DOI literature hyperlinks require an explicit citation-key marker or CITATION field")
        keys = re.findall(r"\bCITATION\s+([A-Za-z0-9_:.+/-]+)", instruction)
        if keys:
            keys.extend(re.findall(r"\\m\s+([A-Za-z0-9_:.+/-]+)", instruction))
        return "[" + "; ".join("@" + key for key in keys) + "]" if keys else ""
    for part, note_id, root in pending:
        stack = []
        relationships = parts.get("word/_rels/" + Path(part).name + ".rels", ET.Element("empty"))
        targets = {node.get("Id"): node.get("Target", "") for node in relationships}
        for index, paragraph in enumerate(root.iter(w + "p"), 1):
            pieces, math_children = [], set()
            location = {"path": path.name, "sha256": digest, "part": part, "paragraph": index,
                "coordinates": "word_paragraph_and_citation_order"}
            if note_id is not None: location["note_id"] = note_id
            paragraphs.append((location, pieces))
            simple_results = {id(node) for field in paragraph.iter(w + "fldSimple")
                if re.search(r"\bCITATION\s", field.get(w + "instr", "")) for node in field.iter(w + "t")}
            for node in paragraph.iter():
                if id(node) in math_children:
                    continue
                if node.tag in {math + "oMath", math + "oMathPara"}:
                    formula = ET.canonicalize(ET.tostring(node, encoding="unicode"), rewrite_prefixes=True)
                    pieces.append(" [OMML formula: " + formula + "] ")
                    math_children.update(id(child) for child in node.iter())
                elif node.tag in {w + "footnoteReference", w + "endnoteReference"}:
                    kind, identifier = node.tag.removeprefix(w).removesuffix("Reference"), node.get(w + "id")
                    key = kind, identifier
                    if key not in notes:
                        errors.append("DOCX references a missing " + kind + ": " + str(identifier))
                    elif key not in seen:
                        seen.add(key); pending.append(("word/" + kind + "s.xml", identifier, notes[key]))
                elif node.tag == w + "fldSimple":
                    pieces.append(marker(node.get(w + "instr", "")))
                elif node.tag == w + "hyperlink":
                    target = targets.get(node.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"), "")
                    label = "".join(child.text or "" for child in node.iter(w + "t"))
                    instructions = " ".join(child.text or "" for child in node.iter(w + "instrText"))
                    instructions += " " + " ".join(child.get(w + "instr", "") for child in node.iter(w + "fldSimple"))
                    if DOI_LINK_RE.match(target) and not MARKER_RE.search(label) and not re.search(r"\bCITATION\s", instructions):
                        errors.append("DOI literature hyperlinks require an explicit citation-key marker or CITATION field")
                elif node.tag == w + "fldChar":
                    kind = node.get(w + "fldCharType")
                    if kind == "begin":
                        stack.append([pieces, len(pieces), []]); pieces.append("")
                    elif kind == "end" and stack:
                        field_pieces, position, instruction = stack.pop()
                        field_pieces[position] = marker("".join(instruction))
                elif node.tag == w + "instrText":
                    if stack: stack[-1][2].append(node.text or "")
                    else: pieces.append(marker(node.text or ""))
                elif node.tag == w + "t":
                    field_result = id(node) in simple_results or any(re.search(r"\bCITATION\s", "".join(field[2])) for field in stack)
                    if not field_result:
                        pieces.append(node.text or "")
                        visible.append(node.text or "")
                elif node.tag in {w + "tab", w + "br", w + "cr"}:
                    pieces.append(" ")
        if stack:
            errors.append("DOCX contains an unterminated citation field in " + part)
    for location, pieces in paragraphs:
        text = "".join(pieces)
        matches = [(m.start(), m.end(), re.findall(r"@([A-Za-z0-9_:.+/-]+)", m.group()), False) for m in MARKER_RE.finditer(text)]
        result.extend(_citation_scopes(text, matches, lambda offset: location))
    if not result:
        errors.append("DOCX has no explicit citation-key mapping; retain [@key] markers or Word CITATION fields")
    if re.search(r"\[\d+(?:\s*[,–-]\s*\d+)*\]", " ".join(visible)):
        errors.append("numeric DOCX citations require an explicit bibliography-key mapping")
    return result, list(dict.fromkeys(errors))


def citation_usages(path: Path) -> list[dict]:
    """Located literal citation uses; the existing reviewer judges their meaning."""
    if path.suffix.lower() == ".docx":
        rows, errors = _docx_usage_inventory(path)
        if errors:
            raise CitationAuditError("; ".join(errors))
        return rows
    if path.suffix.lower() != ".tex":
        raise CitationAuditError("citation scopes require canonical TeX or DOCX")
    try:from scripts.tex_sources import expand
    except ModuleNotFoundError:from tex_sources import expand
    expanded = expand(path)
    digests = {p.relative_to(path.parent.resolve()).as_posix(): sha256_file(p) for p in expanded.files}
    def location(offset):
        value = expanded.locate(offset)
        return {**value, "sha256": digests[value["path"]], "coordinates": "source_line_and_citation_order"}
    begin = expanded.text.find(r"\begin{document}")
    start = begin + len(r"\begin{document}") if begin >= 0 else 0
    end = expanded.text.find(r"\end{document}", start)
    body = expanded.text[start:end if end >= 0 else len(expanded.text)]
    supported = {"cite", "citep", "citet", "parencite", "textcite", "autocite", "citeauthor", "citeyear",
        "citeyearpar", "footcite", "footcitetext", "nocite", "citestyle", "setcitestyle", "citereset"}
    if any(m[1] not in supported for m in re.finditer(r"\\([A-Za-z@]*cite[A-Za-z@]*)\b", body)):
        raise CitationAuditError("unsupported citation command needs an explicit literal citation-key source export")
    for link in re.finditer(r"\\(href|url)\s*\{\s*https?://(?:dx\.)?doi\.org/[^{}]+\}", body, re.I):
        # A key-bearing label is explicit; an author/year hyperlink alone can
        # otherwise disappear beside already mapped citations in the same file.
        label = re.match(r"\s*\{\s*(" + CITE_RE.pattern + r")\s*\}", body[link.end():]) if link[1].lower() == "href" else None
        if not label:
            raise CitationAuditError("DOI literature hyperlinks require an explicit citation-key command; replace the unkeyed link with \\cite{key}")
    matches = [(m.start(), m.end(), [key.strip() for key in m[2].split(",") if key.strip()],
        m[1] in {"citet", "textcite", "citeauthor"}) for m in CITE_RE.finditer(expanded.text, start, end if end >= 0 else len(expanded.text))]
    return _citation_scopes(expanded.text, matches, location, tex=True)


def docx_citation_keys(path: Path) -> tuple[set[str], list[str]]:
    """Map explicit bibliography keys; unsupported formatted citations fail closed."""
    rows, errors = _docx_usage_inventory(path)
    return {row["citation_key"] for row in rows}, errors


def parse_bibtex(text: str) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for match in ENTRY_RE.finditer(text):
        depth = 1
        index = match.end()
        while index < len(text) and depth:
            if text[index] == "{":
                depth += 1
            elif text[index] == "}":
                depth -= 1
            index += 1
        body = text[match.end() : index - 1] if depth == 0 else text[match.end() :]
        fields: dict[str, str] = {}
        # Commas inside braced or quoted values do not separate fields.
        segments: list[str] = []
        start = nested = 0
        quoted = escaped = False
        for pos, char in enumerate(body):
            if escaped:
                escaped = False
                continue
            if char == "\\":
                escaped = True
            elif char == '"' and nested == 0:
                quoted = not quoted
            elif not quoted and char == "{":
                nested += 1
            elif not quoted and char == "}":
                nested -= 1
            elif char == "," and nested == 0 and not quoted:
                segments.append(body[start:pos])
                start = pos + 1
        segments.append(body[start:])
        for segment in segments:
            if not segment.strip():
                continue
            field = FIELD_RE.fullmatch(segment)
            if not field:
                depth = 1
                continue
            value = field.group(2).strip()
            if len(value) >= 2 and ((value[0] == "{" and value[-1] == "}") or (value[0] == '"' and value[-1] == '"')):
                value = value[1:-1]
            elif not re.fullmatch(r"\d+", value):
                # Macro expansion and concatenation need a full BibTeX engine;
                # fail closed rather than treating them as literal metadata.
                depth = 1
            fields[field.group(1).lower()] = value.strip()
        if nested != 0 or quoted:
            depth = 1
        entries.append(
            {
                "type": match.group(1).lower(),
                "key": match.group(2),
                "fields": fields,
                "balanced": depth == 0,
            }
        )
    return entries


def crossref_record(doi: str, fetcher: Callable[..., Any]) -> dict[str, Any]:
    encoded = urllib.parse.quote(doi, safe="")
    payload = fetcher(f"https://api.crossref.org/works/{encoded}")
    if not isinstance(payload, dict) or not isinstance(payload.get("message"), dict):
        raise CitationAuditError("Crossref returned an unexpected response")
    return payload["message"]


def _metadata_cache_directory(bib_path: Path) -> Path | None:
    projects = (Path(__file__).resolve().parents[1] / "projects").resolve()
    resolved = bib_path.resolve()
    if resolved.is_relative_to(projects):
        parts = resolved.relative_to(projects).parts
        if len(parts) >= 2:
            return projects / parts[0] / "state/citation-metadata"
    return None


def cached_crossref_record(doi: str, fetcher: Callable[..., Any], cache_directory: Path | None,
                          *, refresh: bool = False) -> tuple[dict[str, Any], dict[str, Any]]:
    """Cache public metadata for 24h; never cache a bibliography PASS decision."""
    url = "https://api.crossref.org/works/" + urllib.parse.quote(doi, safe="")
    target = cache_directory / (hashlib.sha256(url.encode()).hexdigest() + ".json") if cache_directory else None
    if target is not None:
        if any(p.is_symlink() for p in (target, *target.parents)):
            raise CitationAuditError("citation metadata cache cannot use symlinks")
        if target.is_file() and not refresh:
            try:
                value = json.loads(target.read_text(encoding="utf-8"))
                age = datetime.now(timezone.utc) - datetime.fromisoformat(value["retrieved_at"])
                encoded = json.dumps(value["record"], sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
                if (value.get("schema_version") == "1.0" and value.get("url") == url
                        and value.get("doi") == doi and isinstance(value["record"], dict)
                        and timedelta(0) <= age < timedelta(hours=24)
                        and hashlib.sha256(encoded).hexdigest() == value["record_sha256"]):
                    return value["record"], {"source_url": url, "retrieved_at": value["retrieved_at"],
                                              "record_sha256": value["record_sha256"], "cache_hit": True}
            except (OSError, ValueError, TypeError, KeyError):
                pass
    record = crossref_record(doi, fetcher)
    digest = hashlib.sha256(json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()
    receipt = {"schema_version": "1.0", "doi": doi, "url": url, "retrieved_at": now(),
               "record_sha256": digest, "record": record}
    if target is not None:
        try:
            from scripts.research_artifacts import write
        except ModuleNotFoundError:
            from research_artifacts import write  # type: ignore
        write(target, receipt)
    return record, {"source_url": url, "retrieved_at": receipt["retrieved_at"],
                    "record_sha256": digest, "cache_hit": False}


def record_year(record: dict[str, Any]) -> int | None:
    for key in ("published-print", "published-online", "published", "issued"):
        parts = record.get(key, {}).get("date-parts", []) if isinstance(record.get(key), dict) else []
        if parts and isinstance(parts[0], list) and parts[0] and isinstance(parts[0][0], int):
            return parts[0][0]
    return None


def load_manual(path: Path | None) -> dict[str, dict[str, Any]]:
    if path is None:
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CitationAuditError(f"Cannot read manual verifications: {exc}") from exc
    if not isinstance(value, dict):
        raise CitationAuditError("Manual verifications must be an object keyed by citation key")
    records: dict[str, dict[str, Any]] = {}
    for key, record in value.items():
        if not isinstance(record, dict):
            raise CitationAuditError(f"Manual verification {key} must be an object")
        required = ("verified_by", "verified_at", "source_url", "title")
        if any(not isinstance(record.get(field), str) or not record[field].strip() for field in required):
            raise CitationAuditError(f"Manual verification {key} is missing required fields")
        try:
            validate_https_url(record["source_url"], f"manual verification {key} source_url")
        except NetworkSafetyError as exc:
            raise CitationAuditError(str(exc)) from exc
        try:
            datetime.fromisoformat(record["verified_at"].replace("Z", "+00:00"))
        except ValueError as exc:
            raise CitationAuditError(
                f"Manual verification {key} verified_at must be ISO 8601"
            ) from exc
        records[str(key)] = record
    return records


def _identity_text(value: str) -> str:
    """Conservative Unicode tokens; identity matching is never fuzzy."""
    return " ".join(re.findall(r"[^\W_]+", re.sub(r"[{}\\]", "", value).casefold(), re.UNICODE))


def _bib_authors(value: str) -> list[str]:
    names = []
    for author in re.split(r"\s+and\s+", value.strip(), flags=re.IGNORECASE):
        parts = [part.strip() for part in author.split(",")]
        if not author.strip() or len(parts) > 2 or _identity_text(author) == "others":
            return []
        names.append(_identity_text(" ".join(reversed(parts))))
    return names if all(names) else []


def _bibliography_project(bib_path: Path) -> Path | None:
    path = bib_path.absolute()
    if (path.parent.name == "manuscript" and re.fullmatch(r"P[0-9]{2}", path.parent.parent.name)
            and path.parent.parent.parent.name == "papers"):
        return path.parent.parent.parent.parent
    return None


def _field_text(value: str) -> str:
    import unicodedata
    value = re.sub(r"\\[\'\"`^~=.uvHckbdtr]\s*\{?([A-Za-z])\}?", r"\1", value)
    value = "".join(char for char in unicodedata.normalize("NFKD", value) if not unicodedata.combining(char))
    return _identity_text(value.replace("&", " and "))


def _crossref_authors(value: str, authors) -> bool | None:
    """Match source family names and ordered given names/explicit initials only."""
    if not isinstance(authors, list) or not authors or any(not isinstance(row, dict) for row in authors):
        return None
    names, start, depth = [], 0, 0
    for match in re.finditer(r"[{}]|\s+and\s+", value, re.I):
        if match[0] == "{": depth += 1
        elif match[0] == "}": depth -= 1
        elif depth == 0:
            names.append(value[start:match.start()].strip()); start = match.end()
    names.append(value[start:].strip())
    if len(names) != len(authors):
        return False
    for name, author in zip(names, authors):
        family = _field_text(str(author.get("family") or "")).split()
        if not family:
            literal = author.get("name")
            if not isinstance(literal, str) or not literal.strip(): return None
            if _field_text(name) != _field_text(literal): return False
            continue
        parts = name.split(",")
        if len(parts) == 2:
            last, given = _field_text(parts[0]).split(), parts[1]
        elif len(parts) == 1:
            tokens = _field_text(name).split()
            last, given = tokens[-len(family):], " ".join(tokens[:-len(family)])
        else:
            return None  # Suffix/ambiguous forms need original-source review, not guessed names.
        if last != family: return False
        ours, theirs = _field_text(given).split(), _field_text(str(author.get("given") or "")).split()
        if not ours or not theirs: return None
        if len(ours) > len(theirs): return None
        def compatible(tokens):
            return all(a == b or len(a) == 1 and b.startswith(a) or len(b) == 1 and a.startswith(b)
                       for a, b in zip(tokens, theirs))
        if (not compatible(ours) and len(ours) == 1 and len(ours[0]) == len(theirs) > 1
                and (given.strip().isupper() or re.match(r"\s*" + re.escape(ours[0].upper()) + r"\s", name))):
            ours = list(ours[0])
        if not compatible(ours):
            return False
    return True


def _page_text(value) -> str:
    value = re.sub(r"\s+", "", str(value).replace("{", "").replace("}", "")).casefold()
    value = re.sub(r"[-‐‑‒–—−]+", "-", value)
    match = re.fullmatch(r"(\d+)-(\d+)", value)
    if match and len(match[2]) < len(match[1]):
        start, end = int(match[1]), int(match[1][:-len(match[2])] + match[2])
        if end < start: end += 10 ** len(match[2])
        return f"{start}-{end}"
    return str(int(value)) if value.isdigit() else value


def _crossref_fields(fields: dict, record: dict) -> tuple[dict, list[str]]:
    """Verify asserted fields; absent source metadata stays explicitly unknown."""
    aliases = {"journal": ("container-title", "short-container-title"), "journaltitle": ("container-title", "short-container-title"),
        "booktitle": ("container-title", "short-container-title"), "volume": ("volume",), "number": ("issue",),
        "pages": ("page", "article-number"), "page": ("page", "article-number"),
        **{name: ("article-number",) for name in ("eid", "article-number", "articleno", "article_number")}}
    checks, errors = {}, []
    for field in ("author", *aliases):
        if not fields.get(field): continue
        candidates = record.get("author") if field == "author" else []
        if field == "author":
            matched = _crossref_authors(fields[field], candidates)
        else:
            for key in aliases[field]:
                value = record.get(key)
                candidates.extend(value if isinstance(value, list) else [value] if value is not None else [])
            types = (str,) if field in {"journal", "journaltitle", "booktitle"} else (str, int)
            candidates = [value for value in candidates if type(value) in types and str(value).strip()]
            normalize = _page_text if field not in {"journal", "journaltitle", "booktitle"} else _field_text
            matched = any(normalize(fields[field]) == normalize(value) for value in candidates) if candidates else None
        status = "unknown" if matched is None else "matches" if matched else "mismatch"
        checks[field] = {"status": status, "declared": fields[field], "source": candidates}
        if status != "matches":
            errors.append(f"{field} mismatch with Crossref" if status == "mismatch" else f"Crossref {field} field accuracy is unknown")
    return checks, errors


def provider_identity(bib_path: Path, fields: dict[str, str], *, selection: dict | None = None) -> dict:
    """Recheck a no-DOI identity against executed official metadata, offline.

    The receipt proves bibliographic identity only. It is not a licence,
    scientific claim-support finding, or substitute for original-source reading.
    """
    try:
        try:
            from scripts import literature_evidence as evidence, output_provenance
            from scripts.research_artifacts import path_in, read
        except ImportError:
            import literature_evidence as evidence
            import output_provenance
            from research_artifacts import path_in, read
        project = _bibliography_project(bib_path)
        if project is None:
            raise ValueError("provider identity needs a canonical papers/Pxx/manuscript bibliography")
        path_in(project, bib_path.absolute().relative_to(project).as_posix())
        title, year, authors = _identity_text(fields.get("title", "")), fields.get("year", ""), _bib_authors(fields.get("author", ""))
        if not title or not re.fullmatch(r"[0-9]{4}", year) or not authors:
            raise ValueError("no-DOI identity needs an exact title, four-digit year and complete ordered authors")
        arxiv = fields.get("eprint", "").removeprefix("arXiv:").strip()
        if arxiv and not evidence.ARXIV_IDENTIFIER_RE.fullmatch(arxiv):
            raise ValueError("unsupported arXiv identifier")
        url = fields.get("url", "").strip()
        if url:
            validate_https_url(url, "bibliographic source URL")
        if not url and not arxiv:
            raise ValueError("no-DOI identity needs an exact source URL or arXiv identifier")
        receipt_id, work_id = fields.get("evidence_receipt_id"), fields.get("evidence_work_id")
        if selection is not None:
            if receipt_id and (receipt_id, work_id) != (selection.get("receipt_id"), selection.get("work_id")):
                raise ValueError("saved bibliographic receipt differs from the explicit bibliography selection")
            receipt_id, work_id = selection.get("receipt_id"), selection.get("work_id")
        if bool(receipt_id) != bool(work_id):
            raise ValueError("evidence_receipt_id and evidence_work_id must be supplied together")
        if receipt_id and not evidence.SAFE_RECEIPT_RE.fullmatch(receipt_id):
            raise ValueError("invalid bibliographic receipt identifier")
        ledger = path_in(project, "evidence/literature-api-ledger.jsonl")

        def owned(path):
            if path.stat().st_size > evidence.MAX_RESPONSE_BYTES:
                raise ValueError("bibliographic source exceeds its bounded evidence size")
            origin = output_provenance.current_origin(project, path)
            if (origin.get("status") != "tracked" or origin.get("family") != "other"
                    or origin.get("provider") != "deterministic-control-plane"
                    or origin.get("model") != "scripts/literature_evidence.py"):
                raise ValueError("bibliographic evidence lacks current acquisition-controller provenance")

        owned(ledger)
        receipts = evidence.read_jsonl(ledger)
        ids = [row.get("receipt_id") for row in receipts]
        if len(ids) != len(set(ids)):
            raise ValueError("bibliographic receipt identifiers are ambiguous")
        if receipt_id:
            receipts = [row for row in receipts if row.get("receipt_id") == receipt_id]
            if len(receipts) != 1:
                raise ValueError("selected bibliographic receipt is missing or ambiguous")
        candidates, blockers = {}, []
        for receipt in receipts:
            provider = receipt.get("provider")
            if receipt.get("status") != "success" or receipt.get("mode") != "live_search" or provider not in evidence.DEFAULT_SEARCH_PROVIDERS:
                continue
            try:
                expected_url = evidence.build_search_url(provider, receipt["query"], 1,
                    date_range=receipt["declared_date_range"], filters=receipt["declared_filters"])
                expected = urllib.parse.urlsplit(expected_url)
                for source_url in (receipt["request_url"], receipt["final_url"]):
                    validate_https_url(source_url, "executed provider URL")
                    parsed = urllib.parse.urlsplit(source_url)
                    if (parsed.scheme, parsed.hostname, parsed.port, parsed.path) != (expected.scheme, expected.hostname, expected.port, expected.path):
                        raise ValueError("bibliographic receipt does not identify its official metadata endpoint")
                if receipt.get("http_status") != 200:
                    raise ValueError("bibliographic receipt lacks a successful HTTP response")
                raw_relative, normalized_relative = receipt["raw_response_path"], receipt["normalized_results_path"]
                if not raw_relative.startswith("evidence/literature/raw/") or not normalized_relative.startswith("evidence/literature/normalized/"):
                    raise ValueError("bibliographic evidence is outside protected acquisition paths")
                raw, normalized = path_in(project, raw_relative), path_in(project, normalized_relative)
                for path, expected_hash in ((raw, receipt["response_sha256"]), (normalized, receipt["normalized_results_sha256"])):
                    owned(path)
                    if sha256_file(path) != expected_hash:
                        raise ValueError("bibliographic provider evidence changed")
                works = read(normalized).get("works")
                replayed, _ = evidence.filter_results(provider, evidence.normalize_search(provider, raw.read_bytes()),
                    evidence.parse_conditions(receipt["declared_date_range"], receipt["declared_filters"]))
                if not isinstance(works, list) or works != replayed or len(works) != receipt.get("result_count"):
                    raise ValueError("normalized bibliographic metadata does not replay from the original response")
                for work in works:
                    if work_id and work.get("id") != work_id:
                        continue
                    work_authors = work.get("authors", [])
                    source_matches = bool(url and work.get("primary_source_url") == url)
                    if arxiv:
                        parsed_url = urllib.parse.urlsplit(url)
                        source_matches = work.get("arxiv_id") == arxiv and (not url or (
                            parsed_url.hostname == "arxiv.org" and parsed_url.path in {
                                "/abs/" + arxiv, "/pdf/" + arxiv, "/pdf/" + arxiv + ".pdf"}))
                    if (work.get("doi") or not source_matches or _identity_text(work.get("title", "")) != title
                            or work.get("publication_year") != int(year) or not isinstance(work_authors, list)
                            or any(not isinstance(name, str) for name in work_authors)
                            or [_identity_text(name) for name in work_authors] != authors):
                        continue
                    identity = {"kind": "automated_bibliographic_identity", "receipt_id": receipt["receipt_id"],
                        "receipt_sha256": hashlib.sha256(evidence.canonical_json_bytes(receipt)).hexdigest(),
                        "work_id": work["id"], "provider": provider, "ledger_path": "evidence/literature-api-ledger.jsonl",
                        "raw": {"path": raw_relative, "sha256": receipt["response_sha256"]},
                        "normalized": {"path": normalized_relative, "sha256": receipt["normalized_results_sha256"]},
                        "title": work["title"], "year": work["publication_year"], "authors": work_authors,
                        "source_url": work.get("primary_source_url"), "arxiv_id": work.get("arxiv_id"),
                        "human_verification": False, "claim_support_verified": False, "rights_verified": False}
                    candidates.setdefault(work["id"], identity)
            except (OSError, ValueError, KeyError, TypeError, evidence.LiteratureEvidenceError) as exc:
                blockers.append(str(exc))
        if len(candidates) != 1:
            detail = "; ".join(sorted(set(blockers))[:3])
            raise ValueError("no unique matching executed bibliographic identity" + (": " + detail if detail else ""))
        return next(iter(candidates.values()))
    except (OSError, ValueError, KeyError, TypeError, RuntimeError) as exc:
        raise CitationAuditError("source-bound bibliographic identity: " + str(exc)) from exc


def validate_provider_identities(bib_path: Path, report: dict) -> list[str]:
    """Invalidate saved automatic identity results when their sources change."""
    errors = []
    try:
        entries = {entry["key"]: entry for entry in parse_bibtex(bib_path.read_text(encoding="utf-8"))}
        for finding in report.get("findings", []):
            if not isinstance(finding, dict):
                raise CitationAuditError("citation findings must be records")
            if finding.get("status") == "verified_crossref":
                entry = entries.get(finding.get("citation_key"))
                project = _bibliography_project(bib_path)
                if entry is None or project is None:
                    raise CitationAuditError("Crossref field verification needs its canonical bibliography")
                doi = normalize_doi(entry["fields"].get("doi", ""))
                url = "https://api.crossref.org/works/" + urllib.parse.quote(doi, safe="")
                source = read(path_in(project, "state/citation-metadata/" + hashlib.sha256(url.encode()).hexdigest() + ".json"))
                digest = hashlib.sha256(json.dumps(source["record"], sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()
                metadata = finding.get("metadata_receipt", {})
                if (source.get("doi") != doi or source.get("url") != url or source.get("record_sha256") != digest
                        or metadata.get("source_url") != url or metadata.get("record_sha256") != digest
                        or metadata.get("retrieved_at") != source.get("retrieved_at")):
                    raise CitationAuditError("saved Crossref metadata source changed")
                checks, issues = _crossref_fields(entry["fields"], source["record"])
                if issues or finding.get("crossref", {}).get("field_verification") != checks:
                    raise CitationAuditError("saved Crossref field verification is missing, stale or unresolved; refresh citation audit")
                continue
            if finding.get("status") != "verified_provider_identity":
                continue
            stored = finding.get("provider_identity")
            if not isinstance(stored, dict):
                raise CitationAuditError("automatic citation identity receipt is missing")
            entry = entries.get(finding.get("citation_key"))
            if entry is None or provider_identity(bib_path, entry["fields"], selection=stored) != stored:
                raise CitationAuditError("saved automatic bibliographic identity is stale")
    except (OSError, ValueError, KeyError, TypeError, CitationAuditError) as exc:
        errors.append(str(exc))
    return errors


def audit(
    bib_path: Path,
    *,
    manual_path: Path | None = None,
    offline: bool = False,
    docx_verified_by: str | None = None,
    fetcher: Callable[..., Any] = fetch_json,
    cache_directory: Path | None = None,
    refresh_metadata: bool = False,
) -> dict[str, Any]:
    try:
        text = bib_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise CitationAuditError(f"Cannot read bibliography: {exc}") from exc
    entries = parse_bibtex(text)
    manual = load_manual(manual_path)
    findings: list[dict[str, Any]] = []
    seen_dois: dict[str, str] = {}
    for entry in entries:
        fields = entry["fields"]
        key = entry["key"]
        title = fields.get("title", "")
        result: dict[str, Any] = {
            "citation_key": key,
            "entry_type": entry["type"],
            "title": title or None,
            "doi": None,
            "status": "unverified",
            "issues": [],
        }
        if not entry["balanced"]:
            result["issues"].append("unbalanced BibTeX entry")
        if not title:
            result["issues"].append("missing title")
        doi_value = fields.get("doi")
        if doi_value:
            doi = normalize_doi(doi_value)
            result["doi"] = doi
            if not doi.startswith("10.") or "/" not in doi:
                result["issues"].append("malformed DOI")
            if doi in seen_dois:
                result["issues"].append(f"duplicate DOI also used by {seen_dois[doi]}")
            else:
                seen_dois[doi] = key
            if offline:
                result["issues"].append("DOI not queried in offline mode")
            elif not result["issues"]:
                try:
                    record, metadata_receipt = cached_crossref_record(doi, fetcher, cache_directory,
                                                                       refresh=refresh_metadata)
                    result["metadata_receipt"] = metadata_receipt
                    crossref_title = " ".join(record.get("title", []))
                    similarity = title_similarity(title, crossref_title)
                    result["crossref"] = {
                        "title": crossref_title,
                        "year": record_year(record),
                        "type": record.get("type"),
                        "url": record.get("URL"),
                        "title_similarity": round(similarity, 4),
                    }
                    field_checks, field_issues = _crossref_fields(fields, record)
                    result["crossref"].update(field_verification=field_checks,
                        field_accuracy_verified=bool(field_checks) and not field_issues)
                    result["issues"].extend(field_issues)
                    if similarity < 0.75:
                        result["issues"].append("title does not sufficiently match Crossref")
                    bib_year = fields.get("year")
                    crossref_year = record_year(record)
                    if bib_year and crossref_year is None:
                        result["issues"].append("Crossref year field accuracy is unknown")
                    if bib_year and bib_year.isdigit() and crossref_year and int(bib_year) != crossref_year:
                        result["issues"].append(
                            f"year mismatch: bibliography {bib_year}, Crossref {crossref_year}"
                        )
                    if not result["issues"]:
                        result["status"] = "verified_crossref"
                except (NetworkSafetyError, CitationAuditError, OSError) as exc:
                    result["issues"].append(f"Crossref verification failed: {exc}")
        else:
            try:
                identity = provider_identity(bib_path, fields)
                result["provider_identity"] = identity
                if not result["issues"]:
                    result["status"] = "verified_provider_identity"
            except CitationAuditError as exc:
                if key in manual:
                    verification = manual[key]
                    similarity = title_similarity(title, verification["title"])
                    result["manual_verification"] = verification
                    if similarity < 0.75:
                        result["issues"].append("title does not match the manual verification record")
                    elif not result["issues"]:
                        result["status"] = "verified_manual"
                else:
                    result["issues"].append(str(exc))
        findings.append(result)
    unresolved = [item["citation_key"] for item in findings if not item["status"].startswith("verified_")]
    bibliography_keys = {entry["key"] for entry in entries}
    tex_path = bib_path.parent / "main.tex"
    docx_path = bib_path.parent / "main.docx"
    manuscript_path = tex_path if tex_path.is_file() else docx_path if docx_path.is_file() else None
    usage_errors = []
    if tex_path.is_file():
        occurrences = citation_usages(tex_path)
        cited_keys = {row["citation_key"] for row in occurrences}
    elif docx_path.is_file():
        occurrences, usage_errors = _docx_usage_inventory(docx_path)
        cited_keys = {row["citation_key"] for row in occurrences}
    else:
        cited_keys, occurrences = set(), []
    unresolved.extend("usage:" + error for error in usage_errors)
    missing_citations = sorted(cited_keys - bibliography_keys)
    if missing_citations:
        unresolved.extend(f"missing:{key}" for key in missing_citations)
    return {
        "schema_version": "1.0",
        "created_at": now(),
        "bibliography": str(bib_path),
        "bibliography_sha256": sha256_file(bib_path),
        "manuscript": str(manuscript_path) if manuscript_path else None,
        "manuscript_sha256": manuscript_digest(manuscript_path) if manuscript_path else None,
        "offline": offline,
        "entry_count": len(entries),
        "verified_count": sum(item["status"].startswith("verified_") for item in findings),
        "unresolved_count": len(unresolved),
        "unresolved_keys": unresolved,
        "status": "pass" if entries and not unresolved else "fail",
        "citation_usage": {
            "status": (
                "checked_automatically" if (tex_path.is_file() or docx_path.is_file()) and not usage_errors
                else "mapping_required" if docx_path.is_file()
                else "no_manuscript_found"
            ),
            "verified_by": docx_verified_by.strip() if isinstance(docx_verified_by,str) and docx_verified_by.strip() else None,
            "verified_at": now() if docx_path.is_file() and isinstance(docx_verified_by,str) and docx_verified_by.strip() else None,
            "cited_keys": sorted(cited_keys),
            "occurrences": occurrences,
            "missing_bibliography_keys": missing_citations,
            "unused_bibliography_keys": sorted(bibliography_keys - cited_keys)
            if tex_path.is_file()
            else [],
            "mapping_errors": usage_errors,
            "note": "Explicit citation keys checked against the bibliography; unsupported DOCX formats remain unresolved.",
        },
        "findings": findings,
    }


def _citation_population(path: Path) -> dict:
    """Prove a literal BibTeX population, or keep coverage explicitly unknown."""
    unknown = {"status": "coverage_unknown", "citation_keys": None}
    if path.suffix.lower() != ".bib":
        return {**unknown, "reason": "This source has no mechanically established bibliography population."}
    from scripts.tex_sources import comments
    text = comments(path.read_text(encoding="utf-8"))
    entries = parse_bibtex(text)
    if not entries or len(entries) > 5000 or any(not row["balanced"] for row in entries):
        return {**unknown, "reason": "The complete literal BibTeX population could not be parsed."}
    keys = [row["key"] for row in entries]
    if len(set(keys)) != len(keys):
        return {**unknown, "reason": "Duplicate BibTeX keys prevent a unique source population."}
    cursor = 0
    for match in ENTRY_RE.finditer(text):
        if match.start() < cursor or text[cursor:match.start()].strip():
            return {**unknown, "reason": "Unsupported BibTeX content prevents proof of the complete population."}
        cursor, depth = match.end(), 1
        while cursor < len(text) and depth:
            if text[cursor] == "{": depth += 1
            elif text[cursor] == "}": depth -= 1
            cursor += 1
        if depth:
            return {**unknown, "reason": "An incomplete BibTeX entry prevents proof of the complete population."}
    if text[cursor:].strip():
        return {**unknown, "reason": "Unparsed BibTeX content prevents proof of the complete population."}
    return {"status": "known", "citation_keys": sorted(keys), "basis": "complete_literal_bibtex"}


CROSSCHECK_ROLE_CONTRACT = "Independently return citation_extraction:{source,records:[{citation_key,doi,title,year,authors}]}. Read only the bound original source; extract every bibliographic record, including its exact citation key. Do not inspect another extractor, prior differences or prior verdicts. Unknown fields remain null."


def crosscheck(project: Path, spec: dict) -> dict:
    """Mechanical comparison of two separately retained extraction artifacts.

    Distinct files and extractor identities are observable. Their claimed mutual
    blindness and the semantic correctness of either extraction are not inferred.
    """
    from scripts.research_artifacts import bound_source, path_in, read
    from scripts.output_provenance import current_origin
    from scripts.literature_workbench import _id, _text
    if not isinstance(spec, dict) or set(spec) - {"schema_version", "id", "source", "extractions", "paper_id"} or spec.get("schema_version") != "1.0":
        raise ValueError("citation crosscheck needs a source and two retained extractions")
    from scripts.literature_source_tasks import citation_source
    source = citation_source(project, spec)
    population = _citation_population(path_in(project, source["path"]))
    incoming = spec.get("extractions")
    panel, controlled = {}, {}
    if incoming is None:
        from scripts.literature_source_tasks import citation_extractions, judgment_responses
        frozen = citation_extractions(project, spec)
        incoming = [row["binding"] for row in frozen]
        controlled = {row["binding"]["path"]: row for row in frozen}
        if not frozen:
            for row in judgment_responses(project, spec.get("paper_id")):
                extracted = row["response"].get("citation_extraction")
                if extracted is not None:
                    receipt = row["receipt"]
                    binding = {**receipt["response"], "locator": "original independent citation extraction"}
                    incoming.append(binding)
                    panel[binding["path"]] = {**extracted, "extractor": receipt["role"] + ":" + receipt["identity"]["requested_model"]}
        if len(incoming) < 2:
            return {"schema_version": "1.0", "operation": "citation_crosscheck", "id": _id(spec["id"]),
                "source": source, "extractions": incoming, "status": "awaiting_two_independent_extractions",
                "source_population": population,
                "coverage": {"status": "awaiting_two_independent_extractions", "extractions": []},
                "differences": [], "unknown_fields": [], "blindness_verified": False, "semantic_support_verified": False,
                "model_call_made": False, "scientific_completion_verified": False,
                "role_contract": CROSSCHECK_ROLE_CONTRACT}
    if not isinstance(incoming, list) or len(incoming) != 2:
        raise ValueError("exactly two frozen extraction bindings are required")
    extractions, methods, paths = [], set(), set()
    for binding in incoming:
        bound = bound_source(project, binding)
        target = path_in(project, bound["path"])
        origin = current_origin(project, target)
        if origin.get("status") != "tracked" or bound["path"] in paths or target.stat().st_size > 2_000_000:
            raise ValueError("extraction must be a distinct current provenance-bound artifact")
        if any(word in str(origin.get("role", "")).casefold() for word in ("writer", "author")):
            raise ValueError("a writer cannot declare itself an independent citation extractor")
        paths.add(bound["path"])
        payload = panel.get(bound["path"]) or read(target)
        method = _text(payload.get("extractor"), "actual extractor identity")
        if payload.get("source") != source or method in methods:
            raise ValueError("extractors must be distinct and bind the same original source")
        methods.add(method)
        records = payload.get("records")
        if not isinstance(records, list) or not 1 <= len(records) <= 5000:
            raise ValueError("extraction needs bounded citation records")
        by_key = {}
        for row in records:
            key = _text(row.get("citation_key"), "extracted citation key", 200)
            if key in by_key:
                raise ValueError("duplicate extracted citation key")
            if set(row) - {"citation_key", "doi", "title", "year", "authors"}:
                raise ValueError("unsupported extracted citation fields")
            by_key[key] = row
        extractions.append({"binding": bound, "extractor": method, "origin": origin, "records": by_key})
    left, right = (e["records"] for e in extractions)
    coverage = {"status": "coverage_unknown", "extractions": []}
    if population["status"] == "known":
        expected = set(population["citation_keys"])
        coverage["extractions"] = [{"extractor": row["extractor"],
            "missing_citation_keys": sorted(expected - row["records"].keys()),
            "unexpected_citation_keys": sorted(row["records"].keys() - expected)} for row in extractions]
        coverage["status"] = "incomplete_extraction" if any(row["missing_citation_keys"] or row["unexpected_citation_keys"]
            for row in coverage["extractions"]) else "complete"
    differences, unknown = [], []
    for key in sorted(left.keys() | right.keys()):
        if key not in left or key not in right:
            differences.append({"citation_key": key, "field": "record", "left": left.get(key), "right": right.get(key)})
            continue
        for field in ("doi", "title", "year", "authors"):
            a, b = left[key].get(field), right[key].get(field)
            if a in (None, "", []) or b in (None, "", []):
                unknown.append({"citation_key": key, "field": field, "left": a, "right": b})
                continue
            if field == "doi": a, b = normalize_doi(str(a)), normalize_doi(str(b))
            if field == "title": a, b = normalize_title(str(a)), normalize_title(str(b))
            if a != b:
                differences.append({"citation_key": key, "field": field, "left": a, "right": b})
    return {"schema_version": "1.0", "operation": "citation_crosscheck", "id": _id(spec["id"]),
        "source": source, "extractions": extractions, "differences": differences, "unknown_fields": unknown,
        "source_population": population, "coverage": coverage,
        "status": "differences_need_source_review" if differences else "incomplete_extraction"
            if unknown or coverage["status"] == "incomplete_extraction" else "coverage_unknown"
            if coverage["status"] == "coverage_unknown" else "fields_agree",
        "blindness_verified": False, "bibliographic_truth_verified": False, "semantic_support_verified": False,
        "runtime_extractions_verified": bool(controlled), "source_isolation_verified": bool(controlled),
        "model_call_made": False, "scientific_completion_verified": False,
        "role_contract": CROSSCHECK_ROLE_CONTRACT}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bibliography", type=Path)
    parser.add_argument("--manual-verifications", type=Path)
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--refresh-metadata", action="store_true", help="Bypass the 24h metadata cache when checking changed publisher metadata")
    parser.add_argument("--cache-metadata", action="store_true", help="Control-plane use only: save hash-bound public metadata under project state")
    parser.add_argument("--docx-citations-verified-by",help="Named human who checked every DOCX in-text citation against the bibliography")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = audit(
            args.bibliography,
            manual_path=args.manual_verifications,
            offline=args.offline,
            docx_verified_by=args.docx_citations_verified_by,
            refresh_metadata=args.refresh_metadata,
            cache_directory=_metadata_cache_directory(args.bibliography) if args.cache_metadata else None,
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report["status"] == "pass" else 1
    except CitationAuditError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
