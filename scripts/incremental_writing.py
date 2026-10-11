"""Current-source argument coverage and bounded, authorized scientific editing."""
from __future__ import annotations

import re
from pathlib import Path

from scripts.incremental_evidence import binding, digest, identifier, rows, strings, text
from scripts.research_artifacts import path_in, read, sha, write, record

ROOT = "reports/research-increments"


def paper_path(project, paper_id):
    if not isinstance(paper_id, str) or not re.fullmatch(r"P[0-9]{2}", paper_id):
        raise ValueError("paper_id must be P01, P02, etc.")
    paper = project / "papers" / paper_id
    if not paper.is_dir() or paper.is_symlink():
        raise ValueError("paper does not belong to this project")
    return paper


def inventory(project: Path, paper_id: str) -> dict:
    """Enumerate source paragraphs in traversal order, without claiming PDF layout."""
    from scripts.ref_verify_adapter import canonical_manuscript
    from scripts.citation_audit import manuscript_digest
    canonical = canonical_manuscript(paper_path(project, paper_id))
    units, sources = [], {}
    if canonical.suffix == ".docx":
        from scripts.revision_ledger import source_snapshot
        snapshot = source_snapshot(project, canonical)
        sources = {row["path"]: row["sha256"] for row in snapshot["sources"]}
        for row in snapshot["units"]:
            if row["kind"] != "docx-paragraph" or not row["text"].strip():
                continue
            units.append({"path": row["path"], "location": row["location"],
                          "text": row["text"], "sha256": digest(row["text"])})
    else:
        active, count = set(), [0]

        def visit(source, top=False):
            source = path_in(project, source.relative_to(project).as_posix())
            if source in active:
                raise ValueError("cyclic TeX includes are unsupported")
            count[0] += 1
            if count[0] > 200 or source.stat().st_size > 4_000_000:
                raise ValueError("TeX argument inventory exceeds its bounded scope")
            content = source.read_text(encoding="utf-8")
            if r"\includeonly" in content:
                raise ValueError("includeonly needs an explicit canonical source export")
            offset = 0
            if top and r"\begin{document}" in content:
                offset = content.index(r"\begin{document}") + len(r"\begin{document}")
                content = content[offset:]
            if r"\end{document}" in content:
                content = content[:content.index(r"\end{document}")]
            sources[source.relative_to(project).as_posix()] = sha(source)
            active.add(source)
            # Includes must occupy a source line; inline/dynamic expansion is not guessed.
            pieces = re.split(r"(?m)^([ \t]*\\(?:input|include)\{[^{}\n]+\}[ \t]*(?:%[^\n]*)?$)", content)
            position = offset
            for piece in pieces:
                include = re.fullmatch(r"[ \t]*\\(?:input|include)\{([^{}\n]+)\}[ \t]*(?:%[^\n]*)?", piece)
                if include:
                    name = include.group(1)
                    if not re.fullmatch(r"[A-Za-z0-9_./-]+", name) or ".." in Path(name).parts:
                        raise ValueError("dynamic or parent TeX include is unsupported")
                    target = source.parent / name
                    if not target.suffix:
                        target = target.with_suffix(".tex")
                    visit(target)
                else:
                    if re.search(r"\\(?:input|include)\b", piece):
                        raise ValueError("inline TeX includes need a source paragraph export")
                    for match in re.finditer(r"\S[\s\S]*?(?=\n[ \t]*\n|\Z)", piece):
                        raw = match.group()
                        visible = re.sub(r"(?m)(?<!\\)%.*$", "", raw).strip()
                        if visible:
                            units.append({"path": source.relative_to(project).as_posix(),
                                          "location": f"characters:{position + match.start()}:{position + match.end()}",
                                          "text": visible, "sha256": digest(visible)})
                position += len(piece)
            active.remove(source)
        visit(canonical, True)
    occurrences = {}
    for index, unit in enumerate(units, 1):
        key = (unit["path"], unit["location"])
        occurrences[key] = occurrences.get(key, 0) + 1
        unit.update({"order": index, "occurrence": occurrences[key]})
        unit["unit_id"] = digest({key: unit[key] for key in ("path", "location", "occurrence")})[:24]
    if not units:
        raise ValueError("canonical manuscript contains no source paragraphs")
    return {"paper_id": paper_id, "canonical_sha256": manuscript_digest(canonical),
            "sources": [{"path": p, "sha256": h} for p, h in sorted(sources.items())],
            "units": units, "scope": "source_paragraphs_in_traversal_order",
            "rendered_pagination_verified": False}


