"""Cloud-only, source-preserving Unicode hygiene using pinned upstream code.

This removes only approved character-level artifacts from prose candidates.
It does not establish authorship, remove statistical watermarks, rewrite text,
change scientific images, or remove provenance/disclosure metadata.
"""
from __future__ import annotations

import copy
import difflib
import hashlib
import importlib.util
import io
import json
import os
import re
import sys
import unicodedata
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path

try:
    from scripts import output_provenance
    from scripts.research_artifacts import path_in
except ImportError:
    import output_provenance  # type: ignore
    from research_artifacts import path_in  # type: ignore

ROOT = Path(__file__).resolve().parents[1]
UPSTREAM_COMMIT = "c5297e9e69fec0779c29127c7892427e673fafd9"
UPSTREAM_PATH = "third_party/watermarks-remover/scripts/text_unicode.py"
UPSTREAM_SHA256 = "ed86ed9715f40e306371731f97bf6f2a63f6a7719674630afac89eb3741bc6fd"
UPSTREAM_URL = "https://github.com/guillaumemeyer/watermarks-remover"
MAX_TEXT_BYTES = 2_000_000
MAX_SOURCE_BYTES = 20_000_000
MAX_ZIP_BYTES = 50_000_000
MAX_ZIP_MEMBERS = 2000
MAX_FINDINGS = 10_000
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
M = "{http://schemas.openxmlformats.org/officeDocument/2006/math}"
DOCUMENT = "word/document.xml"
OPTIONS = {"nfkc": False, "aggressive_homoglyphs": False, "normalize_spaces": False,
           "strip_emoji_glue": False, "strip_bidi": False}
DISCLOSURE = re.compile(r"\b(?:AI[ -]?(?:use|assisted|assistance|generated|disclosure|tools?|statement)|artificial intelligence|"
                        r"ChatGPT|OpenAI|Anthropic|Claude|GPT[- ]?\d|language model|"
                        r"LLM|acknowledg(?:e)?ments?|author contributions?|conflicts? of interest|funding|declarations?|provenance)\b|"
                        r"人工智能|大语言模型|AI\s*(?:使用|辅助|生成|披露|声明)|作者贡献|利益冲突|资金来源", re.I)


def digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _upstream():
    source = ROOT / UPSTREAM_PATH
    if any(p.is_symlink() for p in (source, *source.parents)):
        raise ValueError("upstream module cannot be a symlink")
    payload = source.read_bytes()
    canonical = payload.replace(b"\r\n", b"\n")
    if digest(canonical) != UPSTREAM_SHA256:
        raise ValueError("pinned watermarks-remover implementation hash changed")
    name = "_lunwen_watermarks_unicode_" + UPSTREAM_SHA256[:16]
    module = sys.modules.get(name)
    if module is None:
        spec = importlib.util.spec_from_file_location(name, source)
        if spec is None or spec.loader is None:
            raise ValueError("cannot load pinned Unicode implementation")
        module = importlib.util.module_from_spec(spec)
        # Dataclass resolves annotations through sys.modules during import.
        sys.modules[name] = module
        # Execute precisely the verified bytes without a second source read or
        # an import-generated .pyc write in the vendored directory.
        exec(compile(canonical, str(source), "exec"), module.__dict__)
    if source.read_bytes() != payload:
        raise ValueError("upstream implementation changed while importing")
    return module, {"repository": UPSTREAM_URL, "commit": UPSTREAM_COMMIT, "path": UPSTREAM_PATH,
                    "sha256": digest(payload), "canonical_lf_sha256": UPSTREAM_SHA256,
                    "supporting_files": [{"path": relative, "sha256": digest((ROOT / relative).read_bytes())}
                        for relative in ("third_party/watermarks-remover/SKILL.md", "third_party/watermarks-remover/LICENSE",
                                         "third_party/watermarks-remover/references/detectors.md",
                                         "third_party/watermarks-remover/references/responsible-use.md",
                                         "third_party/watermarks-remover/references/writing-in-your-voice.md")]}


def _inspection_text(text: str) -> tuple[str, list[int]]:
    chars, indices = [], []
    for index, char in enumerate(text):
        if unicodedata.category(char) not in {"Cf", "Cc"} or char in "\n\r\t":
            chars.append(char)
            indices.append(index)
    return "".join(chars), indices


