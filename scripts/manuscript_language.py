#!/usr/bin/env python3
"""Deterministically verify that a final manuscript body is written in English."""
from __future__ import annotations

import argparse
import json
import re
import unicodedata
import zipfile
from pathlib import Path
from xml.etree import ElementTree


MIN_ENGLISH_WORDS = 200
MIN_LATIN_LETTER_RATIO = 0.98
MIN_ENGLISH_MARKER_RATIO = 0.02
MAX_MANUSCRIPT_BYTES = 10 * 1024 * 1024
CJK_RE = re.compile(
    "[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\u3040-\u30ff\uac00-\ud7af]"
)
WORD_RE = re.compile(r"[A-Za-z]+(?:['’-][A-Za-z]+)*")
ENGLISH_MARKERS = {
    "the", "and", "of", "to", "in", "for", "with", "that", "is", "are",
    "we", "our", "this", "from", "by", "as", "on", "was", "were", "which",
    "these", "between", "using", "results", "method", "study", "data", "model",
    "analysis", "however", "therefore", "because", "than", "into", "within",
}


def tex_text(
    path: Path,
    *,
    root: Path | None = None,
    seen: set[Path] | None = None,
) -> str:
    root = (root or path.parent).resolve()
    seen = seen if seen is not None else set()
    resolved = path.resolve()
    if resolved != root and root not in resolved.parents:
        raise ValueError("TeX include escapes the manuscript directory")
    if resolved in seen:
        return ""
    seen.add(resolved)
    if not resolved.is_file():
        raise ValueError(f"missing TeX include: {resolved.relative_to(root)}")
    if sum(item.stat().st_size for item in seen) > MAX_MANUSCRIPT_BYTES:
        raise ValueError("combined TeX manuscript exceeds the 10 MiB language-audit limit")
    text = resolved.read_text(encoding="utf-8")
    includes: list[str] = []
    for match in re.finditer(r"\\(?:input|include)\{([^}]+)\}", text):
        relative = Path(match.group(1))
        if not relative.suffix:
            relative = relative.with_suffix(".tex")
        includes.append(tex_text(root / relative, root=root, seen=seen))
    text = re.sub(r"(?m)(?<!\\)%.*$", " ", text)
    text = re.sub(r"\$\$.*?\$\$|\$.*?\$|\\\[.*?\\\]", " ", text, flags=re.S)
    text = re.sub(r"\\begin\{[^}]+\}|\\end\{[^}]+\}", " ", text)
    text = re.sub(r"\\[A-Za-z@]+\*?(?:\[[^\]]*\])?", " ", text)
    return text.replace("{", " ").replace("}", " ") + "\n" + "\n".join(includes)


def docx_text(path: Path) -> str:
    try:
        with zipfile.ZipFile(path) as archive:
            member = archive.getinfo("word/document.xml")
            if member.file_size > MAX_MANUSCRIPT_BYTES:
                raise ValueError("DOCX document XML exceeds the 10 MiB language-audit limit")
            payload = archive.read(member)
    except (OSError, KeyError, zipfile.BadZipFile) as exc:
        raise ValueError(f"cannot read DOCX manuscript: {exc}") from exc
    try:
        root = ElementTree.fromstring(payload)
    except ElementTree.ParseError as exc:
        raise ValueError(f"invalid DOCX document XML: {exc}") from exc
    return " ".join(node.text or "" for node in root.iter() if node.tag.endswith("}t"))


def extract_text(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".tex":
        return tex_text(path)
    if suffix == ".docx":
        return docx_text(path)
    raise ValueError("manuscript must be main.tex or main.docx")


def analyze(path: Path) -> dict[str, object]:
    text = extract_text(path)
    words = [word.lower() for word in WORD_RE.findall(text)]
    english_words = len(words)
    english_marker_ratio = (
        sum(word in ENGLISH_MARKERS for word in words) / english_words
        if english_words
        else 0.0
    )
    cjk_characters = len(CJK_RE.findall(text))
    letters = [character for character in text if character.isalpha()]
    latin_letters = sum(
        1 for character in letters if "LATIN" in unicodedata.name(character, "")
    )
    latin_ratio = latin_letters / len(letters) if letters else 0.0
    errors: list[str] = []
    if english_words < MIN_ENGLISH_WORDS:
        errors.append(
            f"manuscript has {english_words} English words; at least {MIN_ENGLISH_WORDS} are required for language validation"
        )
    if cjk_characters:
        errors.append(f"manuscript body contains {cjk_characters} CJK character(s)")
    if latin_ratio < MIN_LATIN_LETTER_RATIO:
        errors.append(
            f"Latin-letter ratio {latin_ratio:.3f} is below {MIN_LATIN_LETTER_RATIO:.2f}"
        )
    if english_marker_ratio < MIN_ENGLISH_MARKER_RATIO:
        errors.append(
            f"English marker-word ratio {english_marker_ratio:.3f} is below {MIN_ENGLISH_MARKER_RATIO:.2f}"
        )
    return {
        "schema_version": "1.0",
        "file": path.as_posix(),
        "declared_language": "en",
        "english_words": english_words,
        "cjk_characters": cjk_characters,
        "latin_letter_ratio": round(latin_ratio, 6),
        "english_marker_word_ratio": round(english_marker_ratio, 6),
        "status": "pass" if not errors else "fail",
        "errors": errors,
        "note": "This deterministic script checks script/language composition, not academic writing quality.",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("manuscript", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = analyze(args.manuscript)
    rendered = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
