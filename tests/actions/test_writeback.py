from unittest.mock import Mock

from riskagent.models import RiskFlag, DeadCodeCandidate
from riskagent.actions.writeback import post_risk_comment, file_dead_code_issue


def test_post_risk_comment_calls_client_and_sets_status():
    client = Mock()
    risk_flag = RiskFlag(
        pr_number=5, score=3.0, affected_files=["a.py"], affected_owners=["alice"], justification="risky"
    )
    result = post_risk_comment(client, "owner", "repo", risk_flag)
    client.post_pr_comment.assert_called_once()
    args, kwargs = client.post_pr_comment.call_args
    assert args[0] == "owner"
    assert args[1] == "repo"
    assert args[2] == 5
    assert "risky" in args[3]
    assert "a.py" in args[3]
    assert result.status == "posted"


def test_file_dead_code_issue_calls_client_and_sets_status():
    client = Mock()
    candidate = DeadCodeCandidate(file_path="old.py", reason="orphaned", justification="unused since 2024")
    result = file_dead_code_issue(client, "owner", "repo", candidate, assignee="alice")
    client.create_issue.assert_called_once_with(
        "owner",
        "repo",
        "Cleanup candidate: old.py",
        "unused since 2024\n\nFlagged by automated dead-code analysis.",
        assignee="alice",
        labels=["cleanup-candidate"],
    )
    assert result.status == "issue_filed"