def _protected_spans(text: str, format: str) -> list[tuple[int, int, str]]:
    spans: list[tuple[int, int, str]] = []
    def matches(pattern, kind, flags=0):
        spans.extend((m.start(), m.end(), kind) for m in re.finditer(pattern, text, flags))
    # Source syntax and quotations stay byte-for-byte unchanged. Unclosed
    # fences/verbatim/math spans fail conservatively by protecting the suffix.
    matches(r"(?ms)^\s{0,3}(`{3,}|~{3,})[^\r\n]*\r?\n.*?(?:^\s{0,3}\1\s*$|\Z)", "code-fence")
    matches(r"(`+)(?!`).*?\1(?!`)", "inline-code", re.S)
    matches(r"(?ms)<(script|style|pre|code)\b[^>]*>.*?(?:</\1\s*>|\Z)", "html-code")
    matches(r"<[^>\r\n]+>", "html-markup")
    matches(r"https?://[^\s<>\"']+|(?:doi:)?10\.\d{4,9}/[^\s<>]+", "url-doi", re.I)
    matches(r'"[^"\r\n]*"|“[^”]*”|‘[^’]*’|(?<!\w)\'[^\'\r\n]+\'(?!\w)', "verbatim-quote")
    matches(r"(?s)(?<!\\)\$\$.*?(?:(?<!\\)\$\$|\Z)|(?<![\\$])\$(?!\$).*?(?:(?<!\\)\$(?!\$)|\Z)", "math")
    matches(r"(?s)\\\[.*?(?:\\\]|\Z)|\\\(.*?(?:\\\)|\Z)", "math")
    if format == "md":
        matches(r"\A(?:\ufeff)?---\s*\r?\n[\s\S]*?(?:\r?\n(?:---|\.\.\.)\s*(?:\r?\n|\Z)|\Z)", "frontmatter")
        matches(r"(?m)^\s{0,3}>[^\r\n]*(?:\r?\n|$)", "blockquote")
        matches(r"(?m)^\s{0,3}\[[^\]\r\n]+\]:[^\r\n]*", "link-definition")
        matches(r"!?\[[^\]\r\n]*\](?:\([^\r\n]*?\)|\[[^\]\r\n]*\])", "link-image")
        # Entire link-bearing lines are conservative protection for nested
        # Markdown destinations/titles; no guessed partial URL is rewritten.
        matches(r"(?m)^[^\r\n]*!?\[[^\]\r\n]+\]\([^\r\n]*$", "complex-link-line")
        matches(r"\[[^\]\r\n]+\]", "bracket-reference")
        matches(r"\[[^\]\r\n]*@[^\]\r\n]+\]", "citation")
    if format == "tex":
        matches(r"(?m)(?<!\\)%[^\r\n]*", "tex-comment")
        matches(r"(?s)\\begin\{(equation\*?|align\*?|gather\*?|multline\*?|math|displaymath|array|tabular\*?|table\*?|figure\*?|verbatim\*?|Verbatim|lstlisting|minted|tikzpicture|algorithm|algorithmic|thebibliography)\}.*?(?:\\end\{\1\}|\Z)", "tex-environment")
        # A balanced scanner protects all macro arguments, even nested ones.
        # Unknown commands are preserved rather than guessed to contain prose.
        for match in re.finditer(r"\\(?:[A-Za-z@]+\*?|.)", text):
            position = match.end()
            if match.group(0).startswith(r"\verb"):
                if position < len(text) and text[position] not in "\r\n":
                    end = text.find(text[position], position + 1)
                    spans.append((match.start(), len(text) if end < 0 else end + 1, "tex-verbatim"))
                continue
            end = position
            while position < len(text):
                while position < len(text) and text[position].isspace():
                    position += 1
                if position >= len(text) or text[position] not in "[{":
                    break
                opener, closer = text[position], "]" if text[position] == "[" else "}"
                depth, position = 1, position + 1
                while position < len(text) and depth:
                    if text[position] == "\\":
                        position += 2
                        continue
                    if text[position] == opener:
                        depth += 1
                    elif text[position] == closer:
                        depth -= 1
                    position += 1
                end = min(position, len(text))
                if depth:
                    break
            spans.append((match.start(), end, "tex-macro"))
    # Inspect through invisible characters solely to locate protected material.
    # This never changes or normalizes the actual source text.
    visible, indices = _inspection_text(text)
    if indices:
        for pattern, kind in ((r"\b[+-]?\d+(?:[.,]\d+)*(?:[eE][+-]?\d+)?\b", "exact-number"),
                              (r"\([^()\r\n]*(?:19|20)\d{2}[a-z]?[^()\r\n]*\)|\[\d+(?:[,; -]\d+)*\]", "citation")):
            for match in re.finditer(pattern, visible):
                spans.append((indices[match.start()], indices[match.end() - 1] + 1, kind))
        for match in re.finditer(r"[^\r\n]*(?:\r?\n|$)", visible):
            if match.end() > match.start() and (DISCLOSURE.search(match.group(0))
                    or re.match(r"\s*(?:author|source|license|copyright|created|metadata|origin|作者|来源|许可)\s*[:：]", match.group(0), re.I)):
                spans.append((indices[match.start()], indices[match.end() - 1] + 1, "disclosure-provenance"))
        # Markdown/plain disclosure headings protect their whole section.
        headings = list(re.finditer(r"(?m)^(#{1,6})\s+([^\r\n]+)", visible))
        for index, match in enumerate(headings):
            if not DISCLOSURE.search(match.group(2)):
                continue
            end = len(visible)
            for following in headings[index + 1:]:
                if len(following.group(1)) <= len(match.group(1)):
                    end = following.start()
                    break
            spans.append((indices[match.start()], indices[end - 1] + 1, "disclosure-section"))
        if format == "tex":
            headings = list(re.finditer(r"\\(chapter|section|subsection|subsubsection)\*?(?:\[[^]]*\])?\{([^}]+)\}", visible))
            levels = {"chapter": 0, "section": 1, "subsection": 2, "subsubsection": 3}
            for index, match in enumerate(headings):
                if not DISCLOSURE.search(match.group(2)):
                    continue
                end = len(visible)
                for following in headings[index + 1:]:
                    if levels[following.group(1)] <= levels[match.group(1)]:
                        end = following.start()
                        break
                spans.append((indices[match.start()], indices[end - 1] + 1, "disclosure-section"))
    if text.startswith("\ufeff"):
        spans.append((0, 1, "encoding-bom"))
    return sorted(spans)


