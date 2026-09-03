#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "$0")/.." && pwd)"
demo="${1:-gdpr}"

case "$demo" in
  gdpr|pipl|idempotency)
    exec "$project_root/scripts/record_${demo}_demo.sh"
    ;;
  *)
    echo "Usage: $0 [gdpr|pipl|idempotency]" >&2
    exit 2
    ;;
esac
