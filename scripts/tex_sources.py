"""Bounded TeX source expansion and submission dependencies; never runs TeX.

Expansion follows source order and keeps original locations. System packages are
left to the publisher toolchain; only explicit project-local dependencies enter
the closure. Dynamic TeX filenames require an explicit source edit, not guessing.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
import re

MAX_FILES = 200
MAX_BYTES = 10 * 1024 * 1024
INCLUDE = re.compile(r"\\(?:input|include|subfile)(?![A-Za-z@])\s*(?:\{([^{}]+)\}|([^\s{}%]+))")
DEPENDENCY = re.compile(r"\\(documentclass|LoadClass|usepackage|RequirePackage|bibliography|bibliographystyle|addbibresource|includegraphics|lstinputlisting|verbatiminput|pgfplotstableread)\*?(?:\s*\[[^\]]*\])*\s*\{([^{}]+)\}")
TEXT_SUFFIXES = {".tex", ".sty", ".cls", ".bst", ".cfg", ".def", ".clo"}
ASSET_SUFFIXES = {".pdf", ".png", ".jpg", ".jpeg", ".eps", ".svg", ".tif", ".tiff"}
SECRET_NAMES = {".env", "credentials.json", "secrets.json", "id_rsa", "id_ed25519"}


def comments(text: str) -> str:
    """Mask comments without moving source offsets or line numbers."""
    return _comments(text)


def _comments(text):
    chars = list(text)
    for match in re.finditer("%", text):
        prefix = text[:match.start()]
        backslashes = len(prefix) - len(prefix.rstrip("\\"))
        if backslashes % 2 == 0:
            end=text.find("\n",match.start())
            if end<0:end=len(text)
            chars[match.start():end] = " " * (end - match.start())
    return "".join(chars)


def safe_path(root: Path, path: Path, *, required=True) -> Path:
    root = root.resolve()
    raw = path if path.is_absolute() else root / path
    if any(p.is_symlink() for p in (raw, *raw.parents)):
        raise ValueError("TeX source/dependency cannot use a symlink")
    result = raw.resolve()
    if result == root or not result.is_relative_to(root):
        raise ValueError("TeX source/dependency escapes its allowed directory")
    relative = result.relative_to(root)
    if any(part.startswith(".") for part in relative.parts) or result.name.lower() in SECRET_NAMES or result.suffix.lower() in {".key", ".pem", ".p12", ".pfx"}:
        raise ValueError("Hidden or credential-like TeX dependency is forbidden")
    if required and not result.is_file():
        raise ValueError("Missing TeX source/dependency: " + relative.as_posix())
    return result


def _name(value: str) -> str:
    value = value.strip()
    if not value or any(c in value for c in ("\\", "\x00", ":", "#", "$", "~")) or Path(value).is_absolute():
        raise ValueError("TeX dependency needs a literal relative filename")
    return value


def _visible(text):
    masked = comments(text)
    for match in re.finditer(r"\\begin\{(verbatim\*?|lstlisting|minted)\}.*?\\end\{\1\}|\\verb\*?([^A-Za-z\s]).*?\2", masked, re.S):
        masked = masked[:match.start()] + re.sub(r"[^\n]", " ", match.group()) + masked[match.end():]
    return masked


@dataclass
class Expanded:
    text: str
    files: tuple[Path, ...]
    locations: list[dict]

    def locate(self, offset: int) -> dict:
        for row in self.locations:
            if row["start"] <= offset < row["end"]:
                return {"path": row["path"], "line": row["line"] + self.text[row["start"]:offset].count("\n")}
        raise ValueError("Expanded TeX location is outside the source map")


def expand(path: Path, *, root: Path | None = None) -> Expanded:
    root = (root or path.parent).resolve()
    files, chunks, locations = set(), [], []
    size = 0
    offset = 0
    def append(content, source, line):
        nonlocal offset, size
        if not content:
            return
        size += len(content.encode("utf-8"))
        if size > MAX_BYTES:
            raise ValueError("Expanded TeX manuscript exceeds 10 MiB")
        locations.append({"path": source.relative_to(root).as_posix(), "line": line, "start": offset, "end": offset + len(content)})
        chunks.append(content)
        offset += len(content)
    def visit(target, stack):
        target = safe_path(root, target)
        if target in stack:
            raise ValueError("Cyclic TeX include: " + target.relative_to(root).as_posix())
        files.add(target)
        if len(files) > MAX_FILES:
            raise ValueError("TeX manuscript includes more than 200 files")
        raw = target.read_text(encoding="utf-8")
        if target.stat().st_size > MAX_BYTES:
            raise ValueError("TeX source exceeds 10 MiB")
        text = _visible(raw)
        position = 0
        for match in INCLUDE.finditer(text):
            append(text[position:match.start()], target, text[:position].count("\n") + 1)
            name = _name(match.group(1) or match.group(2))
            relative = Path(name)
            if ".." in relative.parts:
                raise ValueError("TeX input traversal is forbidden")
            if not relative.suffix:
                relative = relative.with_suffix(".tex")
            if relative.suffix.lower() != ".tex":
                raise ValueError("TeX inputs must be .tex source files")
            visit(root / relative, stack + (target,))
            position = match.end()
        append(text[position:], target, text[:position].count("\n") + 1)
    visit(path, ())
    return Expanded("".join(chunks), tuple(sorted(files)), locations)


def dependencies(path: Path, *, paper: Path) -> list[Path]:
    """Exact local build closure; unrelated manuscript files are never copied."""
    paper = paper.resolve()
    working = path.parent.resolve()
    expanded = expand(path)
    found, pending = set(expanded.files), list(expanded.files)
    graphic_dirs = [working]
    while pending:
        source = pending.pop(0)
        text = _visible(source.read_text(encoding="utf-8"))
        for include in INCLUDE.finditer(text):
            name = _name(include.group(1) or include.group(2))
            if ".." in Path(name).parts:
                raise ValueError("TeX input traversal is forbidden")
            candidate = Path(name) if Path(name).suffix else Path(name).with_suffix(".tex")
            target = safe_path(paper, working / candidate, required=False)
            if not target.is_file():
                target = safe_path(paper, source.parent / candidate)
            if target not in found:
                found.add(target)
                if target.suffix.lower() in TEXT_SUFFIXES:
                    pending.append(target)
        for group in re.finditer(r"\\graphicspath\s*\{((?:\s*\{[^{}]+\}\s*)+)\}", text):
            for name in re.findall(r"\{([^{}]+)\}", group.group(1)):
                directory = safe_path(paper, working / _name(name), required=False)
                if directory not in graphic_dirs:
                    graphic_dirs.append(directory)
        for match in DEPENDENCY.finditer(text):
            command, value = match.groups()
            names = value.split(",") if command in {"usepackage", "RequirePackage", "bibliography"} else [value]
            for value in names:
                name = _name(value)
                suffixes = ({"documentclass": [".cls"], "LoadClass": [".cls"], "usepackage": [".sty"],
                             "RequirePackage": [".sty"], "bibliography": [".bib"], "bibliographystyle": [".bst"],
                             "addbibresource": [".bib"], "includegraphics": sorted(ASSET_SUFFIXES)}).get(command, [""])
                optional = command in {"documentclass", "LoadClass", "usepackage", "RequirePackage", "bibliographystyle"}
                base_dirs = graphic_dirs if command == "includegraphics" else [working, source.parent]
                candidates = []
                for base in base_dirs:
                    for suffix in ([""] if Path(name).suffix else suffixes):
                        candidate = safe_path(paper, base / (name + suffix), required=False)
                        if candidate.is_file() and candidate not in candidates:
                            candidates.append(candidate)
                if not candidates:
                    if optional and "/" not in name:
                        continue  # A standard package/class remains toolchain-owned.
                    raise ValueError("Missing explicit local TeX dependency: " + name)
                # A suffix-free graphic resolves by the declared graphics search
                # order. Preserve available variants so PDF/DVI engines can build.
                for target in candidates:
                    if target not in found:
                        found.add(target)
                        if target.suffix.lower() in TEXT_SUFFIXES:
                            nested = expand(target, root=working) if target.suffix.lower() == ".tex" else None
                            if nested:
                                for item in nested.files:
                                    if item not in found:
                                        found.add(item); pending.append(item)
                            pending.append(target)
        if len(found) > MAX_FILES or sum(item.stat().st_size for item in found) > 64 * 1024 * 1024:
            raise ValueError("TeX dependency closure exceeds 200 files or 64 MiB")
    return sorted(found, key=lambda p: p.relative_to(paper).as_posix())


def digest(path: Path) -> str:
    result = hashlib.sha256()
    for source in expand(path).files:
        result.update(source.relative_to(path.parent.resolve()).as_posix().encode())
        result.update(b"\0" + source.read_bytes() + b"\0")
    return result.hexdigest()
