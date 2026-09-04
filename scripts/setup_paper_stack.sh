#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
AGENTSHIELD_PYTHON="${AGENTSHIELD_PYTHON:-python3.11}"
AWM_VENV="$PROJECT_ROOT/.venv-awm"

"$AGENTSHIELD_PYTHON" -m venv "$AWM_VENV"
"$AWM_VENV/bin/python" -m pip install --upgrade pip
"$AWM_VENV/bin/python" -m pip install -r "$PROJECT_ROOT/requirements-paper.txt"
NLTK_ALLOW_PROXIED_URLOPEN=1 "$AWM_VENV/bin/python" - <<PY
import nltk
directory = "$AWM_VENV/nltk_data"
for resource in ("punkt", "punkt_tab"):
    nltk.download(resource, download_dir=directory, quiet=True, raise_on_error=True)
PY
"$AWM_VENV/bin/playwright" install chromium

echo "AWM 隔离环境已安装：$AWM_VENV（AgentShield 代码由项目根目录直接加载）"
echo "下一步：部署 WebArena 站点、配置 URL 与 OPENAI_API_KEY，再运行 agentshield webarena status。"
