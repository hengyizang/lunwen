"""Extract a finite scalar from an exact, hash-bound result location."""
from __future__ import annotations

import csv
import json
import math
from pathlib import Path

from scripts.research_artifacts import path_in, sha


def extract(project: Path, binding: dict, *, outputs: set[tuple[str, str]] | None = None) -> float:
    if not isinstance(binding, dict):
        raise ValueError("numeric value needs a source path, hash and explicit selector")
    relative, digest = binding.get("path"), binding.get("sha256")
    path = path_in(project, relative)
    if not path.is_file() or sha(path) != digest:
        raise ValueError("numeric source is missing or its hash changed")
    if outputs is not None and (relative, digest) not in outputs:
        raise ValueError("numeric source was not produced by the selected attempts")
    if path.stat().st_size > 16 * 1024 * 1024:
        raise ValueError("numeric source exceeds the bounded result-reader size")
    selector = binding.get("selector")
    if not isinstance(selector, dict):
        raise ValueError("numeric source needs an explicit selector")
    if set(selector) == {"json_pointer"}:
        pointer = selector["json_pointer"]
        if not isinstance(pointer, str) or (pointer and not pointer.startswith("/")):
            raise ValueError("use an RFC 6901 JSON pointer")
        value = json.loads(path.read_text(encoding="utf-8"))
        for part in pointer.split("/")[1:] if pointer else []:
            part = part.replace("~1", "/").replace("~0", "~")
            if isinstance(value, list) and part.isdigit():
                value = value[int(part)]
            elif isinstance(value, dict) and part in value:
                value = value[part]
            else:
                raise ValueError("numeric JSON pointer does not locate a value")
        if type(value) not in (int, float):
            raise ValueError("numeric JSON pointer must locate a number")
    elif set(selector) == {"column", "row"}:
        row_key, column = selector["row"], selector["column"]
        if not isinstance(row_key, dict) or not row_key or not isinstance(column, str):
            raise ValueError("CSV selector needs a column and unique row key")
        with path.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle, delimiter="\t" if path.suffix.lower() == ".tsv" else ",")
            if (not reader.fieldnames or len(set(reader.fieldnames)) != len(reader.fieldnames)
                    or not {column, *row_key} <= set(reader.fieldnames)):
                raise ValueError("CSV numeric selector names missing or duplicate columns")
            rows = [row for row in reader if all(row.get(k) == str(v) for k, v in row_key.items())]
        if len(rows) != 1 or None in rows[0]:
            raise ValueError("CSV numeric selector must locate exactly one well-formed row")
        value = float(rows[0][column])
    elif set(selector) == {"line", "numeric_token"}:
        from scripts.scientific_numbers import TOKEN
        line, index = selector["line"], selector["numeric_token"]
        lines = path.read_text(encoding="utf-8").splitlines()
        if type(line) is not int or type(index) is not int or not 1 <= line <= len(lines) or index < 0:
            raise ValueError("text selector needs a 1-based line and 0-based numeric token")
        tokens = list(TOKEN.finditer(lines[line-1]))
        if index >= len(tokens):
            raise ValueError("numeric text token is absent")
        value = float(tokens[index].group().replace("−", "-"))
    else:
        raise ValueError("unsupported numeric selector; use JSON pointer, CSV row/column, or text line/token")
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError("numeric source must contain a finite number")
    return float(value)
