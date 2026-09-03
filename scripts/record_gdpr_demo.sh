#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "$0")/.." && pwd)"
demo_root="$(mktemp -d "${TMPDIR:-/tmp}/agentshield-gdpr.XXXXXX")"
trap 'rm -rf "$demo_root"' EXIT

cd "$project_root"
runner="${AGENTSHIELD_BIN:-$project_root/.venv/bin/agentshield}"

echo "AgentShield | GDPR Personal Data Exfiltration Prevention"
echo "Isolated database: $demo_root/runtime.db"
echo "Request: count EU customers and send only the statistics externally."
echo
"$runner" demo gdpr --db "$demo_root/runtime.db"
echo
echo "Expected invariant: raw_pii_messages=0, aggregate_messages=1."
echo "Optional recording: asciinema rec -c '$0' gdpr-demo.cast"
