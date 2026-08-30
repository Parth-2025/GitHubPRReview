import json

from riskagent.agent.prompts import (
    DEAD_CODE_JUDGMENT_SYSTEM_PROMPT,
    OWNER_TIEBREAK_SYSTEM_PROMPT,
    RISK_JUSTIFICATION_SYSTEM_PROMPT,
)
from riskagent.agent.scripted_client import ScriptedLLMClient


def test_dead_code_branch_defaults_to_dead():
    client = ScriptedLLMClient()
    out = json.loads(client.complete(DEAD_CODE_JUDGMENT_SYSTEM_PROMPT, "File path: x"))
    assert out["verdict"] == "dead"
    assert "justification" in out


def test_dead_code_branch_can_be_false_positive():
    client = ScriptedLLMClient(dead_code_verdict="false_positive")
    out = json.loads(client.complete(DEAD_CODE_JUDGMENT_SYSTEM_PROMPT, "File path: x"))
    assert out["verdict"] == "false_positive"


def test_owner_branch_picks_first_tied_owner():
    client = ScriptedLLMClient()
    user = "File path: pkg/mod.py\nTied candidate owners: alice, bob"
    out = json.loads(client.complete(OWNER_TIEBREAK_SYSTEM_PROMPT, user))
    assert out["owner"] == "alice"


def test_risk_branch_returns_configured_justification():
    client = ScriptedLLMClient(risk_justification="canned text")
    out = json.loads(client.complete(RISK_JUSTIFICATION_SYSTEM_PROMPT, "PR #1: refactor"))
    assert out["justification"] == "canned text"


def test_records_calls():
    client = ScriptedLLMClient()
    client.complete("s", "u")
    assert client.calls == [("s", "u")]
