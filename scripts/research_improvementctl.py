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
    parser.add_argument("action", choices=("notebook", "statistics", "word-revision", "journals", "method-contracts", "style-eval"))
    parser.add_argument("--project")
    parser.add_argument("--paper")
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
        if args.action in {"statistics", "word-revision"} and not re.fullmatch(r"P[0-9]{2}", args.paper or ""):
            parser.error("paper must be P01, P02, etc.")
        if args.action == "notebook":
            from scripts.research_notebook import refresh
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
    return 1 if result.get("status") in {"fail", "blocked"} else 0


if __name__ == "__main__":
    raise SystemExit(main())
