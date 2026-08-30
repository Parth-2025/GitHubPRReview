# Local End-to-End Runnable Demo Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the already-built `riskagent` library runnable end-to-end from the terminal against a real public GitHub repo, using Gemini as the live judgment backend, so the analysis logic can be validated before any Foundry/AIP wiring.

**Architecture:** The portable core (`src/riskagent/`, 57 passing tests) is untouched in spirit. This plan adds the missing edges: a GitHub-URL parser, a default-branch lookup on the existing `GitHubClient`, a real `LLMClient` implementation backed by Google's Gemini API, a credential-free offline `LLMClient` for dry runs, two new `analyze_repo` knobs (file cap, risk-score threshold) for rate-limit safety, and a `python -m riskagent` CLI that runs the pipeline and prints a report — with an opt-in `--post` path that performs the GitHub writeback actions. Everything stays unit-tested with mocked HTTP; no real network or real LLM calls in tests.

**Tech Stack:** Python 3.11+, `pytest`, `requests` (HTTP mocked in tests via `unittest.mock`), standard library `argparse`/`json`/`re`/`os`. Live backend: Google Gemini Generative Language API (`gemini-2.0-flash`, free tier).

**Spec:** `/Users/parthmohan/Desktop/PalantirProject/docs/specs/2026-08-24-codebase-risk-agent-design.md`

## Global Constraints

- Language support is Python only (import parsing via `ast`) — unchanged from v1.
- Trigger is on-demand only — the CLI is invoked by hand; no webhook/automatic logic.
- No real network calls or real LLM calls in tests — everything is mocked/faked.
- Dead-code candidates the agent judges as false positives must never reach the writeback step (status `rejected`, not `pending`) — already enforced in `judgment.py`; the CLI `--post` path must also skip `rejected` candidates.
- Writeback (PR comment, GitHub issue) fires only when explicitly invoked — the CLI must never post as a side effect of analysis; `--post` is opt-in and, unless `--yes` is given, prompts for confirmation before writing.
- The `LLMClient` seam is `complete(system_prompt: str, user_prompt: str) -> str`. Any new client implements exactly that; swapping Gemini for a real AIP Logic SDK client later must remain a one-line change.
- Secrets come from environment variables only (`GITHUB_TOKEN`, `GEMINI_API_KEY`) — never CLI arguments, never written to disk.
- Existing tests must stay green. New `analyze_repo` parameters are keyword-only with defaults that preserve current behavior (`max_files=None`, `risk_score_threshold=0.0`).

---

## File Structure

```
requirements.txt                          # NEW - declare requests + pytest
README.md                                 # NEW - how to run the CLI locally
src/riskagent/
  repo_url.py                             # NEW - parse_repo_url()
  cli.py                                  # NEW - argparse CLI, report formatting, writeback path
  __main__.py                             # NEW - `python -m riskagent` entrypoint
  github/client.py                        # MODIFY - add get_default_branch()
  analysis/graph.py                       # MODIFY - add DependencyGraph.file() accessor
  pipeline.py                             # MODIFY - add max_files + risk_score_threshold
  agent/
    gemini_client.py                      # NEW - GeminiLLMClient (real backend)
    scripted_client.py                    # NEW - ScriptedLLMClient (offline dry-run)
tests/
  test_repo_url.py                        # NEW
  test_cli.py                             # NEW
  agent/test_gemini_client.py            # NEW
  agent/test_scripted_client.py          # NEW
  github/test_client.py                   # MODIFY - add default-branch test
  analysis/test_graph.py                  # MODIFY - add file() accessor test
  test_pipeline.py                        # MODIFY - add max_files + threshold tests
docs/
  foundry_mapping.md                      # MODIFY - document the local-demo modules and the swap point
```

---

### Task 1: GitHub repo-URL parser

**Files:**
- Create: `src/riskagent/repo_url.py`
- Test: `tests/test_repo_url.py`

**Interfaces:**
- Produces: `parse_repo_url(url: str) -> tuple[str, str]` in `riskagent.repo_url`. Returns `(owner, repo)`. Accepts `https://github.com/owner/repo`, the same with a `.git` suffix or trailing slash, `git@github.com:owner/repo.git`, and bare `owner/repo` shorthand. Raises `ValueError` for anything else.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_repo_url.py
import pytest

from riskagent.repo_url import parse_repo_url


def test_parses_https_url():
    assert parse_repo_url("https://github.com/pallets/flask") == ("pallets", "flask")


def test_parses_https_url_with_git_suffix():
    assert parse_repo_url("https://github.com/pallets/flask.git") == ("pallets", "flask")


def test_parses_https_url_with_trailing_slash():
    assert parse_repo_url("https://github.com/pallets/flask/") == ("pallets", "flask")