def _safety_preserve(char: str) -> bool:
    cp = ord(char)
    # Never interpret real directional controls, combining grapheme joiners,
    # mathematical invisible operators or private-use scientific glyphs as
    # proven watermarks. Upstream itself preserves valid script/emoji glue.
    return (cp in {0x034F, 0x061C, 0x200E, 0x200F, 0x2061, 0x2062, 0x2063, 0x2064}
            or 0x202A <= cp <= 0x202E or 0x2066 <= cp <= 0x206F
            or unicodedata.category(char) == "Co")


def _clean(text: str, format: str, extra_spans=()) -> tuple[str, dict]:
    if format not in {"txt", "md", "tex"} or not isinstance(text, str):
        raise ValueError("Unicode candidates support txt, md or tex strings")
    if len(text.encode("utf-8")) > MAX_TEXT_BYTES:
        raise ValueError("text exceeds the bounded Unicode cleanup limit")
    upstream, source = _upstream()
    candidate, upstream_stats = upstream.clean_text(text, **OPTIONS)
    spans = _protected_spans(text, format) + list(extra_spans)
    mask = bytearray(len(text))
    for start, end, _kind in spans:
        if not 0 <= start <= end <= len(text):
            raise ValueError("invalid protected source span")
        mask[start:end] = b"\1" * (end - start)
    changed, retained, out = [], [], []
    position, line, column = 0, 1, 1
    for index, char in enumerate(text):
        removed = position >= len(candidate) or char != candidate[position]
        if not removed:
            position += 1
            out.append(char)
        else:
            item = {"offset": index, "line": line, "column": column, "codepoint": f"U+{ord(char):04X}",
                    "character": char, "name": unicodedata.name(char, "UNNAMED")}
            if mask[index] or _safety_preserve(char):
                out.append(char)
                retained.append({**item, "reason": "protected_source_span" if mask[index] else "legitimate_unicode_safety"})
            else:
                changed.append(item)
            if len(changed) + len(retained) > MAX_FINDINGS:
                raise ValueError("too many Unicode findings for a complete bounded audit")
        line, column = (line + 1, 1) if char == "\n" else (line, column + 1)
    if position != len(candidate):
        raise ValueError("upstream attempted a replacement; only conservative deletions are authorized")
    cleaned = "".join(out)
    return cleaned, {"format": format, "input_characters": len(text), "output_characters": len(cleaned),
                     "removed_count": len(changed), "changes": changed, "retained_findings": retained,
                     "protected_spans": [{"start": a, "end": b, "kind": kind} for a, b, kind in sorted(spans)],
                     "upstream_statistics": upstream_stats, "upstream": source, "options": dict(OPTIONS),
                     "scientific_equivalence_proven": False, "human_review_required": True}


