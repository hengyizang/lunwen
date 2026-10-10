#!/usr/bin/env python3
"""Cloud-only deterministic builders for research quality improvements."""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

# Direct-file and module execution share the same package imports.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("notebook", "daily-brief", "statistics", "word-revision", "revision-ledger", "revision-ledger-manifest", "research-support", "support-sources", "review-packets", "journals", "method-contracts", "style-eval", "editorial-audit", "watermark-cleanup", "watermark-validate"))
    parser.add_argument("--project")
    parser.add_argument("--paper")
    parser.add_argument("--source", help="Exact project-relative manuscript source for Unicode cleanup")
    parser.add_argument("--expected-sha256", help="Reviewed current source SHA256")
    parser.add_argument("--receipt", help="Protected cleanup receipt to revalidate")
    args = parser.parse_args()
    if os.environ.get("GITHUB_ACTIONS") != "true" and os.environ.get("DR_OS_CLOUD_EXECUTOR") != "1":
        parser.error("builders must run in an authorized cloud executor; local research execution is disabled")
    if args.action == "style-eval":
        from scripts.style_evaluation import evaluate, repository_cases
        result = evaluate(repository_cases())
    else:
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]{1,62}", args.project or ""):
            parser.error("an initialized project slug is required")
        project = ROOT / "projects" / args.project
        if not project.is_dir() or project.is_symlink():
            parser.error("project is absent or unsafe")
        if args.action in {"statistics", "word-revision", "revision-ledger", "revision-ledger-manifest", "editorial-audit", "watermark-cleanup"} and not re.fullmatch(r"P[0-9]{2}", args.paper or ""):
            parser.error("paper must be P01, P02, etc.")
        if args.action == "editorial-audit":
            from scripts.academic_style import write_audit
            _, result = write_audit(project, args.paper)
        elif args.action == "watermark-cleanup":
            if not args.source or not args.expected_sha256:
                parser.error("watermark-cleanup requires --source and --expected-sha256")
            from scripts.watermark_cleanup import build
            result = build(project, args.paper, args.source, args.expected_sha256)
        elif args.action == "watermark-validate":
            if not args.receipt:
                parser.error("watermark-validate requires --receipt")
            from scripts.watermark_cleanup import validate_saved_report
            errors = validate_saved_report(project, args.receipt)
            result = {"status": "fail" if errors else "pass", "errors": errors}
        elif args.action == "notebook":
            from scripts.research_notebook import refresh
            result = refresh(project)
        elif args.action == "daily-brief":
            from scripts.research_notebook import daily_brief
            result = daily_brief(project)
        elif args.action == "revision-ledger":
            from scripts.revision_ledger import refresh
            result = refresh(project, args.paper)
        elif args.action == "revision-ledger-manifest":
            from scripts.revision_ledger import change_manifest
            result = change_manifest(project, args.paper)
        elif args.action == "research-support":
            from scripts.research_support import refresh
            result = refresh(project)
        elif args.action == "support-sources":
            from scripts.research_support import fetch_sources
            result = fetch_sources(project)
        elif args.action == "review-packets":
            from scripts.review_packets import refresh
            result = refresh(project)
        elif args.action == "statistics":
            from scripts.statistical_reporting import refresh
            result = refresh(project, args.paper)
        elif args.action == "word-revision":
            from scripts.docx_revision import build
            result = build(project, args.paper)
        elif args.action == "journals":
            from scripts.journal_dossier import refresh
            result = refresh(project)
        else:
            from scripts.method_tools import refresh
            result = refresh(project)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if result.get("status") in {"fail", "blocked", "revise"} else 0


if __name__ == "__main__":
    raise SystemExit(main())
