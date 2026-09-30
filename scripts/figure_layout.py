#!/usr/bin/env python3
"""Pinned Nature figure alignment and final-PDF collision adapter."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

try:
    from scripts.research_methods import load_vendored_module, safe_path, sha256
except ImportError:
    from research_methods import load_vendored_module, safe_path, sha256

ALIGNMENT = "third_party/nature-figure/scripts/audit_panel_alignment.py"
COLLISIONS = "third_party/nature-figure/scripts/audit_figure_collisions.py"


def inspect_panels(fig: Any) -> dict[str, Any]:
    helper = load_vendored_module(ALIGNMENT)
    manifest = helper.matplotlib_layout_manifest(fig)
    report = helper.audit_layout_manifest(manifest)
    return {"manifest": manifest, "report": report, "pass": helper.exit_code(report) == 0}


def inspect_pdf(pdf: Path) -> dict[str, Any]:
    helper = load_vendored_module(COLLISIONS)
    try:
        report = helper.audit_pdf(pdf)
        report["pdf"] = pdf.name
        return {"report": report, "pass": helper.exit_code(report) == 0}
    except (ImportError, OSError, RuntimeError, ValueError) as exc:
        return {"report": {"auditable": False, "verdict": "NOT AUDITABLE", "error": str(exc)},
                "pass": False}


def save_audit(project: Path, pdf: Path, output: Path,
               alignment: dict[str, Any]) -> dict[str, Any]:
    collision = inspect_pdf(pdf)
    payload = {"schema_version": "1.0", "pdf": pdf.relative_to(project).as_posix(),
               "pdf_sha256": sha256(pdf), "alignment": alignment, "collision": collision,
               "pass": alignment["pass"] and collision["pass"],
               "human_visual_review_required": True}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2) + "\n")
    try:
        from scripts import output_provenance
    except ImportError:
        import output_provenance
    output_provenance.record_model_writes(
        project, [output], family="other", provider="deterministic-figure-layout",
        model="scripts/figure_layout.py", role="figure-layout-auditor", run_id="figure-layout",
    )
    return {"path": output.relative_to(project).as_posix(), "sha256": sha256(output),
            "pass": payload["pass"], "collision_verdict": collision["report"]["verdict"]}


def validate_saved_figures(paper: Path) -> list[str]:
    """Recompute geometry checks; never accept a writer's PASS flag."""
    project = paper.parent.parent
    errors: list[str] = []
    try:
        from scripts.publication_figures import validate_spec
    except ImportError:
        from publication_figures import validate_spec
    for spec in sorted((paper / "figures").rglob("*.spec.json")):
        try:
            value = json.loads(spec.read_text(encoding="utf-8"))
            validate_spec(value)
            stem = safe_path(project, value.get("output_stem"))
            if not stem.resolve().is_relative_to((paper / "figures").resolve()):
                raise ValueError("figure output must belong to this paper")
            build_path = stem.with_suffix(".figure-build.json")
            if not build_path.is_file():
                raise ValueError("native spec has no rendered build and layout audit")
            build = json.loads(build_path.read_text())
            if (build.get("renderer") != "scripts/publication_figures.py" or
                    build.get("spec", {}).get("path") != spec.relative_to(project).as_posix()):
                raise ValueError("native spec does not match its declared renderer/build")
        except (OSError, ValueError, KeyError, TypeError, AttributeError, RuntimeError) as exc:
            errors.append(f"{spec.name}: unrendered or invalid native spec: {exc}")
    for build_path in sorted((paper / "figures").rglob("*.figure-build.json")):
        try:
            try:
                from scripts import output_provenance
            except ImportError:
                import output_provenance
            build = json.loads(build_path.read_text())
            if build.get("renderer") != "scripts/publication_figures.py":
                continue
            if build.get("renderer_sha256") != sha256(Path(__file__).with_name("publication_figures.py")):
                errors.append(f"{build_path.name}: renderer changed; rebuild the figure")
            for row in [build["spec"], *build["data"], *build["outputs"]]:
                source = safe_path(project, row["path"])
                if not source.is_file() or sha256(source) != row.get("sha256"):
                    errors.append(f"{build_path.name}: figure input/output is missing or stale: {row['path']}")
            record = build.get("quality", {}).get("layout_audit")
            if not isinstance(record, dict):
                errors.append(f"{build_path.name}: current rendered layout audit is required")
                continue
            audit_path = safe_path(project, record["path"])
            for path, provider in ((build_path, "deterministic-local-renderer"),
                                   (audit_path, "deterministic-figure-layout")):
                origin = output_provenance.current_origin(project, path)
                if (origin.get("status") != "tracked" or origin.get("family") != "other" or
                        origin.get("provider") != provider):
                    errors.append(f"{build_path.name}: layout/build report lacks current control provenance")
            if sha256(audit_path) != record["sha256"]:
                errors.append(f"{build_path.name}: layout audit hash is stale")
                continue
            payload = json.loads(audit_path.read_text())
            pdf = safe_path(project, payload["pdf"])
            if sha256(pdf) != payload.get("pdf_sha256"):
                errors.append(f"{build_path.name}: audited PDF is stale")
            helper = load_vendored_module(ALIGNMENT)
            alignment = payload["alignment"]
            replay = helper.audit_layout_manifest(alignment["manifest"])
            if replay != alignment["report"] or helper.exit_code(replay):
                errors.append(f"{build_path.name}: panel alignment failed or changed")
            current_collision = inspect_pdf(pdf)
            if current_collision != payload.get("collision") or not current_collision["pass"]:
                errors.append(f"{build_path.name}: collision audit failed or changed")
            if payload.get("pass") is not True or record.get("pass") is not True:
                errors.append(f"{build_path.name}: rendered figure is not mechanically passed")
        except (OSError, ValueError, KeyError, TypeError, RuntimeError, AttributeError) as exc:
            errors.append(f"{build_path.name}: cannot replay figure layout: {exc}")
    return errors


def refresh_native_figures(paper: Path) -> dict[str, Any]:
    """Render declarative native specs after writing, outside model authority."""
    project = paper.parent.parent
    try:
        from scripts.publication_figures import render
    except ImportError:
        from publication_figures import render
    outputs, errors = [], []
    for spec in sorted((paper / "figures").rglob("*.spec.json")):
        try:
            value = json.loads(spec.read_text(encoding="utf-8"))
            if not isinstance(value, dict):
                raise ValueError("native figure spec must be an object")
            stem = safe_path(project, value.get("output_stem"))
            if not stem.resolve().is_relative_to((paper / "figures").resolve()):
                raise ValueError("figure output must belong to the active paper")
            report = render(project, spec)
            outputs.append({"spec": spec.relative_to(project).as_posix(),
                            "layout_audit": report["quality"]["layout_audit"]})
        except (OSError, ValueError, KeyError, TypeError, RuntimeError) as exc:
            errors.append(f"{spec.relative_to(project)}: {exc}")
    return {"outputs": outputs, "errors": errors, "pass": not errors,
            "human_visual_review_required": True}