def clean_text_candidate(text: str, format: str = "txt") -> tuple[str, dict]:
    """Pure string-to-candidate operation; performs no writes or model calls."""
    return _clean(text, format)


def _docx(payload: bytes) -> tuple[bytes, dict, str, str]:
    from lxml import etree as ET
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        infos = archive.infolist()
        if (len(infos) > MAX_ZIP_MEMBERS or len({item.filename for item in infos}) != len(infos)
                or sum(item.file_size for item in infos) > MAX_ZIP_BYTES):
            raise ValueError("duplicate or oversized DOCX package")
        for item in infos:
            parts = Path(item.filename).parts
            if (item.filename.startswith(("/", "\\")) or ".." in parts or "\\" in item.filename
                    or ":" in item.filename or item.flag_bits & 1 or item.file_size > MAX_SOURCE_BYTES
                    or item.file_size > max(100_000, item.compress_size * 300)):
                raise ValueError("unsafe, encrypted or excessive-compression DOCX member")
        parts = {item.filename: archive.read(item) for item in infos}
        comment = archive.comment
    if DOCUMENT not in parts or len(parts[DOCUMENT]) > MAX_TEXT_BYTES * 3:
        raise ValueError("DOCX lacks a bounded document.xml")
    try:
        root = ET.fromstring(parts[DOCUMENT], parser=ET.XMLParser(resolve_entities=False, no_network=True))
    except ET.XMLSyntaxError as exc:
        raise ValueError("invalid DOCX document XML") from exc
    if root.getroottree().docinfo.doctype:
        raise ValueError("DOCX entities/DTD are unsupported")
    if any(node.tag in {W + "ins", W + "del", W + "moveFrom", W + "moveTo"} for node in root.iter()):
        raise ValueError("resolve existing Word revisions before Unicode cleanup")
    original = copy.deepcopy(root)
    field_nodes, depth = set(), 0
    for node in root.iter():
        if node.tag == W + "fldChar":
            kind = node.get(W + "fldCharType")
            if kind == "begin":
                depth += 1
            elif kind == "end":
                depth -= 1
            if depth < 0 or depth > 32:
                raise ValueError("invalid nested DOCX field")
        if node.tag == W + "t" and depth:
            field_nodes.add(node)
    if depth:
        raise ValueError("unterminated DOCX field")
    paragraphs, changes, before_text, after_text = [], [], [], []
    if sum(1 for _ in root.iter(W + "p")) > 5000:
        raise ValueError("DOCX paragraph audit exceeds its bounded 5000-paragraph limit")
    disclosure_level, total_findings, total_prose_bytes = None, 0, 0
    allowed_ancestors = {W + name for name in ("document", "body", "tbl", "tr", "tc", "p", "r")}
    for number, paragraph in enumerate(root.iter(W + "p"), 1):
        nodes = [node for node in paragraph.iter(W + "t")
                 if next((p for p in node.iterancestors() if p.tag == W + "p"), None) is paragraph]
        text = "".join(node.text or "" for node in nodes)
        total_prose_bytes += len(text.encode("utf-8"))
        if total_prose_bytes > MAX_TEXT_BYTES:
            raise ValueError("combined DOCX prose exceeds the bounded cleanup limit")
        visible = _inspection_text(text)[0]
        style = paragraph.find(W + "pPr/" + W + "pStyle")
        style_name = style.get(W + "val", "") if style is not None else ""
        heading = re.fullmatch(r"Heading([1-9])", style_name, re.I)
        if heading:
            level = int(heading.group(1))
            if disclosure_level is not None and level <= disclosure_level:
                disclosure_level = None
            if DISCLOSURE.search(visible):
                disclosure_level = level
        extra, offset = [], 0
        if disclosure_level is not None or DISCLOSURE.search(visible):
            extra.append((0, len(text), "disclosure-provenance"))
        for node in nodes:
            run = node.getparent()
            eligible = (run.tag == W + "r" and node not in field_nodes
                        and all(parent.tag in allowed_ancestors for parent in node.iterancestors())
                        and all(child.tag in {W + "rPr", W + "t", W + "tab", W + "br", W + "cr"} for child in run))
            end = offset + len(node.text or "")
            if not eligible:
                extra.append((offset, end, "complex-word-object"))
            offset = end
        cleaned, detail = _clean(text, "txt", extra)
        total_findings += detail["removed_count"] + len(detail["retained_findings"])
        if total_findings > MAX_FINDINGS:
            raise ValueError("DOCX has too many findings for a complete bounded audit")
        removed = {item["offset"] for item in detail["changes"]}
        offset = 0
        for node in nodes:
            content = node.text or ""
            replacement = "".join(char for index, char in enumerate(content, offset) if index not in removed)
            if replacement != content:
                changes.append((node, content))
                node.text = replacement
            offset += len(content)
        detail["paragraph"] = number
        paragraphs.append(detail)
        before_text.append(text)
        after_text.append(cleaned)
    # Prove no structural/property/citation/math/link or other XML change was
    # introduced. Original resources and package metadata are copied verbatim.
    restored = copy.deepcopy(root)
    old_nodes, new_nodes = list(original.iter(W + "t")), list(restored.iter(W + "t"))
    for old, new in zip(old_nodes, new_nodes):
        new.text = old.text
    if ET.tostring(restored) != ET.tostring(original):
        raise ValueError("Word cleanup attempted a non-text structural change")
    if not changes:
        derived = payload
    else:
        parts[DOCUMENT] = ET.tostring(root, encoding="utf-8", xml_declaration=True)
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.comment = comment
            for item in infos:
                archive.writestr(copy.copy(item), parts[item.filename])
        derived = buffer.getvalue()
    report = {"format": "docx", "paragraphs": paragraphs,
              "removed_count": sum(item["removed_count"] for item in paragraphs),
              "changed_text_nodes": len(changes), "unchanged_package_parts": sorted(name for name in parts if name != DOCUMENT),
              "non_text_xml_unchanged": True, "metadata_and_relationships_preserved": True,
              "human_review_required": True, "scientific_equivalence_proven": False}
    return derived, report, "\n".join(before_text), "\n".join(after_text)


