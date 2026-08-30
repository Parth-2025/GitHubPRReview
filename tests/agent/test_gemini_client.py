from unittest.mock import Mock, patch

import pytest
import requests

from riskagent.agent.gemini_client import GeminiLLMClient


def _resp(json_data, status=200):
    resp = Mock()
    resp.status_code = status
    resp.json.return_value = json_data
    resp.raise_for_status = Mock()
    if status >= 400:
        resp.raise_for_status.side_effect = requests.HTTPError(response=resp)
    return resp


@patch("riskagent.agent.gemini_client.requests.post")
def test_complete_returns_model_text(mock_post):
    mock_post.return_value = _resp(
        {"candidates": [{"content": {"parts": [{"text": '{"verdict": "dead"}'}]}}]}
    )
    client = GeminiLLMClient(api_key="k")
    assert client.complete("sys", "usr") == '{"verdict": "dead"}'


@patch("riskagent.agent.gemini_client.requests.post")
def test_complete_sends_system_instruction_and_json_mode(mock_post):
    mock_post.return_value = _resp({"candidates": [{"content": {"parts": [{"text": "{}"}]}}]})
    client = GeminiLLMClient(api_key="secret-key", model="gemini-2.0-flash")
    client.complete("SYSTEM", "USER")
    (url,), kwargs = mock_post.call_args
    assert url.endswith("/v1beta/models/gemini-2.0-flash:generateContent")
    assert kwargs["headers"]["x-goog-api-key"] == "secret-key"
    assert kwargs["json"]["system_instruction"]["parts"][0]["text"] == "SYSTEM"
    assert kwargs["json"]["contents"][0]["parts"][0]["text"] == "USER"
    assert kwargs["json"]["generationConfig"]["responseMimeType"] == "application/json"


@patch("riskagent.agent.gemini_client.requests.post")
def test_complete_raises_when_no_candidates(mock_post):
    mock_post.return_value = _resp({"promptFeedback": {"blockReason": "SAFETY"}})
    client = GeminiLLMClient(api_key="k")
    with pytest.raises(RuntimeError):
        client.complete("sys", "usr")


@patch("riskagent.agent.gemini_client.requests.post")
def test_complete_propagates_http_error(mock_post):
    mock_post.return_value = _resp({}, status=429)
    client = GeminiLLMClient(api_key="k")
    with pytest.raises(requests.HTTPError):
        client.complete("sys", "usr")
