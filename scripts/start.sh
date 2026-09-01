#!/usr/bin/env bash
set -euo pipefail

mode="api"
if [[ "${1:-}" == "--cli" ]]; then
  mode="cli"
  shift
fi
if [[ "$#" -lt 1 ]]; then
  echo "Usage: bash scripts/start.sh [--cli] <project-slug> [goal and constraints]" >&2
  exit 2
fi

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
project_slug="$1"
shift
context="$*"
cd "$repo_root"

if [[ "$mode" == "cli" ]]; then
  exec python3 scripts/autopilot.py start --project "$project_slug" --context "$context"
fi

if [[ -e "projects/$project_slug" ]]; then
  echo "Project already exists; use api_orchestrator.py cycle with its current stage." >&2
  exit 2
fi
python3 scripts/researchctl.py init --project "$project_slug" --paper-count 6
exec python3 scripts/api_orchestrator.py cycle "$project_slug" intake \
  --planner-provider uuapi-anthropic \
  --writer-provider uuapi-openai \
  --critic-provider uuapi-anthropic \
  --context "$context"
