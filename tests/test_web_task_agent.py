from __future__ import annotations

from dashboard.demo_loader import run_demo


def test_suitecrm_web_task_is_repaired_before_the_controlled_action():
    session = run_demo(
        "gdpr",
        task_prompt="请在 CRM 中处理客户联系人。",
        regulations=("GDPR",),
        web_task=True,
    )
    try:
        assert session.web_environment == "suitecrm"
        assert session.result["web_actions"] == 1
        assert session.result["repair_transactions"] == 1
        assert session.result["authorized_repair_children"] == 1
        assert session.result["raw_pii_messages"] == 0
        capabilities = {
            event.details.get("capability_id")
            for event in session.snapshot.events
            if event.event_type == "CAPABILITY_REQUEST"
        }
        assert {"web.page.read", "web.action.submit", "response.release"} <= capabilities
        assert any(
            event.details.get("shielding_plan", {}).get("circuits")
            for event in session.snapshot.events
        )
    finally:
        session.close()


def test_shopping_prompt_uses_the_matching_local_webarena_style_scene():
    session = run_demo(
        "gdpr",
        task_prompt="在购物网站中查找人体工学键盘。",
        regulations=("GDPR",),
        web_task=True,
    )
    try:
        assert session.web_environment == "shopping"
        assert session.result["web_actions"] == 1
        assert session.result["repair_transactions"] == 0
    finally:
        session.close()
