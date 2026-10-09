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
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def signatures(text: str) -> list[str]:
    """Bind protected tokens to clauses and local content, catching value swaps.

    Conservative false positives are reviewed, never auto-fixed. Formatting-only
    TeX commands and conjunctions are ignored; material qualifiers are retained.
    """
    text = re.sub(r"\\(?:cite|citep|citet|parencite|textcite|autocite)\*?(?:\[[^]]*\])*\{([^}]*)\}",
                  r" CITATION_\1 ", text)
    text = re.sub(r"\\[A-Za-z]+", " ", text)
    result = []
    for clause in re.split(r"(?<!\d)[.!?;\n]+(?!\d)|\b(?:whereas|while|but)\b", text, flags=re.I):
        tokens = [t.casefold() for t in WORD.findall(clause) if t.casefold() not in FILLER]
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
        for node in document.iter():
            if node.tag == W+"instrText" or node.tag == W+"fldSimple":
                value = node.text or node.get(W+"instr", "")
                if re.search(r"CITATION|ZOTERO|CSL_CITATION|EN\.CITE", value, re.I):
                    result.append(re.sub(r"\s+", " ", value).strip())
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
