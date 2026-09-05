from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json

import pytest

from agentshield.integrations.user_handoff import (
    handoff_expired,
    handoff_resume_prompt,
    record_handoff_completion,
)


def _request(*, expires_delta: timedelta = timedelta(minutes=10)) -> dict[str, object]:
    return {
        "original_prompt": "填写测试客户邮箱 alice@example.com，然后继续浏览商品。",
        "handoff": {
            "handoff_id": "UH-123456789abc",
            "status": "PENDING_USER",
            "action_sha256": "a" * 64,
            "recipient_sha256": "b" * 64,
            "rule_ids": ["GDPR_LAWFUL_BASIS_001"],
            "expires_at": (datetime.now(timezone.utc) + expires_delta).isoformat(),
        },
    }


def test_handoff_completion_is_scoped_payload_minimized_and_single_use(tmp_path):
    request = _request()

    path = record_handoff_completion(request, tmp_path)
    payload = json.loads(path.read_text(encoding="utf-8"))

    assert payload["status"] == "COMPLETED_BY_USER"
    assert payload["action_sha256"] == "a" * 64
    assert "alice@example.com" not in path.read_text(encoding="utf-8")
    with pytest.raises(ValueError, match="已经使用"):
        record_handoff_completion(request, tmp_path)


def test_expired_or_malformed_handoff_cannot_continue(tmp_path):
    expired = _request(expires_delta=timedelta(seconds=-1))
    assert handoff_expired(expired["handoff"]) is True
    with pytest.raises(ValueError, match="无效或已过期"):
        record_handoff_completion(expired, tmp_path)

    malformed = _request()
    malformed["handoff"]["handoff_id"] = "UH-../../escape"
    with pytest.raises(ValueError, match="无效或已过期"):
        record_handoff_completion(malformed, tmp_path)


def test_resume_prompt_prohibits_reprocessing_user_handled_data():
    prompt = handoff_resume_prompt("fallback", _request())

    assert "UH-123456789abc" in prompt
    assert "不要再次请求、读取、填写或输出" in prompt
    assert prompt.startswith("填写测试客户邮箱")
