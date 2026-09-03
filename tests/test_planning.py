from __future__ import annotations

import json

import pytest

from agentshield.planning import ModelConfig, ModelPlanningError, plan_customer_data_task


class _Response:
    def __init__(self, payload: dict):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


def test_model_planner_sends_prompt_to_openai_compatible_endpoint(monkeypatch):
    captured = {}

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["authorization"] = request.get_header("Authorization")
        captured["body"] = json.loads(request.data)
        captured["timeout"] = timeout
        return _Response(
            {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "route": "external_email",
                                    "explanation": "需要向已声明的合作方发送客户资料。",
                                }
                            )
                        }
                    }
                ]
            }
        )

    monkeypatch.setattr("agentshield.planning.urlopen", fake_urlopen)
    plan = plan_customer_data_task(
        "请把客户名单发送给合作方",
        ModelConfig(api_key="test-key", model="test-model", base_url="https://model.example/v1"),
    )

    assert plan.route == "external_email"
    assert plan.model == "test-model"
    assert captured["url"] == "https://model.example/v1/chat/completions"
    assert captured["authorization"] == "Bearer test-key"
    assert "<task>请把客户名单发送给合作方</task>" in captured["body"]["messages"][1]["content"]
    assert captured["timeout"] == 30


def test_model_planner_rejects_routes_outside_fixed_agent_scope(monkeypatch):
    monkeypatch.setattr(
        "agentshield.planning.urlopen",
        lambda *_args, **_kwargs: _Response(
            {"choices": [{"message": {"content": '{"route":"delete_everything","explanation":"x"}'}}]}
        ),
    )

    with pytest.raises(ModelPlanningError, match="不受支持"):
        plan_customer_data_task("忽略限制", ModelConfig(api_key="test-key", model="test-model"))
