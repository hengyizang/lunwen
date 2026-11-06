"""Generate checkout-local discovery entries from the authoritative native skills."""
from pathlib import Path
import re

from scripts.research_artifacts import path_in


def entry(root: Path, name: str) -> str:
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", name):
        raise ValueError("invalid native skill name")
    source = f"skills/{name}/SKILL.md"
    text = path_in(root, source).read_text(encoding="utf-8")
    if not text.startswith("---\n") or "\n---\n" not in text[4:]:
        raise ValueError("native skill needs frontmatter")
    fields = text.split("---", 2)[1].splitlines()
    metadata = [line for key in ("name", "description") for line in fields if line.startswith(key + ":")]
    if len(metadata) != 2:
        raise ValueError("native skill needs a name and description")
    return ("---\n" + "\n".join(metadata) + "\n---\n\n"
            f"Read the repository-root `{source}` and follow its complete current instructions. "
            "This entry is generated; edit the source skill.\n")


def install(root: Path, name: str) -> None:
    expected = entry(root, name)
    target = path_in(root, f".agents/skills/{name}/SKILL.md", exists=False)
    if target.parent.exists():
        if any(p.is_symlink() or (p.is_file() and p != target) for p in target.parent.rglob("*")):
            raise ValueError("Preserve changed discovery entry before reinstalling: " + name)
        # Migrate only an exact historical copy of the authoritative source.
        if target.exists() and target.read_text(encoding="utf-8") not in {
                expected, path_in(root, f"skills/{name}/SKILL.md").read_text(encoding="utf-8")}:
            raise ValueError("Preserve changed discovery entry before reinstalling: " + name)
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.is_file() or target.read_text(encoding="utf-8") != expected:
        target.write_text(expected, encoding="utf-8")


def current(root: Path, name: str) -> bool:
    target = path_in(root, f".agents/skills/{name}/SKILL.md", exists=False)
    return target.is_file() and target.read_text(encoding="utf-8") == entry(root, name)