def _process(payload: bytes, suffix: str) -> tuple[bytes, dict, str, str]:
    if suffix == ".docx":
        try:
            return _docx(payload)
        except (zipfile.BadZipFile, KeyError) as exc:
            raise ValueError("invalid DOCX package") from exc
    if suffix not in {".txt", ".md", ".tex"}:
        raise ValueError("Unicode cleanup supports txt, md, tex and bounded DOCX text only")
    text = payload.decode("utf-8")
    cleaned, details = clean_text_candidate(text, suffix[1:])
    return cleaned.encode("utf-8"), details, text, cleaned


def _input(project: Path, paper_id: str, source: str) -> Path:
    if not re.fullmatch(r"P[0-9]{2}", paper_id):
        raise ValueError("invalid paper ID")
    if not isinstance(source, str) or not source.startswith(f"papers/{paper_id}/manuscript/"):
        raise ValueError("cleanup input must belong to the named paper's manuscript directory")
    target = path_in(project, source)
    if target.stat().st_size > MAX_SOURCE_BYTES:
        raise ValueError("cleanup source exceeds the bounded input limit")
    return target


def _diff(before: str, after: str) -> bytes:
    result = "".join(difflib.unified_diff(before.splitlines(keepends=True), after.splitlines(keepends=True),
                                        fromfile="original-preserved", tofile="derived-candidate", n=3)).encode("utf-8")
    if len(result) > MAX_TEXT_BYTES * 2:
        raise ValueError("complete diff exceeds the bounded audit limit")
    return result


