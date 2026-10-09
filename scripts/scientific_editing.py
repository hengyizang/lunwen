"""Conservative context checks for scientific edits; never an authorship detector.

Mechanical signatures flag possible drift for review. They do not prove semantic
equivalence. No rewriting, removal of provenance, or model calls occurs here.
"""
from __future__ import annotations

import json
import re
import unicodedata
import zipfile
from collections import Counter
from pathlib import Path
from xml.etree import ElementTree as ET

NUMBER = re.compile(r"(?<![A-Za-z])[-+]?\d+(?:[.,]\d+)*(?:[eE][-+]?\d+)?%?")
WORD = re.compile(r"[A-Za-z][A-Za-z0-9_-]*|[-+]?\d+(?:[.,]\d+)*(?:[eE][-+]?\d+)?%?")
PROTECTED = re.compile(
    r"\b(?:not|no|never|without|unless|only|except|excluding|excluded|"
    r"may|might|could|causal|causality|associated|correlation|significant|"
    r"nonsignificant|non-significant|independent|paired|unpaired|randomized|"
    r"observational|exploratory|confirmatory|SD|SE|SEM|CI|"
    r"mm|cm|m|km|ms|s|mg|g|kg|ml|mL|mol|Hz|kHz|MPa|Pa)\b", re.I)
FILLER = {"the", "a", "an", "and", "or", "of", "in", "on", "to", "for", "by",
          "with", "was", "were", "is", "are", "has", "have", "it", "this", "that"}
SI_UNITS = {"mm", "cm", "m", "km", "ms", "s", "mg", "g", "kg", "ml", "mL", "mol", "Hz", "kHz", "MPa", "Pa", "M", "mM"}
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


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


def docx_citations(path: Path) -> list[str]:
    """Retain Word citation fields, citation hyperlinks and author/year anchors."""
    result = []
    with zipfile.ZipFile(path) as archive:
        document = ET.fromstring(archive.read("word/document.xml"))
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
        for name in archive.namelist():
            if name == "word/_rels/document.xml.rels":
                for node in ET.fromstring(archive.read(name)):
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


def scientific_text(path: Path) -> str:
    """Language cleanup must not erase equations from scientific drift checks."""
    if path.suffix.lower() == ".tex":
        try:
            from scripts.citation_audit import tex_source_paths
        except ImportError:
            from citation_audit import tex_source_paths
        return "\n".join(re.sub(r"(?m)(?<!\\)%.*$", "", p.read_text(encoding="utf-8"))
                         for p in sorted(tex_source_paths(path)))
    try:
        from scripts.manuscript_language import extract_text
    except ImportError:
        from manuscript_language import extract_text
    return extract_text(path)


def formula_tokens(path: Path) -> list[str]:
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
        with zipfile.ZipFile(path) as archive:
            root = ET.fromstring(archive.read("word/document.xml"))
        math = "{http://schemas.openxmlformats.org/officeDocument/2006/math}oMath"
        return [ET.tostring(node, encoding="unicode") for node in root.iter(math)]
    return []
