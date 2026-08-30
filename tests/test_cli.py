# tests/test_cli.py
from unittest.mock import Mock, patch

import pytest

from riskagent.analysis.graph import DependencyGraph
from riskagent.cli import build_arg_parser, format_report, main
from riskagent.models import DeadCodeCandidate, RiskFlag


def test_build_arg_parser_basic():
    args = build_arg_parser().parse_args(
        ["owner/repo", "--dry-run", "--max-files", "5", "--risk-threshold", "2.5"]
    )
    assert args.repo == "owner/repo"
    assert args.dry_run is True
    assert args.max_files == 5
    assert args.risk_threshold == 2.5
    assert args.model == "gemini-2.0-flash"


def test_help_exits_zero():
    with pytest.raises(SystemExit) as exc:
        main(["--help"])
    assert exc.value.code == 0


def test_format_report_has_both_sections():
    result = {
        "graph": DependencyGraph([], []),
        "risk_flags": [
            RiskFlag(
                pr_number=7,
                score=3.0,
                affected_files=["a.py"],
                affected_owners=["alice"],
                justification="touches a.py",
                status="pending",
            )
        ],
        "dead_code_candidates": [
            DeadCodeCandidate(
                file_path="old.py",
                reason="orphan",
                verdict=True,
                justification="unused",
                status="pending",
            )
        ],
    }
    text = format_report(result)
    assert "PR #7" in text
    assert "a.py" in text
    assert "touches a.py" in text
    assert "old.py" in text


@patch("riskagent.cli.analyze_repo")
@patch("riskagent.cli._make_llm")
@patch("riskagent.cli._make_github")
def test_main_invokes_pipeline(mock_github, mock_llm, mock_analyze):
    gh = Mock()
    gh.get_default_branch.return_value = "main"
    mock_github.return_value = gh
    mock_analyze.return_value = {
        "graph": DependencyGraph([], []),
        "risk_flags": [],
        "dead_code_candidates": [],
    }

    rc = main(["someowner/somerepo", "--dry-run"])

    assert rc == 0
    args, kwargs = mock_analyze.call_args
    assert args[2] == "someowner"
    assert args[3] == "somerepo"
    assert kwargs["max_files"] is None
    assert kwargs["risk_score_threshold"] == 0.0
