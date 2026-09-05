"""Scoped user-handoff completion evidence for paused WebAgent runs."""

from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import re
from typing import Mapping


def handoff_expired(handoff: Mapping[str, object]) -> bool:
    try:
        expires_at = datetime.fromisoformat(str(handoff["expires_at"]))
    except (KeyError, TypeError, ValueError):
        return True
    if expires_at.tzinfo is None:
        return True
    return datetime.now(timezone.utc) >= expires_at


def record_handoff_completion(
    request: Mapping[str, object],
    directory: str | Path = ".agentshield/user-handoffs",
) -> Path:
    handoff_value = request.get("handoff")
    if not isinstance(handoff_value, Mapping):
        raise ValueError("用户接管请求缺少检查点")
    handoff = dict(handoff_value)
    handoff_id = str(handoff.get("handoff_id", ""))
    if not re.fullmatch(r"UH-[0-9a-f]{12}", handoff_id) or handoff_expired(handoff):
        raise ValueError("用户接管检查点无效或已过期")
    completion = {
        "handoff_id": handoff_id,
        "status": "COMPLETED_BY_USER",
        "action_sha256": handoff.get("action_sha256"),
        "recipient_sha256": handoff.get("recipient_sha256"),
        "rule_ids": list(handoff.get("rule_ids") or ()),
        "evidence_type": "USER_ATTESTATION",
        "attestation_sha256": sha256(
            f"{handoff_id}:COMPLETED_BY_USER".encode("utf-8")
        ).hexdigest(),
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }
    completion_directory = Path(directory)
    completion_directory.mkdir(parents=True, exist_ok=True)
    path = completion_directory / f"{handoff_id}.json"
    try:
        with path.open("x", encoding="utf-8") as stream:
            json.dump(completion, stream, ensure_ascii=False, indent=2)
    except FileExistsError as exc:
        raise ValueError("该用户接管检查点已经使用，不能重复继续") from exc
    return path


def handoff_resume_prompt(original_prompt: str, request: Mapping[str, object]) -> str:
    handoff_value = request.get("handoff")
    if not isinstance(handoff_value, Mapping):
        raise ValueError("用户接管请求缺少检查点")
    handoff = dict(handoff_value)
    original_prompt = str(request.get("original_prompt") or original_prompt)
    return (
        original_prompt
        + "\n\n[AgentShield 用户接管检查点] "
        + f"用户已亲自完成 {handoff.get('handoff_id')} 要求的敏感步骤。"
        + "不要再次请求、读取、填写或输出该步骤中的个人信息；只继续完成原任务剩余的非敏感步骤。"
    )
