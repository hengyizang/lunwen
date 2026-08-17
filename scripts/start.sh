#!/usr/bin/env bash
set -euo pipefail

if [[ "$#" -lt 1 ]]; then
  echo "Usage: bash scripts/start.sh <project-slug> [goal and constraints]" >&2
  exit 2
fi

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
project_slug="$1"
shift
context="$*"
cd "$repo_root"

exec python3 scripts/autopilot.py start --project "$project_slug" --context "$context"