def test_parses_ssh_url():
    assert parse_repo_url("git@github.com:pallets/flask.git") == ("pallets", "flask")


def test_parses_shorthand():
    assert parse_repo_url("pallets/flask") == ("pallets", "flask")


def test_rejects_non_github_input():
    with pytest.raises(ValueError):
        parse_repo_url("https://gitlab.com/pallets/flask")
    with pytest.raises(ValueError):
        parse_repo_url("not a url")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_repo_url.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'riskagent.repo_url'`

- [ ] **Step 3: Write implementation**

```python
# src/riskagent/repo_url.py
import re

_PATTERNS = [
    re.compile(r"^https?://github\.com/(?P<owner>[^/]+)/(?P<repo>[^/]+?)(?:\.git)?/?$"),
    re.compile(r"^git@github\.com:(?P<owner>[^/]+)/(?P<repo>[^/]+?)(?:\.git)?$"),
    re.compile(r"^(?P<owner>[A-Za-z0-9_.-]+)/(?P<repo>[A-Za-z0-9_.-]+?)(?:\.git)?$"),
]


def parse_repo_url(url: str) -> tuple[str, str]:
    """Parse a GitHub repo reference into (owner, repo).

    Accepts full https URLs, ssh URLs, and bare ``owner/repo`` shorthand,
    each optionally suffixed with ``.git`` (and https optionally with a
    trailing slash). Raises ValueError for anything that does not match.
    """
    text = url.strip()
    for pattern in _PATTERNS:
        match = pattern.match(text)
        if match:
            return match.group("owner"), match.group("repo")
    raise ValueError(
        f"Not a recognizable GitHub repo URL or owner/repo shorthand: {url!r}"
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_repo_url.py -v`
Expected: PASS (6 passed)

- [ ] **Step 5: Commit**

```bash
git add src/riskagent/repo_url.py tests/test_repo_url.py
git commit -m "feat: add GitHub repo-URL parser"
```

---

### Task 2: Default-branch lookup on GitHubClient

**Files:**
- Modify: `src/riskagent/github/client.py` (add one method after `get_repo_tree`)
- Test: `tests/github/test_client.py` (add one test)

**Interfaces:**
- Consumes: the existing `GitHubClient` (`token`, `base_url`, `_headers()`).
- Produces: `GitHubClient.get_default_branch(owner: str, repo: str) -> str` — GETs `/repos/{owner}/{repo}` and returns the `default_branch` field. Lets the CLI analyze repos whose default branch is not `main`.

- [ ] **Step 1: Write the failing test**

```python
# append to tests/github/test_client.py

@patch("riskagent.github.client.requests.get")
def test_get_default_branch(mock_get):
    mock_get.return_value = _mock_response({"default_branch": "master"})
    client = GitHubClient(token="fake-token")
    assert client.get_default_branch("owner", "repo") == "master"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/github/test_client.py::test_get_default_branch -v`
Expected: FAIL with `AttributeError: 'GitHubClient' object has no attribute 'get_default_branch'`

- [ ] **Step 3: Write implementation**

Add this method to `GitHubClient` in `src/riskagent/github/client.py`, immediately after `get_repo_tree`:

```python
    def get_default_branch(self, owner: str, repo: str) -> str:
        url = f"{self.base_url}/repos/{owner}/{repo}"
        resp = requests.get(url, headers=self._headers())
        resp.raise_for_status()
        return resp.json()["default_branch"]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/github/test_client.py -v`
Expected: PASS (8 passed — the 7 existing plus the new one)

- [ ] **Step 5: Commit**

```bash
git add src/riskagent/github/client.py tests/github/test_client.py
git commit -m "feat: add GitHubClient.get_default_branch"
```

---

### Task 3: GeminiLLMClient (real judgment backend)

**Files:**
- Create: `src/riskagent/agent/gemini_client.py`
- Test: `tests/agent/test_gemini_client.py`

**Interfaces:**
- Consumes: nothing from the package (only `requests`).
- Produces: `GeminiLLMClient(api_key: str, model: str = "gemini-2.0-flash", base_url: str = "https://generativelanguage.googleapis.com", timeout: int = 30)` with `.complete(system_prompt: str, user_prompt: str) -> str`. Satisfies the `riskagent.agent.llm_client.LLMClient` Protocol. POSTs to `{base_url}/v1beta/models/{model}:generateContent` with the API key in the `x-goog-api-key` header, the system prompt in `system_instruction`, the user prompt as the sole `user` turn, and `responseMimeType: "application/json"` so the model returns bare JSON that `riskagent.agent.judgment` can `json.loads`. Raises `RuntimeError` when the response has no candidates (e.g. a safety block); lets `requests.HTTPError` propagate on non-2xx.

- [ ] **Step 1: Write the failing test**

```python
# tests/agent/test_gemini_client.py
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/agent/test_gemini_client.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'riskagent.agent.gemini_client'`

- [ ] **Step 3: Write implementation**

```python
# src/riskagent/agent/gemini_client.py
import requests


class GeminiLLMClient:
    """Real LLMClient backed by Google's Gemini API.

    This is the local stand-in for the AIP Logic agent. It implements the
    same ``complete(system_prompt, user_prompt) -> str`` seam that
    ``riskagent.agent.judgment`` calls, so replacing it with a real AIP
    Logic SDK client later is a one-line change at the call site.
    """

    def __init__(
        self,
        api_key: str,
        model: str = "gemini-2.0-flash",
        base_url: str = "https://generativelanguage.googleapis.com",
        timeout: int = 30,
    ):
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        url = f"{self.base_url}/v1beta/models/{self.model}:generateContent"
        payload = {
            "system_instruction": {"parts": [{"text": system_prompt}]},
            "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
            "generationConfig": {
                "temperature": 0,
                "responseMimeType": "application/json",
            },
        }
        resp = requests.post(
            url,
            headers={
                "x-goog-api-key": self.api_key,
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=self.timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        candidates = data.get("candidates") or []
        if not candidates:
            feedback = data.get("promptFeedback", {})
            raise RuntimeError(
                f"Gemini returned no candidates (promptFeedback={feedback!r})"
            )
        parts = candidates[0].get("content", {}).get("parts") or []
        text = "".join(part.get("text", "") for part in parts)
        return text.strip()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/agent/test_gemini_client.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add src/riskagent/agent/gemini_client.py tests/agent/test_gemini_client.py
git commit -m "feat: add GeminiLLMClient as the live judgment backend"
```

---

### Task 4: ScriptedLLMClient (offline dry-run backend)

**Files:**
- Create: `src/riskagent/agent/scripted_client.py`
- Test: `tests/agent/test_scripted_client.py`

**Interfaces:**
- Consumes: nothing (routes purely on the text of the system prompt).
- Produces: `ScriptedLLMClient(dead_code_verdict: str = "dead", owner: str | None = None, risk_justification: str = "Dry-run: risk justification not generated by a real model.")` with `.complete(system_prompt: str, user_prompt: str) -> str` and `.calls` (list of `(system_prompt, user_prompt)` tuples). Returns canned, schema-valid JSON for each of the three judgment call sites so `analyze_repo` runs with no API key. For the owner-tiebreak call it returns `owner` if set, otherwise the first name from the `Tied candidate owners:` line of the user prompt (so `judgment.resolve_owner_tiebreak`'s "owner must be in candidate list" check passes).

- [ ] **Step 1: Write the failing test**

```python
# tests/agent/test_scripted_client.py
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/agent/test_scripted_client.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'riskagent.agent.scripted_client'`

- [ ] **Step 3: Write implementation**

```python
# src/riskagent/agent/scripted_client.py
import json
from typing import Optional


class ScriptedLLMClient:
    """Offline LLMClient for ``--dry-run``: returns canned, schema-valid JSON
    so the pipeline runs end-to-end with no API key. It routes by inspecting
    the system prompt, which differs per judgment call site.
    """

    def __init__(
        self,
        dead_code_verdict: str = "dead",
        owner: Optional[str] = None,
        risk_justification: str = "Dry-run: risk justification not generated by a real model.",
    ):
        self.dead_code_verdict = dead_code_verdict
        self.owner = owner
        self.risk_justification = risk_justification
        self.calls: list = []

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        self.calls.append((system_prompt, user_prompt))
        # Route on the quoted JSON-key token from each prompt's response
        # schema. Bare "owner" would false-match the risk-justification
        # prompt, whose prose contains the word "owners".
        if '"verdict"' in system_prompt:
            return json.dumps(
                {
                    "verdict": self.dead_code_verdict,
                    "justification": "dry-run: no model was called",
                }
            )
        if '"owner"' in system_prompt:
            chosen = self.owner or self._first_tied_owner(user_prompt)
            return json.dumps(
                {"owner": chosen, "justification": "dry-run: first tied owner"}
            )
        return json.dumps({"justification": self.risk_justification})

    @staticmethod
    def _first_tied_owner(user_prompt: str) -> str:
        marker = "Tied candidate owners:"
        if marker in user_prompt:
            tail = user_prompt.split(marker, 1)[1].strip()
            first = tail.splitlines()[0].split(",")[0].strip()
            if first:
                return first
        return "unknown"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/agent/test_scripted_client.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add src/riskagent/agent/scripted_client.py tests/agent/test_scripted_client.py
git commit -m "feat: add ScriptedLLMClient for credential-free dry runs"
```

---

### Task 5: analyze_repo file cap + risk-score threshold, and a graph accessor

**Files:**
- Modify: `src/riskagent/analysis/graph.py` (add `file()` method to `DependencyGraph`)
- Modify: `src/riskagent/pipeline.py` (add two keyword-only params)
- Test: `tests/analysis/test_graph.py` (add one test)
- Test: `tests/test_pipeline.py` (add two tests)

**Interfaces:**
- Consumes: existing `DependencyGraph`, `analyze_repo`.
- Produces:
  - `DependencyGraph.file(path: str) -> FileNode | None` — returns the node for a path, or `None`. Lets the CLI look up a file's `primary_owner` when filing an issue.
  - `analyze_repo(github_client, llm_client, owner, repo, branch="main", *, max_files: int | None = None, risk_score_threshold: float = 0.0) -> dict` — same return shape (`"graph"`, `"risk_flags"`, `"dead_code_candidates"`). When `max_files` is set, only the first `max_files` paths from the repo tree are analyzed (rate-limit safety on large repos). A PR whose blast-radius score is below `risk_score_threshold` gets a `RiskFlag` with `status="below_threshold"` and no LLM justification call (saves quota); at or above threshold, behavior is unchanged. Defaults keep current behavior exactly.

- [ ] **Step 1: Write the failing tests**

```python
# append to tests/analysis/test_graph.py

def test_file_accessor_returns_node_or_none():
    g = _graph()
    assert g.file("a.py").path == "a.py"
    assert g.file("missing.py") is None
```

```python
# append to tests/test_pipeline.py

def test_analyze_repo_respects_max_files():
    github_client = _fixture_github_client()
    llm_client = _fixture_llm_client()

    result = analyze_repo(github_client, llm_client, "owner", "repo", max_files=1)

    assert [f.path for f in result["graph"].files] == ["pkg/a.py"]


def test_analyze_repo_below_threshold_skips_justification():
    github_client = _fixture_github_client()
    llm_client = _fixture_llm_client()

    result = analyze_repo(
        github_client, llm_client, "owner", "repo", risk_score_threshold=99.0
    )

    assert len(result["risk_flags"]) == 1
    assert result["risk_flags"][0].status == "below_threshold"
    assert result["risk_flags"][0].justification == ""
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/analysis/test_graph.py::test_file_accessor_returns_node_or_none tests/test_pipeline.py -v`
Expected: `test_file_accessor_returns_node_or_none` FAILs with `AttributeError: 'DependencyGraph' object has no attribute 'file'`; `test_analyze_repo_respects_max_files` FAILs with `TypeError: analyze_repo() got an unexpected keyword argument 'max_files'`.

- [ ] **Step 3: Add the graph accessor**

In `src/riskagent/analysis/graph.py`, add this method to `DependencyGraph`, immediately after `direct_dependents`:

```python
    def file(self, path: str) -> Optional[FileNode]:
        return self._file_by_path.get(path)
```

- [ ] **Step 4: Add the pipeline parameters**

In `src/riskagent/pipeline.py`, change the `analyze_repo` signature and two spots in the body.

Signature:

```python
def analyze_repo(
    github_client: GitHubClient,
    llm_client: LLMClient,
    owner: str,
    repo: str,
    branch: str = "main",
    *,
    max_files: Optional[int] = None,
    risk_score_threshold: float = 0.0,
) -> dict:
```

Add `from typing import Optional` to the imports at the top of the file.

Right after `paths = github_client.get_repo_tree(owner, repo, branch)`:

```python
    if max_files is not None:
        paths = paths[:max_files]
```

In the PR loop, replace:

```python
        risk_flag = RiskFlag(
            pr_number=pr.number, score=score, affected_files=sorted(affected), affected_owners=owners
        )
        risk_flag = write_risk_justification(risk_flag, pr, llm_client)
        risk_flags.append(risk_flag)
```

with:

```python
        risk_flag = RiskFlag(
            pr_number=pr.number, score=score, affected_files=sorted(affected), affected_owners=owners
        )
        if score >= risk_score_threshold:
            risk_flag = write_risk_justification(risk_flag, pr, llm_client)
        else:
            risk_flag.status = "below_threshold"
        risk_flags.append(risk_flag)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/analysis/test_graph.py tests/test_pipeline.py -v`
Expected: PASS (all graph tests plus all pipeline tests, including the 2 new ones)

- [ ] **Step 6: Commit**

```bash
git add src/riskagent/analysis/graph.py src/riskagent/pipeline.py tests/analysis/test_graph.py tests/test_pipeline.py
git commit -m "feat: add file cap and risk-score threshold to analyze_repo"
```

---

### Task 6: CLI — run the pipeline and print a report

**Files:**
- Create: `src/riskagent/cli.py`
- Create: `src/riskagent/__main__.py`
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes: `parse_repo_url` (Task 1), `GitHubClient` + `get_default_branch` (Task 2), `GeminiLLMClient` (Task 3), `ScriptedLLMClient` (Task 4), `analyze_repo` (Task 5), `post_risk_comment` / `file_dead_code_issue` from `riskagent.actions.writeback`.
- Produces, in `riskagent.cli`:
  - `build_arg_parser() -> argparse.ArgumentParser` — positional `repo`; flags `--branch`, `--max-files` (int), `--risk-threshold` (float, default 0.0), `--dry-run`, `--model` (default `gemini-2.0-flash`), `--post`, `--yes`.
  - `format_report(result: dict) -> str` — renders the `analyze_repo` result dict as plain text with an "Open PR risk flags" section and a "Dead-code candidates" section (confirmed vs. rejected).
  - `main(argv: list[str] | None = None) -> int` — parses args, resolves `owner/repo`, builds the GitHub + LLM clients, resolves the branch (explicit `--branch` or `get_default_branch`), runs `analyze_repo`, prints `format_report`, and (if `--post`) calls `_run_writeback`. Returns `0`.
  - `_make_github(args) -> GitHubClient` and `_make_llm(args) -> LLMClient` — read `GITHUB_TOKEN` / `GEMINI_API_KEY` from the environment; raise `SystemExit` with a helpful message if a needed one is missing (`--dry-run` skips the Gemini key).
- `src/riskagent/__main__.py` wires `python -m riskagent` to `main`.

- [ ] **Step 1: Write the failing test**

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_cli.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'riskagent.cli'`

- [ ] **Step 3: Write implementation**

```python
# src/riskagent/cli.py
import argparse
import os

from riskagent.actions.writeback import file_dead_code_issue, post_risk_comment
from riskagent.agent.gemini_client import GeminiLLMClient
from riskagent.agent.scripted_client import ScriptedLLMClient
from riskagent.github.client import GitHubClient
from riskagent.pipeline import analyze_repo
from riskagent.repo_url import parse_repo_url


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="riskagent",
        description="Analyze a public GitHub repo for change-risk and dead code.",
    )
    parser.add_argument("repo", help="GitHub repo URL or owner/repo shorthand")
    parser.add_argument(
        "--branch", default=None, help="Branch to analyze (default: the repo's default branch)"
    )
    parser.add_argument(
        "--max-files", type=int, default=None, help="Only analyze the first N Python files"
    )
    parser.add_argument(
        "--risk-threshold",
        type=float,
        default=0.0,
        help="Only write a justification for PRs scoring at or above this",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Use the offline scripted LLM client (no GEMINI_API_KEY needed)",
    )
    parser.add_argument("--model", default="gemini-2.0-flash", help="Gemini model name")
    parser.add_argument(
        "--post",
        action="store_true",
        help="Post PR comments / file issues for findings (needs a write-scoped token)",
    )
    parser.add_argument(
        "--yes", action="store_true", help="Skip the confirmation prompt for --post"
    )
    return parser


def _make_github(args) -> GitHubClient:
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        raise SystemExit(
            "GITHUB_TOKEN is not set. Create a token at "
            "https://github.com/settings/tokens and `export GITHUB_TOKEN=...`."
        )
    return GitHubClient(token=token)


def _make_llm(args):
    if args.dry_run:
        return ScriptedLLMClient()
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        raise SystemExit(
            "GEMINI_API_KEY is not set. Get one at https://aistudio.google.com/apikey "
            "and `export GEMINI_API_KEY=...`, or pass --dry-run to use the offline client."
        )
    return GeminiLLMClient(api_key=key, model=args.model)


def format_report(result: dict) -> str:
    lines = [f"Files analyzed: {len(result['graph'].files)}", "", "== Open PR risk flags =="]
    if not result["risk_flags"]:
        lines.append("  (none)")
    for rf in result["risk_flags"]:
        lines.append(f"  PR #{rf.pr_number}  score={rf.score}  status={rf.status}")
        lines.append(f"    affected files: {', '.join(rf.affected_files) or '(none)'}")
        lines.append(f"    affected owners: {', '.join(rf.affected_owners) or '(none)'}")
        if rf.justification:
            lines.append(f"    reasoning: {rf.justification}")
    lines += ["", "== Dead-code candidates =="]
    if not result["dead_code_candidates"]:
        lines.append("  (none)")
    for c in result["dead_code_candidates"]:
        if c.status == "rejected":
            lines.append(f"  {c.file_path}  verdict=false-positive (skipped)")
        else:
            lines.append(f"  {c.file_path}  verdict=DEAD")
        if c.justification:
            lines.append(f"    reasoning: {c.justification}")
    return "\n".join(lines)


def _run_writeback(args, github, owner, repo, result) -> None:
    flags = [rf for rf in result["risk_flags"] if rf.status != "below_threshold"]
    candidates = [c for c in result["dead_code_candidates"] if c.status != "rejected"]
    print(
        f"\n--post will comment on {len(flags)} PR(s) and file "
        f"{len(candidates)} issue(s) on {owner}/{repo}."
    )
    if not args.yes:
        reply = input("Proceed? [y/N] ").strip().lower()
        if reply not in ("y", "yes"):
            print("Aborted; nothing was written to GitHub.")
            return
    for rf in flags:
        post_risk_comment(github, owner, repo, rf)
        print(f"  commented on PR #{rf.pr_number}")
    for c in candidates:
        node = result["graph"].file(c.file_path)
        assignee = node.primary_owner if node else None
        file_dead_code_issue(github, owner, repo, c, assignee=assignee)
        print(f"  filed issue for {c.file_path}")


def main(argv=None) -> int:
    args = build_arg_parser().parse_args(argv)
    owner, repo = parse_repo_url(args.repo)
    github = _make_github(args)
    llm = _make_llm(args)
    branch = args.branch or github.get_default_branch(owner, repo)
    result = analyze_repo(
        github,
        llm,
        owner,
        repo,
        branch,
        max_files=args.max_files,
        risk_score_threshold=args.risk_threshold,
    )
    print(format_report(result))
    if args.post:
        _run_writeback(args, github, owner, repo, result)
    return 0
```

```python
# src/riskagent/__main__.py
from riskagent.cli import main

raise SystemExit(main())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_cli.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add src/riskagent/cli.py src/riskagent/__main__.py tests/test_cli.py
git commit -m "feat: add python -m riskagent CLI with text report"
```

---

### Task 7: CLI `--post` writeback path

**Files:**
- Modify: `tests/test_cli.py` (add two tests — the `_run_writeback` implementation already landed in Task 6; this task locks its behavior with tests)

**Interfaces:**
- Consumes: `main` and `_run_writeback` from Task 6, `post_risk_comment` / `file_dead_code_issue` (patched in tests).
- Produces: no new code. Verifies that `--post` without `--yes` prompts and writes nothing on a "no" answer, and that `--post --yes` calls both writeback functions, passing the file's `primary_owner` as the issue assignee.

- [ ] **Step 1: Write the failing tests**

```python
# append to tests/test_cli.py
from riskagent.models import FileNode


def _writeback_result():
    return {
        "graph": DependencyGraph([FileNode(path="old.py", primary_owner="alice")], []),
        "risk_flags": [
            RiskFlag(
                pr_number=1,
                score=5.0,
                affected_files=[],
                affected_owners=[],
                status="pending",
            )
        ],
        "dead_code_candidates": [
            DeadCodeCandidate(
                file_path="old.py", reason="x", verdict=True, status="pending"
            )
        ],
    }


@patch("riskagent.cli.file_dead_code_issue")
@patch("riskagent.cli.post_risk_comment")
@patch("riskagent.cli.analyze_repo")
@patch("riskagent.cli._make_llm")
@patch("riskagent.cli._make_github")
def test_post_declined_writes_nothing(
    mock_github, mock_llm, mock_analyze, mock_comment, mock_issue, monkeypatch
):
    gh = Mock()
    gh.get_default_branch.return_value = "main"
    mock_github.return_value = gh
    mock_analyze.return_value = _writeback_result()
    monkeypatch.setattr("builtins.input", lambda _prompt: "n")

    main(["o/r", "--dry-run", "--post"])

    mock_comment.assert_not_called()
    mock_issue.assert_not_called()


@patch("riskagent.cli.file_dead_code_issue")
@patch("riskagent.cli.post_risk_comment")
@patch("riskagent.cli.analyze_repo")
@patch("riskagent.cli._make_llm")
@patch("riskagent.cli._make_github")
def test_post_with_yes_calls_writeback(
    mock_github, mock_llm, mock_analyze, mock_comment, mock_issue
):
    gh = Mock()
    gh.get_default_branch.return_value = "main"
    mock_github.return_value = gh
    mock_analyze.return_value = _writeback_result()

    main(["o/r", "--dry-run", "--post", "--yes"])

    mock_comment.assert_called_once()
    mock_issue.assert_called_once()
    _, kwargs = mock_issue.call_args
    assert kwargs["assignee"] == "alice"
```

- [ ] **Step 2: Run tests to verify they pass**

Run: `pytest tests/test_cli.py -v`
Expected: PASS (6 passed — the 4 from Task 6 plus these 2). If either new test fails, fix `_run_writeback` in `src/riskagent/cli.py` until both pass.

- [ ] **Step 3: Commit**

```bash
git add tests/test_cli.py
git commit -m "test: lock CLI --post writeback confirmation behavior"
```

---

### Task 8: Packaging, README, and full-suite verification

**Files:**
- Create: `requirements.txt`
- Create: `README.md`

**Interfaces:**
- Consumes: everything above. No code interface.
- Produces: a `requirements.txt` an engineer can `pip install -r`, and a `README.md` that documents the CLI. Ends with a full test-suite run.

- [ ] **Step 1: Write `requirements.txt`**

```
# requirements.txt
requests>=2.31
pytest>=8.0
```

- [ ] **Step 2: Write `README.md`**

```markdown
# riskagent — Codebase Change-Risk & Dead-Code Agent (portable core)

The portable Python logic behind a Palantir AIP submission: given a public
GitHub repo it builds a Python import graph, scores how far each open PR's
changes could ripple, resolves file owners, flags stale unreferenced files
as dead-code candidates, and uses an LLM to separate true-dead files from
false positives and to write human-readable justifications. It can then
post a PR comment / file a cleanup issue on GitHub.

In the Foundry build these modules map onto a Code Repository transform, an
Ontology, AIP Logic agents, and Workshop Actions — see
`docs/foundry_mapping.md`. This repo is the logic, runnable locally.

## Install

    pip install -r requirements.txt

Tests (no network, no API keys needed):

    pytest -q

## Run the CLI

Set credentials as environment variables:

    export GITHUB_TOKEN=ghp_...            # https://github.com/settings/tokens
    export GEMINI_API_KEY=...              # https://aistudio.google.com/apikey

Analyze a repo (Gemini does the judgment calls):

    python -m riskagent https://github.com/pallets/click --max-files 40

Dry run — no Gemini key, canned verdicts, exercises the GitHub + graph half:

    python -m riskagent pallets/click --dry-run --max-files 40

Actually post findings to GitHub (needs a token with `repo` / `public_repo`
write scope; prompts before writing unless `--yes`):

    python -m riskagent your-name/your-repo --post

### Flags

| Flag | Meaning |
|---|---|
| `--branch NAME` | Branch to analyze (default: the repo's default branch) |
| `--max-files N` | Only analyze the first N Python files (rate-limit safety) |
| `--risk-threshold X` | Only write a justification for PRs scoring >= X |
| `--dry-run` | Use the offline scripted LLM client (no `GEMINI_API_KEY`) |
| `--model NAME` | Gemini model (default `gemini-2.0-flash`; `gemini-1.5-flash` also works) |
| `--post` | Post PR comments / file issues for findings |
| `--yes` | Skip the `--post` confirmation prompt |

## The LLM seam

`riskagent.agent.judgment` calls an `LLMClient` — a one-method Protocol,
`complete(system_prompt, user_prompt) -> str`. Implementations:

- `GeminiLLMClient` — live, calls the Gemini API.
- `ScriptedLLMClient` — offline canned responses for `--dry-run`.
- `FakeLLMClient` — test-only, driven by a responder callback.

To move to Foundry, write one more implementation backed by the AIP Logic
SDK and pass it wherever the CLI passes `GeminiLLMClient`. Nothing else
changes. The exact system prompts to configure the AIP Logic agents with
are in `src/riskagent/agent/prompts.py`.
```

- [ ] **Step 3: Run the full test suite**

Run: `pytest -q`
Expected: `82 passed` (57 existing + 25 added across Tasks 1–7). If you merged or split test cases the count will differ — what matters is that every test passes and there are no errors.

- [ ] **Step 4: Commit**

```bash
git add requirements.txt README.md
git commit -m "docs: add requirements.txt and CLI README"
```

---

### Task 9: Update the Foundry mapping doc

**Files:**
- Modify: `docs/foundry_mapping.md`

**Interfaces:**
- Consumes: knowledge of the modules added in Tasks 1–8. No code interface.
- Produces: the mapping doc gains a short section describing the local-demo entrypoint and naming the exact swap point for the AIP Logic client, so whoever does the Foundry wiring knows what the local CLI stands in for.

- [ ] **Step 1: Append this section to `docs/foundry_mapping.md`**

```markdown

## Local runnable demo (stand-in for the Workshop app + AIP Logic)

`python -m riskagent <repo>` (`src/riskagent/cli.py`) runs the same
`analyze_repo` orchestration the Workshop "Analyze" button will trigger,
and its `--post` path calls the same `riskagent.actions.writeback`
functions the Workshop Action buttons will call. It exists to validate the
analysis logic against real repositories before the Foundry build.

| Local demo piece | Foundry/AIP equivalent it stands in for |
|---|---|
| `riskagent.cli.main` / `--post` flow | Workshop app "Analyze" button + per-row "Post comment" / "File issue" Action buttons |
| `riskagent.agent.gemini_client.GeminiLLMClient` | The real **AIP Logic SDK client**. Write one class with the same `complete(system_prompt, user_prompt) -> str` method, calling the three deployed AIP Logic functions, and pass it where `cli._make_llm` passes `GeminiLLMClient`. No other code changes. |
| `riskagent.agent.scripted_client.ScriptedLLMClient` | Nothing — local `--dry-run` convenience only. |
| `GITHUB_TOKEN` env var | The GitHub OAuth App token stored as a Foundry credential the Code Repository transform reads. |

The system prompts in `src/riskagent/agent/prompts.py` are the literal text
to paste into the three AIP Logic function configurations; the JSON
response schema each function must return is documented alongside each
prompt.
```

- [ ] **Step 2: Commit**

```bash
git add docs/foundry_mapping.md
git commit -m "docs: document local demo as stand-in for Workshop + AIP Logic"
```

---

## Self-Review

**1. Spec coverage.** This plan's scope is the "make the existing core locally runnable" slice, not the full design spec (whose Foundry/Ontology/Workshop sections are external platform work — see `docs/handoff-checklist.md`). Against that slice:
- Repo URL input (spec §3 "a public GitHub repository URL") → Task 1.
- Default branch other than `main` (spec §5 Repository.default_branch) → Task 2.
- AIP Logic agent judgment calls, live (spec §8) → Task 3 (Gemini stands in).
- Offline path for development → Task 4.
- GitHub API rate limits, "cap analysis to a subset of files/PRs" (spec §12) → Task 5 `max_files`.
- "flagged as risky" filtering (spec §2, §9) → Task 5 `risk_score_threshold`.
- On-demand trigger + results view (spec §10 steps 2–3) → Task 6 CLI + `format_report`.
- Writeback actions with a human-in-the-loop checkpoint (spec §9) → Task 7 `--post` with confirmation.
- Foundry mapping stays current (spec §4, plan Task 11 of the prior plan) → Task 9.

**2. Placeholder scan.** No "TBD"/"handle edge cases"/"similar to Task N"/"write tests for the above" left. Every code step has full code; every test step has full test bodies.

**3. Type consistency.**
- `parse_repo_url(url) -> tuple[str, str]` — used as `owner, repo = parse_repo_url(args.repo)` in `cli.main`. ✓
- `GitHubClient.get_default_branch(owner, repo) -> str` — used as `github.get_default_branch(owner, repo)` in `cli.main`. ✓
- `GeminiLLMClient(api_key, model=..., base_url=..., timeout=...)` / `.complete(system_prompt, user_prompt) -> str` — matches the `LLMClient` Protocol; constructed in `cli._make_llm` with `api_key=`, `model=`. ✓
- `ScriptedLLMClient(dead_code_verdict=, owner=, risk_justification=)` / `.complete(...) -> str` / `.calls` — constructed no-arg in `cli._make_llm`. ✓
- `analyze_repo(github_client, llm_client, owner, repo, branch="main", *, max_files=None, risk_score_threshold=0.0)` — called in `cli.main` with positional `github, llm, owner, repo, branch` and keyword `max_files=`, `risk_score_threshold=`; called in tests with `max_files=1` and `risk_score_threshold=99.0`. ✓
- `DependencyGraph.file(path) -> FileNode | None` — used as `result["graph"].file(c.file_path)` in `cli._run_writeback`. ✓
- `post_risk_comment(client, owner, repo, risk_flag)` and `file_dead_code_issue(client, owner, repo, candidate, assignee=None)` — existing signatures in `riskagent.actions.writeback`; called that way in `_run_writeback` (`assignee=` keyword). ✓
- `RiskFlag.status` values used: `"pending"` (existing), `"below_threshold"` (new, Task 5), `"posted"` (set by `post_risk_comment`). `DeadCodeCandidate.status`: `"pending"` / `"rejected"` (existing), `"issue_filed"` (set by `file_dead_code_issue`). The CLI only reads these, never invents new ones. ✓

---

## Execution Handoff

**Plan complete and saved to `docs/superpowers/plans/2026-08-30-local-runnable-demo.md`. Two execution options:**

**1. Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration.

**2. Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints.

**Which approach?**
