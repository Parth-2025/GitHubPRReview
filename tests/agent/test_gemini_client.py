from unittest.mock import Mock, patch

import pytest
import requests

from riskagent.agent.gemini_client import GeminiLLMClient


def _resp(json_data, status=200, headers=None):
    resp = Mock()
    resp.status_code = status
    resp.json.return_value = json_data
    resp.headers = headers or {}
    resp.text = "" if json_data is None else str(json_data)
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
def test_complete_raises_immediately_on_non_429_error(mock_post):
    mock_post.return_value = _resp({"error": {"message": "bad key"}}, status=403)
    client = GeminiLLMClient(api_key="k")
    with pytest.raises(requests.HTTPError) as exc:
        client.complete("sys", "usr")
    assert "403 from Gemini" in str(exc.value)
    assert mock_post.call_count == 1


@patch("riskagent.agent.gemini_client.time.sleep")
@patch("riskagent.agent.gemini_client.requests.post")
def test_complete_retries_on_429_then_succeeds(mock_post, mock_sleep):
    limited = _resp(
        {
            "error": {
                "message": "rate limited. Please retry in 12s.",
                "details": [{"retryDelay": "7s"}],
            }
        },
        status=429,
    )
    ok = _resp({"candidates": [{"content": {"parts": [{"text": "{}"}]}}]})
    mock_post.side_effect = [limited, ok]
    client = GeminiLLMClient(api_key="k")
    assert client.complete("sys", "usr") == "{}"
    assert mock_post.call_count == 2
    mock_sleep.assert_called_once_with(7.0)


@patch("riskagent.agent.gemini_client.time.sleep")
@patch("riskagent.agent.gemini_client.requests.post")
def test_complete_gives_up_after_max_retries_on_429(mock_post, mock_sleep):
    mock_post.return_value = _resp(
        {"error": {"message": "quota exceeded", "code": 429}}, status=429
    )
    client = GeminiLLMClient(api_key="k", max_retries=3)
    with pytest.raises(requests.HTTPError) as exc:
        client.complete("sys", "usr")
    assert "429 from Gemini" in str(exc.value)
    assert mock_post.call_count == 4  # initial + 3 retries
    assert mock_sleep.call_count == 3


@patch("riskagent.agent.gemini_client.time.sleep")
@patch("riskagent.agent.gemini_client.requests.post")
def test_retry_delay_capped(mock_post, mock_sleep):
    mock_post.side_effect = [
        _resp({"error": {"message": "slow down", "details": [{"retryDelay": "600s"}]}}, status=429),
        _resp({"candidates": [{"content": {"parts": [{"text": "{}"}]}}]}),
    ]
    client = GeminiLLMClient(api_key="k", retry_cap=30.0)
    client.complete("sys", "usr")
    mock_sleep.assert_called_once_with(30.0)
