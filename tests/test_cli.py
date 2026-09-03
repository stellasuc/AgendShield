from __future__ import annotations

from agentshield.cli import main


def test_policy_list(capsys) -> None:
    assert main(["policy", "list"]) == 0
    output = capsys.readouterr().out
    assert "GDPR     supported" in output
    assert "PIPL     supported" in output


def test_policy_show_preserves_article_and_disclaimer(capsys) -> None:
    assert main(["policy", "show", "GDPR"]) == 0
    output = capsys.readouterr().out
    assert "Article 6(1)" in output
    assert "EUR-Lex" in output or "eur-lex" in output
    assert "not legal advice" in output

