import json
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

from riskagent.pipeline import analyze_repo
from riskagent.agent.llm_client import FakeLLMClient


def _iso_z(dt: datetime) -> str:
    """Format like the real GitHub API: RFC 3339 with a trailing 'Z'."""
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _fixture_github_client():
    client = Mock()
    client.get_repo_tree.return_value = ["pkg/a.py", "pkg/b.py", "pkg/orphan.py"]
    sources = {
        "pkg/a.py": "import pkg.b\n",
        "pkg/b.py": "",
        "pkg/orphan.py": "",
    }
    client.get_file_content.side_effect = lambda owner, repo, path, ref="main": sources[path]
    client.get_codeowners.return_value = None

    def commit_history(owner, repo, path):
        if path == "pkg/orphan.py":
            return [{"author": "bob", "date": _iso_z(datetime.now(timezone.utc) - timedelta(days=3000))}]
        return [{"author": "alice", "date": _iso_z(datetime.now(timezone.utc) - timedelta(days=30))}]

    client.get_commit_history.side_effect = commit_history
    client.get_open_pull_requests.return_value = [
        {"number": 1, "files_changed": ["pkg/b.py"], "diff_summary": "tweak b"}
    ]
    return client


def _fixture_llm_client():
    def responder(system_prompt, user_prompt):
        if "verdict" in system_prompt:
            return json.dumps({"verdict": "dead", "justification": "no references anywhere"})
        if "justification" in system_prompt and "PR #" in user_prompt:
            return json.dumps({"justification": "Touches pkg/a.py which imports pkg/b.py."})
        return json.dumps({"owner": "alice", "justification": "most recent committer"})

    return FakeLLMClient(responder=responder)


def test_analyze_repo_produces_risk_flags_and_dead_code_candidates():
    github_client = _fixture_github_client()
    llm_client = _fixture_llm_client()

    result = analyze_repo(github_client, llm_client, "owner", "repo")

    assert set(result.keys()) == {"graph", "risk_flags", "dead_code_candidates"}

    risk_flags = result["risk_flags"]
    assert len(risk_flags) == 1
    assert risk_flags[0].pr_number == 1
    assert "pkg/a.py" in risk_flags[0].affected_files
    assert risk_flags[0].justification == "Touches pkg/a.py which imports pkg/b.py."

    candidates = result["dead_code_candidates"]
    assert len(candidates) == 1
    assert candidates[0].file_path == "pkg/orphan.py"
    assert candidates[0].verdict is True
    assert candidates[0].status == "pending"


def _fixture_github_client_with_domain_file():
    client = Mock()
    client.get_repo_tree.return_value = ["pkg/a.py", "pkg/domain.py"]
    sources = {
        "pkg/a.py": "",
        "pkg/domain.py": "",
    }
    client.get_file_content.side_effect = lambda owner, repo, path, ref="main": sources[path]
    client.get_codeowners.return_value = None
    client.get_commit_history.side_effect = lambda owner, repo, path: [
        {"author": "bob", "date": _iso_z(datetime.now(timezone.utc) - timedelta(days=3000))}
    ]
    client.get_open_pull_requests.return_value = []
    return client


def test_analyze_repo_does_not_treat_domain_py_as_entry_point():
    # "domain.py" ends with the substring "main.py" but is not itself an
    # entry point; it must still be eligible for dead-code detection.
    github_client = _fixture_github_client_with_domain_file()
    llm_client = _fixture_llm_client()

    result = analyze_repo(github_client, llm_client, "owner", "repo")

    candidate_paths = {c.file_path for c in result["dead_code_candidates"]}
    assert "pkg/domain.py" in candidate_paths
