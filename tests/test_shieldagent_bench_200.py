"""Executable 200-case regression suite for the current BrowserGym guard."""

from __future__ import annotations

import pytest

from agentshield.integrations.browsergym import BrowserGymActionGuard
from tests.fixtures.shieldagent_bench_200_cases import build_cases


CASES = build_cases()


def test_shieldagent_bench_200_distribution_and_scope():
    assert len(CASES) == 200
    assert sum(case.expected_allowed for case in CASES) == 40
    assert sum(not case.expected_allowed for case in CASES) == 160
    assert {case.environment for case in CASES} == {
        "shopping", "cms", "reddit", "gitlab", "maps", "suitecrm",
    }


@pytest.mark.parametrize("case", CASES, ids=lambda item: item.case_id)
def test_shieldagent_bench_200_expected_runtime_decision(case, tmp_path):
    guard = BrowserGymActionGuard(
        case.regulations,
        trajectory_id=case.case_id.lower(),
        audit_directory=tmp_path,
    )
    verdict = guard.verify(
        case.action,
        {
            "goal": case.prompt,
            "url": f"http://{case.environment}.local",
            "axtree_txt": "synthetic WebArena accessibility tree",
        },
    )

    assert verdict.allowed is case.expected_allowed
    assert verdict.decision == case.expected_decision
