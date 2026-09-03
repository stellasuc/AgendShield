#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "$0")/.." && pwd)"
demo_root="$(mktemp -d "${TMPDIR:-/tmp}/agentshield-idempotency.XXXXXX")"
trap 'rm -rf "$demo_root"' EXIT

cd "$project_root"
runner="${AGENTSHIELD_BIN:-$project_root/.venv/bin/agentshield}"

echo "AgentShield | Agent Retry / Broker Restart Protection"
echo "Isolated database: $demo_root/runtime.db"
echo "The same effect_id is submitted before and after broker restart."
echo
"$runner" demo idempotency --db "$demo_root/runtime.db"
echo
echo "Expected invariant: retry=IDEMPOTENT_REPLAY, backend executions=1."
echo "Optional recording: asciinema rec -c '$0' idempotency-demo.cast"
