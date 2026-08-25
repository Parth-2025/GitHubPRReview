import base64
from unittest.mock import patch, Mock

from riskagent.github.client import GitHubClient


def _mock_response(json_data, status_code=200):
    resp = Mock()
    resp.status_code = status_code
    resp.json.return_value = json_data
    resp.raise_for_status = Mock()
    if status_code >= 400:
        import requests
        error = requests.HTTPError(response=resp)
        resp.raise_for_status.side_effect = error
    return resp


@patch("riskagent.github.client.requests.get")
def test_get_repo_tree_filters_python_blobs(mock_get):
    mock_get.return_value = _mock_response({
        "tree": [
            {"path": "a.py", "type": "blob"},
            {"path": "README.md", "type": "blob"},
            {"path": "pkg", "type": "tree"},
        ]
    })
    client = GitHubClient(token="fake-token")
    result = client.get_repo_tree("owner", "repo", "main")
    assert result == ["a.py"]


@patch("riskagent.github.client.requests.get")
def test_get_file_content_decodes_base64(mock_get):
    encoded = base64.b64encode(b"print('hi')").decode("utf-8")
    mock_get.return_value = _mock_response({"content": encoded})
    client = GitHubClient(token="fake-token")
    content = client.get_file_content("owner", "repo", "a.py")
    assert content == "print('hi')"


@patch("riskagent.github.client.requests.get")
def test_get_codeowners_returns_none_on_404(mock_get):
    mock_get.return_value = _mock_response({}, status_code=404)
    client = GitHubClient(token="fake-token")
    assert client.get_codeowners("owner", "repo") is None


@patch("riskagent.github.client.requests.get")
def test_get_commit_history_maps_author_and_date(mock_get):
    mock_get.return_value = _mock_response([
        {"commit": {"author": {"name": "alice", "date": "2026-01-01T00:00:00Z"}}}
    ])
    client = GitHubClient(token="fake-token")
    history = client.get_commit_history("owner", "repo", "a.py")
    assert history == [{"author": "alice", "date": "2026-01-01T00:00:00Z"}]


@patch("riskagent.github.client.requests.get")
def test_get_open_pull_requests_fetches_files_per_pr(mock_get):
    def side_effect(url, headers=None, params=None):
        if url.endswith("/pulls"):
            return _mock_response([{"number": 5, "title": "Fix thing"}])
        if url.endswith("/pulls/5/files"):
            return _mock_response([{"filename": "a.py"}, {"filename": "b.py"}])
        raise AssertionError(f"unexpected URL {url}")

    mock_get.side_effect = side_effect
    client = GitHubClient(token="fake-token")
    prs = client.get_open_pull_requests("owner", "repo")
    assert prs == [{"number": 5, "files_changed": ["a.py", "b.py"], "diff_summary": "Fix thing"}]


@patch("riskagent.github.client.requests.post")
def test_post_pr_comment(mock_post):
    mock_post.return_value = _mock_response({"id": 1})
    client = GitHubClient(token="fake-token")
    result = client.post_pr_comment("owner", "repo", 5, "risky!")
    assert result == {"id": 1}
    mock_post.assert_called_once()


@patch("riskagent.github.client.requests.post")
def test_create_issue_includes_assignee_and_labels(mock_post):
    mock_post.return_value = _mock_response({"id": 2})
    client = GitHubClient(token="fake-token")
    client.create_issue("owner", "repo", "title", "body", assignee="alice", labels=["cleanup-candidate"])
    _, kwargs = mock_post.call_args
    assert kwargs["json"]["assignees"] == ["alice"]
    assert kwargs["json"]["labels"] == ["cleanup-candidate"]