def concept(row):
    """Bindings may be refreshed after writing; the planned argument may not be replaced."""
    return {"paper_id": row.get("paper_id"),
            "paragraphs": [{k: v for k, v in item.items() if k != "units"}
                           for item in rows(row.get("paragraphs"), "argument paragraphs", minimum=1)],
            "precedence": row.get("precedence", [])}


def freeze_plan(project, row, *, phase="review_checkpoint"):
    key = identifier(row.get("id"))
    if phase not in {"before_writer", "review_checkpoint"}:
        raise ValueError("invalid argument freeze phase")
    target = project / ROOT / "argument-plans" / (key + ".json")
    spec = concept(row)
    current = read(target) if target.is_file() else {}
    if current.get("concept_sha256") == digest(spec) and current.get("phase") == "before_writer":
        return current  # Preserve the genuine first pre-write receipt.
    try:
        before = inventory(project, row["paper_id"])
    except (ValueError, OSError, KeyError, RuntimeError):
        before = {"status": "not_yet_available"}
    result = {"schema_version": "1.0", "id": key, "concept_sha256": digest(spec),
              "plan": spec, "phase": phase, "before": before,
              "scientific_completion_verified": False}
    archive = project / ROOT / "argument-plan-history" / (key + "-" + digest(result) + ".json")
    if not archive.is_file():
        write(archive, result)
        record(project, [archive], "incremental-writing-freeze")
    write(target, result)
    record(project, [target], "incremental-writing-freeze")
    return result


def arguments(project, row):
    from scripts import output_provenance
    key = identifier(row.get("id"))
    current = inventory(project, row.get("paper_id"))
    facts = read(paper_path(project, row["paper_id"]) / "reviews/paper-facts.json")
    fact_ids = {item["id"] for item in facts.get("facts", [])}
    by_unit = {item["unit_id"]: item for item in current["units"]}
    covered, outlines, paragraph_ids = set(), [], set()
    for item in rows(row.get("paragraphs"), "argument paragraphs", minimum=1):
        pid = identifier(item.get("paragraph_id"), "paragraph_id")
        if pid in paragraph_ids:
            raise ValueError("duplicate argument paragraph_id")
        paragraph_ids.add(pid)
        function = item.get("function")
        if function not in {"context", "gap", "question", "method", "result", "interpretation",
                            "limitation", "transition", "non_argument"}:
            raise ValueError("unknown paragraph argument function")
        for field in ("section", "purpose", "inference_boundary", "transition"):
            text(item.get(field), field)
        claims = strings(item.get("claim_ids"), "claim_ids")
        if set(claims) - fact_ids:
            raise ValueError("argument claim is absent from current paper facts")
        if function not in {"context", "transition", "non_argument"} and not claims:
            raise ValueError("scientific argument paragraphs must link current paper fact IDs")
        if function == "non_argument":
            text(item.get("exclusion_reason"), "explicit non-argument reason")
        evidence = rows(item.get("evidence", []), "argument evidence", maximum=30)
        from scripts.incremental_evidence import anchors
        if function in {"result", "interpretation", "gap"} and not evidence:
            raise ValueError("result, interpretation and gap paragraphs need source anchors")
        checked = anchors(project, evidence, minimum=0)
        orders, excerpts = [], []
        for linked in rows(item.get("units"), "current paragraph units", maximum=100, minimum=1):
            uid = linked.get("unit_id")
            if uid not in by_unit or uid in covered:
                raise ValueError("missing, duplicate or stale argument source unit")
            unit = by_unit[uid]
            if linked.get("sha256") != unit["sha256"]:
                raise ValueError("argument paragraph text changed; refresh its exact binding")
            covered.add(uid)
            orders.append(unit["order"])
            excerpts.append(unit["text"])
        if sorted(orders) != list(range(min(orders), max(orders) + 1)):
            raise ValueError("one paragraph plan cannot hide noncontiguous arguments")
        outlines.append({"paragraph_id": pid, "section": item["section"], "function": function,
                         "purpose": item["purpose"], "claim_ids": claims, "evidence": checked,
                         "order": min(orders), "text": "\n".join(excerpts),
                         "inference_boundary": item["inference_boundary"]})
    if covered != set(by_unit):
        raise ValueError("argument ledger does not cover every current source paragraph")
    order_map = {item["paragraph_id"]: item["order"] for item in outlines}
    for edge in rows(row.get("precedence", []), "argument precedence"):
        if edge.get("before") not in order_map or edge.get("after") not in order_map:
            raise ValueError("argument precedence refers to an absent paragraph")
        if order_map[edge["before"]] >= order_map[edge["after"]]:
            raise ValueError("argument dependency appears after the paragraph that needs it")
    frozen = path_in(project, f"{ROOT}/argument-plans/{key}.json")
    receipt = read(frozen)
    origin = output_provenance.current_origin(project, frozen)
    if (receipt.get("phase") != "before_writer" or receipt.get("concept_sha256") != digest(concept(row))
            or origin.get("status") != "tracked" or origin.get("provider") != "deterministic-control-plane"):
        raise ValueError("current argument requires a genuine pre-write frozen plan")
    return {"id": key, "paper_id": row["paper_id"], "inventory": current,
            "reverse_outline": sorted(outlines, key=lambda item: item["order"]),
            "paragraph_coverage": "complete", "semantic_support_verified": False}