def build(project: Path, paper_id: str, source: str, expected_sha256: str) -> dict:
    if os.environ.get("GITHUB_ACTIONS", "").lower() != "true" and os.environ.get("DR_OS_CLOUD_EXECUTOR") != "1":
        raise ValueError("Unicode cleanup writer requires cloud execution")
    project = project.resolve()
    target = _input(project, paper_id, source)
    payload = target.read_bytes()
    if not isinstance(expected_sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", expected_sha256) or digest(payload) != expected_sha256:
        raise ValueError("cleanup input hash is missing or stale")
    source_origin = output_provenance.current_origin(project, target)
    derived, details, before, after = _process(payload, target.suffix.lower())
    _, upstream = _upstream()
    if target.read_bytes() != payload:
        raise ValueError("cleanup input changed during processing")
    identifier = uuid.uuid4().hex
    relative = "reports/watermark-cleanup/" + identifier
    output = path_in(project, relative + "/candidate" + target.suffix.lower(), exists=False)
    output.parent.mkdir(parents=True, exist_ok=False)
    changes, diff, receipt_path = output.parent / "changes.json", output.parent / "diff.txt", output.parent / "receipt.json"
    output.write_bytes(derived)
    changes.write_text(json.dumps(details, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    diff.write_bytes(_diff(before, after))
    result = {"schema_version": "1.0", "status": "candidate_created", "paper_id": paper_id, "id": identifier,
              "created_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
              "input": {"path": source, "sha256": expected_sha256, "origin": source_origin},
              "outputs": [{"path": p.relative_to(project).as_posix(), "sha256": digest(p.read_bytes())} for p in (output, changes, diff)],
              "upstream": upstream, "implementation": {"path": "scripts/watermark_cleanup.py", "sha256": digest(Path(__file__).read_bytes())},
              "execution": {"mode": "cloud", "receipt_id": os.environ.get("GITHUB_RUN_ID") or os.environ.get("DR_OS_CLOUD_EXECUTION_RECEIPT_ID") or "cloud-cleanup-" + identifier},
              "removed_count": details["removed_count"], "options": dict(OPTIONS), "original_overwritten": False,
              "source_origin_preserved": True, "canonical_promotion_allowed": False, "ai_disclosure_preserved": True,
              "human_scientific_review_required": True, "statistical_watermarks": {"KGW": "not_assessed", "SynthID_Text": "not_assessed"},
              "authorship_or_detector_evasion_verified": False, "scientific_equivalence_proven": False,
              "media_scope": "text Unicode only; image pixels, C2PA, EXIF, authorship/source metadata are not modified",
              "paid_calls": 0, "rewrites": 0}
    receipt_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    ancestry = source_origin.get("family") or source_origin.get("previous_family")
    output_provenance.record_model_writes(project, [output], family="anthropic" if ancestry == "anthropic" else "other",
                                        provider="watermark-unicode-derived-copy", model="pinned-upstream-unicode-cleaner",
                                        role="candidate-only-not-authorship-attestation", run_id=identifier)
    output_provenance.record_model_writes(project, [changes, diff, receipt_path], family="other",
                                        provider="deterministic-watermark-cleanup", model="scripts/watermark_cleanup.py",
                                        role="protected-unicode-cleanup-audit", run_id=identifier)
    if target.read_bytes() != payload:
        raise ValueError("cleanup source changed before audit completion")
    return result


def validate_saved_report(project: Path, receipt_relative: str) -> list[str]:
    """Recompute the exact transformation; a model-authored receipt cannot pass."""
    try:
        project = project.resolve()
        if not re.fullmatch(r"reports/watermark-cleanup/[0-9a-f]{32}/receipt\.json", receipt_relative):
            raise ValueError("cleanup receipt path is outside the protected output directory")
        receipt = path_in(project, receipt_relative)
        value = json.loads(receipt.read_text(encoding="utf-8"))
        if not isinstance(value, dict) or value.get("schema_version") != "1.0" or value.get("status") != "candidate_created":
            raise ValueError("invalid Unicode cleanup receipt")
        origin = output_provenance.current_origin(project, receipt)
        if origin.get("status") != "tracked" or origin.get("provider") != "deterministic-watermark-cleanup" or origin.get("family") != "other":
            raise ValueError("Unicode cleanup receipt lacks protected control-plane provenance")
        if value.get("id") != receipt.parent.name or origin.get("run_id") != value.get("id"):
            raise ValueError("Unicode cleanup receipt identity does not match its protected run")
        execution = value.get("execution", {})
        if not isinstance(execution, dict) or execution.get("mode") != "cloud" or not str(execution.get("receipt_id", "")).strip():
            raise ValueError("Unicode cleanup receipt lacks cloud execution identity")
        source = _input(project, value["paper_id"], value["input"]["path"])
        payload = source.read_bytes()
        if digest(payload) != value["input"]["sha256"]:
            raise ValueError("Unicode cleanup source hash is stale")
        if output_provenance.current_origin(project, source) != value["input"]["origin"]:
            raise ValueError("Unicode cleanup source origin changed")
        _, upstream = _upstream()
        if value.get("upstream") != upstream or value.get("implementation", {}).get("sha256") != digest(Path(__file__).read_bytes()):
            raise ValueError("Unicode cleanup implementation or upstream receipt is stale")
        derived, details, before, after = _process(payload, source.suffix.lower())
        expected = {"candidate" + source.suffix.lower(): derived,
                    "changes.json": (json.dumps(details, ensure_ascii=False, indent=2) + "\n").encode("utf-8"), "diff.txt": _diff(before, after)}
        outputs = value.get("outputs", [])
        if not isinstance(outputs, list) or len(outputs) != 3:
            raise ValueError("Unicode cleanup outputs must exactly cover candidate, changes and diff")
        seen = set()
        for item in outputs:
            output = path_in(project, item["path"])
            if output.parent != receipt.parent or output.name not in expected or output.name in seen:
                raise ValueError("Unicode cleanup output is outside its immutable candidate directory")
            if output.read_bytes() != expected[output.name] or digest(output.read_bytes()) != item["sha256"]:
                raise ValueError("Unicode cleanup candidate, diff or change audit was modified")
            output_origin = output_provenance.current_origin(project, output)
            if output_origin.get("status") != "tracked" or output_origin.get("run_id") != value["id"]:
                raise ValueError("Unicode cleanup output lacks its current protected provenance")
            if output.name.startswith("candidate"):
                ancestry = value["input"]["origin"].get("family") or value["input"]["origin"].get("previous_family")
                if output_origin.get("provider") != "watermark-unicode-derived-copy" or (ancestry == "anthropic" and output_origin.get("family") != "anthropic"):
                    raise ValueError("Unicode cleanup cannot change the source's authorship lineage")
            seen.add(output.name)
        if value.get("canonical_promotion_allowed") is not False or value.get("ai_disclosure_preserved") is not True or value.get("original_overwritten") is not False:
            raise ValueError("Unicode cleanup receipt cannot authorize source replacement or disclosure changes")
        if value.get("removed_count") != details["removed_count"] or value.get("options") != OPTIONS:
            raise ValueError("Unicode cleanup count/options do not match actual processing")
        if (value.get("statistical_watermarks") != {"KGW": "not_assessed", "SynthID_Text": "not_assessed"}
                or value.get("scientific_equivalence_proven") is not False or value.get("authorship_or_detector_evasion_verified") is not False
                or value.get("paid_calls") != 0 or value.get("rewrites") != 0 or value.get("human_scientific_review_required") is not True):
            raise ValueError("Unicode cleanup cannot certify statistical watermark removal, scientific equivalence or authorship")
        return []
    except (OSError, ValueError, KeyError, TypeError, AttributeError, zipfile.BadZipFile) as exc:
        return [str(exc)]
