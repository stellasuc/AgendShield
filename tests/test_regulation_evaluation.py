from __future__ import annotations

from evaluation.regulation_cases import run_evaluation


def test_deterministic_regulation_evaluation_cases(tmp_path) -> None:
    payload = run_evaluation(tmp_path / "results.json")
    summary = payload["summary"]
    assert summary["cases_total"] == 12
    assert summary["cases_passed"] == 12
    assert summary["violations_detected"] == summary["violations_expected"]
    assert summary["false_blocks"] == 0
    assert summary["repairs_attempted"] == summary["repairs_successful"] == 1