def voice(project, row, confirmation):
    key = identifier(row.get("id"))
    for field in ("language", "genre", "authorized_use", "owner"):
        text(row.get(field), field, 1000)
    if row["authorized_use"] != "style_reference_only":
        raise ValueError("author samples may only guide style, never supply research evidence")
    sample = binding(project, row.get("sample"))
    if sample["path"].startswith(("state/", ROOT + "/")):
        raise ValueError("an authorization receipt cannot be its own author sample")
    content = path_in(project, sample["path"]).read_text(encoding="utf-8")
    if not 100 <= len(content) <= 100_000:
        raise ValueError("author sample must contain 100-100000 readable characters")
    if not confirmation(project, "voice", key, row, "authorize_sample"):
        raise ValueError("author sample needs a current owner authorization for this scope and hash")
    return {"id": key, **sample, "language": row["language"], "genre": row["genre"],
            "use": "style_reference_only", "human_authorship_verified": False}


def editing(project, row, voices):
    """Recommend the least justified edit; do not create additional paid passes."""
    identifier(row.get("id"))
    paper_path(project, row.get("paper_id"))
    if row.get("purpose") not in {"clarity", "language", "structure", "scientific_correction"}:
        raise ValueError("editing purpose must be explicit")
    for field in ("language", "genre"):
        text(row.get(field), field, 1000)
    issues = strings(row.get("issue_ids"), "issue_ids")
    evidence = [binding(project, item) for item in rows(row.get("evidence"), "editing evidence")]
    strength = ("substantive" if row["purpose"] == "scientific_correction"
                else "local" if row["purpose"] == "structure" else "minimal")
    if strength == "substantive" and not evidence:
        raise ValueError("scientific correction requires new bound evidence")
    selected = row.get("voice_id")
    sample_status = "not_requested"
    if selected:
        matched = [item for item in voices if item["id"] == selected]
        if len(matched) != 1 or any(matched[0][k] != row[k] for k in ("language", "genre")):
            raise ValueError("author voice is absent, unauthorized or outside language/genre scope")
        sample_status = "authorized_style_reference"
    fingerprint = digest({"issues": issues, "evidence": evidence, "purpose": row["purpose"],
                          "language": row["language"], "genre": row["genre"], "voice": selected})
    history = project / ROOT / "editing-history" / (row["id"] + ".json")
    old = read(history) if history.is_file() else {}
    unchanged = old.get("fingerprint") == fingerprint
    return {"id": row["id"], "paper_id": row["paper_id"], "fingerprint": fingerprint,
            "edit_strength": strength, "sample_status": sample_status,
            "stop_repeated_editorial_rework": unchanged and row["purpose"] != "scientific_correction",
            "stop_scope": "optional_style_only; scientific blockers and independent audits remain",
            "protected": ["facts", "citations", "uncertainty", "technical_terms", "AI_disclosure"],
            "additional_model_calls": 0}
