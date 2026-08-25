import json

import pytest

from riskagent.models import DeadCodeCandidate, RiskFlag, PullRequest
from riskagent.agent.llm_client import FakeLLMClient
from riskagent.agent.judgment import (
    judge_dead_code_candidate,
    resolve_owner_tiebreak,
    write_risk_justification,
)


def test_judge_dead_code_candidate_true_dead():
    candidate = DeadCodeCandidate(file_path="old.py", reason="no inbound edges")
    llm = FakeLLMClient(responder=lambda s, u: json.dumps({"verdict": "dead", "justification": "unused"}))
    result = judge_dead_code_candidate(candidate, "print('old')", llm)
    assert result.verdict is True
    assert result.justification == "unused"
    assert result.status == "pending"


def test_judge_dead_code_candidate_false_positive_sets_rejected():
    candidate = DeadCodeCandidate(file_path="plugin.py", reason="no inbound edges")
    llm = FakeLLMClient(
        responder=lambda s, u: json.dumps({"verdict": "false_positive", "justification": "dynamic plugin"})
    )
    result = judge_dead_code_candidate(candidate, "def register(): ...", llm)
    assert result.verdict is False
    assert result.status == "rejected"


def test_judge_dead_code_candidate_raises_on_non_json():
    candidate = DeadCodeCandidate(file_path="old.py", reason="no inbound edges")
    llm = FakeLLMClient(responder=lambda s, u: "not json")
    with pytest.raises(ValueError):
        judge_dead_code_candidate(candidate, "content", llm)


def test_resolve_owner_tiebreak_returns_chosen_owner():
    llm = FakeLLMClient(responder=lambda s, u: json.dumps({"owner": "alice", "justification": "most recent"}))
    owner = resolve_owner_tiebreak("pkg/mod.py", ["alice", "bob"], llm)
    assert owner == "alice"


def test_write_risk_justification_sets_text():
    risk_flag = RiskFlag(pr_number=1, score=3.0, affected_files=["a.py"], affected_owners=["alice"])
    pr = PullRequest(number=1, files_changed=["b.py"], diff_summary="refactor")
    llm = FakeLLMClient(responder=lambda s, u: json.dumps({"justification": "This touches a.py, owned by alice."}))
    result = write_risk_justification(risk_flag, pr, llm)
    assert result.justification == "This touches a.py, owned by alice."
