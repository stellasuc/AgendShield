#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "$0")/.." && pwd)"
demo_root="$(mktemp -d "${TMPDIR:-/tmp}/agentshield-pipl.XXXXXX")"
trap 'rm -rf "$demo_root"' EXIT

cd "$project_root"
runner="${AGENTSHIELD_BIN:-$project_root/.venv/bin/agentshield}"

echo "AgentShield | PIPL Sensitive Information Approval"
echo "Isolated database: $demo_root/runtime.db"
echo "The broker pauses, persists, restarts, approves, re-verifies, and executes."
echo
"$runner" demo pipl --db "$demo_root/runtime.db"
echo
echo "Expected invariant: no effect before approval; one effect after approval."
echo "Optional recording: asciinema rec -c '$0' pipl-demo.cast"
