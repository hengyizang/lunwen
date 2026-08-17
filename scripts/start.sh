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

if ! command -v claude >/dev/null 2>&1; then
  echo "Claude Code is not on PATH." >&2
  exit 2
fi

exec claude --plugin-dir "$repo_root" "/doctoral-research-os:start $project_slug $context"

