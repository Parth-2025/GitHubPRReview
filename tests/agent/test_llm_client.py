from riskagent.agent.llm_client import FakeLLMClient
from riskagent.agent.prompts import (
    DEAD_CODE_JUDGMENT_SYSTEM_PROMPT,
    OWNER_TIEBREAK_SYSTEM_PROMPT,
    RISK_JUSTIFICATION_SYSTEM_PROMPT,
)


def test_fake_llm_client_returns_responder_output_and_records_calls():
    client = FakeLLMClient(responder=lambda system, user: f"echo:{user}")
    result = client.complete("system-prompt", "user-prompt")
    assert result == "echo:user-prompt"
    assert client.calls == [("system-prompt", "user-prompt")]


def test_prompts_mention_required_json_fields():
    assert "verdict" in DEAD_CODE_JUDGMENT_SYSTEM_PROMPT
    assert "justification" in DEAD_CODE_JUDGMENT_SYSTEM_PROMPT
    assert "owner" in OWNER_TIEBREAK_SYSTEM_PROMPT
    assert "justification" in RISK_JUSTIFICATION_SYSTEM_PROMPT
