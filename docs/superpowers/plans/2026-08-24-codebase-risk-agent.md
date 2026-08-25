# Codebase Change-Risk & Dead-Code Agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the portable Python core (parsing, deterministic graph analysis, agent-judgment interfaces, GitHub read/writeback) behind the Palantir AIP submission project, structured so each module maps cleanly onto a Foundry Code Repository transform, Ontology object type, AIP Logic function, or Workshop app screen.

**Architecture:** A pure-Python pipeline — GitHub read client → Python `ast`-based import parser → deterministic dependency graph / blast-radius / ownership / dead-code analysis → a pluggable LLM-client interface standing in for AIP Logic agent calls (with a fake implementation for tests, and prompt text that documents exactly what the real AIP Logic agent should be configured with) → GitHub writeback client for PR comments and issues. Everything is unit-tested with mocked HTTP and a fake LLM client, since neither GitHub credentials nor a live AIP instance are available in this environment.

**Tech Stack:** Python 3.11+, `pytest`, `requests` (HTTP calls mocked in tests via `unittest.mock`), standard library `ast`/`json`/`datetime`/`collections`.

**Spec:** `/Users/parthmohan/Desktop/PalantirProject/docs/specs/2026-08-24-codebase-risk-agent-design.md`

## Global Constraints

- Language support is Python only for v1 (import parsing via `ast`).
- Trigger is on-demand only — no webhook/automatic-on-PR-open logic is built here (documented as future work).
- Only public repos with an admin-authorized GitHub client are in scope; no private-repo auth flow is built.
- Writeback (PR comment, GitHub issue) fires only when explicitly invoked — this is the human-in-the-loop checkpoint; nothing posts automatically as a side effect of analysis.
- Dead-code candidates the agent judges as false positives must never reach the writeback step (status `rejected`, not `pending`).
- Blast radius weights dependents with recent commit activity (within `recent_activity_days`, default 90) more heavily than stale ones.
- Dead-code detection cutoff is files with zero direct inbound import edges and no commits within `cutoff_days` (default 180).
- No real network calls or real LLM calls in tests — everything is mocked/faked.

---

## File Structure

```
pytest.ini
src/riskagent/
  __init__.py
  models.py
  parsing/
    __init__.py
    import_parser.py
  analysis/
    __init__.py
    graph.py
    ownership.py
    dead_code.py
  github/
    __init__.py
    client.py
  agent/
    __init__.py
    llm_client.py
    prompts.py
    judgment.py
  actions/
    __init__.py
    writeback.py
  pipeline.py
tests/
  test_models.py
  parsing/test_import_parser.py
  analysis/test_graph.py
  analysis/test_ownership.py
  analysis/test_dead_code.py
  github/test_client.py
  agent/test_judgment.py
  actions/test_writeback.py
  test_pipeline.py
docs/
  foundry_mapping.md
```

---

### Task 1: Project scaffolding and shared data models

**Files:**
- Create: `pytest.ini`
- Create: `src/riskagent/__init__.py`
- Create: `src/riskagent/models.py`
- Test: `tests/test_models.py`

**Interfaces:**
- Produces: `FileNode(path, is_entry_point=False, last_commit_date=None, primary_owner=None)`, `DependencyEdge(importer, imported)`, `PullRequest(number, files_changed, diff_summary, status="open")`, `Owner(handle, files_owned=[])`, `RiskFlag(pr_number, score, affected_files, affected_owners, justification="", status="pending")`, `DeadCodeCandidate(file_path, reason, verdict=None, justification="", status="pending")` — all as `@dataclass` in `src/riskagent/models.py`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_models.py
from riskagent.models import (
    FileNode, DependencyEdge, PullRequest, Owner, RiskFlag, DeadCodeCandidate,
)

def test_file_node_defaults():
    f = FileNode(path="pkg/mod.py")
    assert f.is_entry_point is False
    assert f.last_commit_date is None
    assert f.primary_owner is None

def test_dependency_edge():
    e = DependencyEdge(importer="a.py", imported="b.py")
    assert e.importer == "a.py"
    assert e.imported == "b.py"

def test_pull_request_defaults():
    pr = PullRequest(number=1, files_changed=["a.py"], diff_summary="fix bug")
    assert pr.status == "open"

def test_owner_defaults():
    o = Owner(handle="alice")
    assert o.files_owned == []

def test_risk_flag_defaults():
    r = RiskFlag(pr_number=1, score=2.0, affected_files=["a.py"], affected_owners=["alice"])
    assert r.justification == ""
    assert r.status == "pending"

def test_dead_code_candidate_defaults():
    d = DeadCodeCandidate(file_path="old.py", reason="no inbound edges")
    assert d.verdict is None
    assert d.justification == ""
    assert d.status == "pending"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_models.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'riskagent'`

- [ ] **Step 3: Write scaffolding and implementation**

```ini
# pytest.ini
[pytest]
pythonpath = src
```

```python
# src/riskagent/__init__.py
```

```python
# src/riskagent/models.py
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class FileNode:
    path: str
    is_entry_point: bool = False
    last_commit_date: Optional[str] = None
    primary_owner: Optional[str] = None


@dataclass
class DependencyEdge:
    importer: str
    imported: str


@dataclass
class PullRequest:
    number: int
    files_changed: list
    diff_summary: str
    status: str = "open"


@dataclass
class Owner:
    handle: str
    files_owned: list = field(default_factory=list)


@dataclass
class RiskFlag:
    pr_number: int
    score: float
    affected_files: list
    affected_owners: list
    justification: str = ""
    status: str = "pending"


@dataclass
class DeadCodeCandidate:
    file_path: str
    reason: str
    verdict: Optional[bool] = None
    justification: str = ""
    status: str = "pending"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_models.py -v`
Expected: PASS (6 passed)

- [ ] **Step 5: Commit**

```bash
git add pytest.ini src/riskagent/__init__.py src/riskagent/models.py tests/test_models.py
git commit -m "feat: add shared data models"
```

---

### Task 2: Python import parser and dependency-edge builder

**Files:**
- Create: `src/riskagent/parsing/__init__.py`
- Create: `src/riskagent/parsing/import_parser.py`
- Test: `tests/parsing/test_import_parser.py`

**Interfaces:**
- Consumes: `DependencyEdge` from `riskagent.models` (Task 1).
- Produces: `parse_imports(source: str) -> list[str]`, `build_dependency_edges(files: dict[str, str]) -> list[DependencyEdge]` in `riskagent.parsing.import_parser`.

- [ ] **Step 1: Write the failing test**

```python
# tests/parsing/test_import_parser.py
from riskagent.parsing.import_parser import parse_imports, build_dependency_edges


def test_parse_imports_plain_import():
    source = "import os\nimport pkg.mod\n"
    assert parse_imports(source) == ["os", "pkg.mod"]


def test_parse_imports_from_import():
    source = "from pkg import mod\nfrom pkg.sub import thing\n"
    assert parse_imports(source) == ["pkg", "pkg.sub"]


def test_parse_imports_ignores_relative_imports():
    source = "from . import sibling\n"
    assert parse_imports(source) == []


def test_build_dependency_edges_resolves_within_repo():
    files = {
        "pkg/a.py": "from pkg import b\n",
        "pkg/b.py": "import os\n",
        "pkg/__init__.py": "",
    }
    edges = build_dependency_edges(files)
    assert len(edges) == 1
    assert edges[0].importer == "pkg/a.py"
    assert edges[0].imported == "pkg/__init__.py"


def test_build_dependency_edges_resolves_submodule_import():
    files = {
        "pkg/a.py": "import pkg.sub.mod\n",
        "pkg/sub/mod.py": "",
    }
    edges = build_dependency_edges(files)
    assert len(edges) == 1
    assert edges[0].importer == "pkg/a.py"
    assert edges[0].imported == "pkg/sub/mod.py"


def test_build_dependency_edges_ignores_self_and_external():
    files = {
        "pkg/a.py": "import requests\nimport pkg.a\n",
    }
    edges = build_dependency_edges(files)
    assert edges == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/parsing/test_import_parser.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'riskagent.parsing'`

- [ ] **Step 3: Write implementation**

```python
# src/riskagent/parsing/__init__.py
```

```python
# src/riskagent/parsing/import_parser.py
import ast

from riskagent.models import DependencyEdge


def parse_imports(source: str) -> list:
    tree = ast.parse(source)
    modules = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                modules.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module and node.level == 0:
                modules.append(node.module)
    return modules


def _module_name_for_path(path: str) -> str:
    if path.endswith("/__init__.py"):
        path = path[: -len("/__init__.py")]
    elif path.endswith(".py"):
        path = path[: -len(".py")]
    return path.replace("/", ".")


def build_dependency_edges(files: dict) -> list:
    module_to_path = {_module_name_for_path(p): p for p in files}
    edges = []
    for path, source in files.items():
        try:
            imports = parse_imports(source)
        except SyntaxError:
            continue
        for module in imports:
            matched_path = module_to_path.get(module)
            if matched_path is None:
                for mod_name, mod_path in module_to_path.items():
                    if module.startswith(mod_name + "."):
                        matched_path = mod_path
                        break
            if matched_path and matched_path != path:
                edges.append(DependencyEdge(importer=path, imported=matched_path))
    return edges
```

Note: relative imports (`from . import x`, `node.level > 0`) are intentionally skipped — a documented v1 limitation (see spec section 12), not a bug.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/parsing/test_import_parser.py -v`
Expected: PASS (6 passed)

- [ ] **Step 5: Commit**

```bash
git add src/riskagent/parsing tests/parsing/test_import_parser.py
git commit -m "feat: add Python import parser and dependency-edge builder"
```

---

### Task 3: Dependency graph, dependents, and blast-radius scoring

**Files:**
- Create: `src/riskagent/analysis/__init__.py`
- Create: `src/riskagent/analysis/graph.py`
- Test: `tests/analysis/test_graph.py`

**Interfaces:**
- Consumes: `FileNode`, `DependencyEdge` from `riskagent.models` (Task 1).
- Produces: `DependencyGraph(files: list[FileNode], edges: list[DependencyEdge])` with methods `direct_dependents(path: str) -> set[str]`, `dependents_of(path: str) -> set[str]`, `affected_files(changed_files: list[str]) -> set[str]`, `blast_radius_score(changed_files: list[str], recent_activity_days: int = 90, now: datetime | None = None) -> float`, in `riskagent.analysis.graph`.

- [ ] **Step 1: Write the failing test**

```python
# tests/analysis/test_graph.py
from datetime import datetime, timedelta

from riskagent.models import FileNode, DependencyEdge
from riskagent.analysis.graph import DependencyGraph


def _graph():
    # a.py -> b.py -> c.py  (b and c depend on a transitively being changed... actually
    # edge direction is importer -> imported, so dependents of "a.py" are files that import it)
    files = [
        FileNode(path="a.py"),
        FileNode(path="b.py"),
        FileNode(path="c.py"),
        FileNode(path="d.py"),
    ]
    edges = [
        DependencyEdge(importer="b.py", imported="a.py"),
        DependencyEdge(importer="c.py", imported="b.py"),
    ]
    return DependencyGraph(files, edges)


def test_direct_dependents():
    g = _graph()
    assert g.direct_dependents("a.py") == {"b.py"}
    assert g.direct_dependents("d.py") == set()


def test_dependents_of_is_transitive():
    g = _graph()
    assert g.dependents_of("a.py") == {"b.py", "c.py"}


def test_affected_files_includes_changed_and_dependents():
    g = _graph()
    assert g.affected_files(["a.py"]) == {"a.py", "b.py", "c.py"}


def test_blast_radius_score_weights_recent_activity():
    now = datetime(2026, 1, 1)
    files = [
        FileNode(path="a.py"),
        FileNode(path="b.py", last_commit_date=(now - timedelta(days=10)).isoformat()),
        FileNode(path="c.py", last_commit_date=(now - timedelta(days=400)).isoformat()),
    ]
    edges = [
        DependencyEdge(importer="b.py", imported="a.py"),
        DependencyEdge(importer="c.py", imported="a.py"),
    ]
    g = DependencyGraph(files, edges)
    score = g.blast_radius_score(["a.py"], recent_activity_days=90, now=now)
    # b.py is recent (weight 2.0), c.py is stale (weight 1.0)
    assert score == 3.0


def test_blast_radius_score_excludes_changed_files():
    g = _graph()
    score = g.blast_radius_score(["c.py"], now=datetime(2026, 1, 1))
    assert score == 0.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/analysis/test_graph.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'riskagent.analysis'`

- [ ] **Step 3: Write implementation**

```python
# src/riskagent/analysis/__init__.py
```

```python
# src/riskagent/analysis/graph.py
from collections import deque
from datetime import datetime


class DependencyGraph:
    def __init__(self, files, edges):
        self.files = files
        self.edges = edges
        self._file_by_path = {f.path: f for f in files}
        self._reverse = {f.path: set() for f in files}
        for e in edges:
            self._reverse.setdefault(e.imported, set()).add(e.importer)

    def direct_dependents(self, path: str) -> set:
        return set(self._reverse.get(path, set()))

    def dependents_of(self, path: str) -> set:
        visited = set()
        queue = deque(self._reverse.get(path, set()))
        while queue:
            current = queue.popleft()
            if current in visited:
                continue
            visited.add(current)
            for parent in self._reverse.get(current, set()):
                if parent not in visited:
                    queue.append(parent)
        return visited

    def affected_files(self, changed_files: list) -> set:
        affected = set(changed_files)
        for cf in changed_files:
            affected |= self.dependents_of(cf)
        return affected

    def blast_radius_score(self, changed_files: list, recent_activity_days: int = 90, now=None) -> float:
        now = now or datetime.utcnow()
        affected = self.affected_files(changed_files) - set(changed_files)
        score = 0.0
        for path in affected:
            node = self._file_by_path.get(path)
            weight = 1.0
            if node and node.last_commit_date:
                commit_dt = datetime.fromisoformat(node.last_commit_date)
                if (now - commit_dt).days <= recent_activity_days:
                    weight = 2.0
            score += weight
        return score
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/analysis/test_graph.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add src/riskagent/analysis/__init__.py src/riskagent/analysis/graph.py tests/analysis/test_graph.py
git commit -m "feat: add dependency graph with blast-radius scoring"
```

---

### Task 4: Ownership resolution (CODEOWNERS + commit-history fallback)

**Files:**
- Create: `src/riskagent/analysis/ownership.py`
- Test: `tests/analysis/test_ownership.py`

**Interfaces:**
- Produces: `parse_codeowners(text: str) -> dict[str, str]`, `match_codeowners(file_path: str, codeowners: dict[str, str]) -> str | None`, `resolve_owner(file_path: str, codeowners: dict[str, str], commit_authors: list[str]) -> tuple[str | None, list[str]]` (second element is the tie list, non-empty only when ambiguous) in `riskagent.analysis.ownership`.

- [ ] **Step 1: Write the failing test**

```python
# tests/analysis/test_ownership.py
from riskagent.analysis.ownership import parse_codeowners, match_codeowners, resolve_owner


def test_parse_codeowners_basic():
    text = "# comment\npkg/ @alice\ndocs/ @bob\n"
    assert parse_codeowners(text) == {"pkg": "alice", "docs": "bob"}


def test_parse_codeowners_ignores_blank_and_malformed_lines():
    text = "\n   \npkg/onlyowner\npkg/ @alice\n"
    assert parse_codeowners(text) == {"pkg": "alice"}


def test_match_codeowners_picks_longest_prefix():
    codeowners = {"pkg": "alice", "pkg/sub": "bob"}
    assert match_codeowners("pkg/sub/mod.py", codeowners) == "bob"
    assert match_codeowners("pkg/other.py", codeowners) == "alice"
    assert match_codeowners("unrelated.py", codeowners) is None


def test_resolve_owner_prefers_codeowners():
    owner, ties = resolve_owner("pkg/mod.py", {"pkg": "alice"}, ["bob", "bob", "carol"])
    assert owner == "alice"
    assert ties == []


def test_resolve_owner_falls_back_to_most_frequent_committer():
    owner, ties = resolve_owner("pkg/mod.py", {}, ["bob", "bob", "carol"])
    assert owner == "bob"
    assert ties == []


def test_resolve_owner_reports_tie_when_ambiguous():
    owner, ties = resolve_owner("pkg/mod.py", {}, ["bob", "carol"])
    assert owner is None
    assert ties == ["bob", "carol"]


def test_resolve_owner_none_when_no_data():
    owner, ties = resolve_owner("pkg/mod.py", {}, [])
    assert owner is None
    assert ties == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/analysis/test_ownership.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'riskagent.analysis.ownership'`

- [ ] **Step 3: Write implementation**

```python
# src/riskagent/analysis/ownership.py
from collections import Counter
from typing import Optional


def parse_codeowners(text: str) -> dict[str, str]:
    owners = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) < 2 or not parts[1].startswith("@"):
            continue
        pattern, owner = parts[0], parts[1]
        owners[pattern.rstrip("/").lstrip("/")] = owner.lstrip("@")
    return owners


def match_codeowners(file_path: str, codeowners: dict[str, str]) -> Optional[str]:
    best_match = None
    best_len = -1
    for pattern, owner in codeowners.items():
        if file_path == pattern or file_path.startswith(pattern + "/"):
            if len(pattern) > best_len:
                best_len = len(pattern)
                best_match = owner
    return best_match


def resolve_owner(file_path: str, codeowners: dict[str, str], commit_authors: list[str]) -> tuple[Optional[str], list[str]]:
    owner = match_codeowners(file_path, codeowners)
    if owner:
        return owner, []
    if not commit_authors:
        return None, []
    counts = Counter(commit_authors)
    max_count = max(counts.values())
    top = sorted(a for a, c in counts.items() if c == max_count)
    if len(top) == 1:
        return top[0], []
    return None, top
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/analysis/test_ownership.py -v`
Expected: PASS (7 passed)

- [ ] **Step 5: Commit**

```bash
git add src/riskagent/analysis/ownership.py tests/analysis/test_ownership.py
git commit -m "feat: add CODEOWNERS/commit-history ownership resolution"
```

---

### Task 5: Deterministic dead-code candidate detection

**Files:**
- Create: `src/riskagent/analysis/dead_code.py`
- Test: `tests/analysis/test_dead_code.py`

**Interfaces:**
- Consumes: `DependencyGraph` (Task 3), `DeadCodeCandidate` from `riskagent.models` (Task 1).
- Produces: `find_dead_code_candidates(graph: DependencyGraph, cutoff_days: int = 180, now: datetime | None = None) -> list[DeadCodeCandidate]` in `riskagent.analysis.dead_code`.

- [ ] **Step 1: Write the failing test**

```python
# tests/analysis/test_dead_code.py
from datetime import datetime, timedelta

from riskagent.models import FileNode, DependencyEdge
from riskagent.analysis.graph import DependencyGraph
from riskagent.analysis.dead_code import find_dead_code_candidates


def test_flags_orphaned_stale_file():
    now = datetime(2026, 1, 1)
    files = [
        FileNode(path="orphan.py", last_commit_date=(now - timedelta(days=200)).isoformat()),
    ]
    graph = DependencyGraph(files, [])
    candidates = find_dead_code_candidates(graph, cutoff_days=180, now=now)
    assert len(candidates) == 1
    assert candidates[0].file_path == "orphan.py"


def test_does_not_flag_file_with_inbound_edge():
    now = datetime(2026, 1, 1)
    files = [
        FileNode(path="used.py", last_commit_date=(now - timedelta(days=200)).isoformat()),
        FileNode(path="caller.py"),
    ]
    edges = [DependencyEdge(importer="caller.py", imported="used.py")]
    graph = DependencyGraph(files, edges)
    candidates = find_dead_code_candidates(graph, cutoff_days=180, now=now)
    assert candidates == []


def test_does_not_flag_recently_modified_orphan():
    now = datetime(2026, 1, 1)
    files = [FileNode(path="new.py", last_commit_date=(now - timedelta(days=5)).isoformat())]
    graph = DependencyGraph(files, [])
    assert find_dead_code_candidates(graph, cutoff_days=180, now=now) == []


def test_does_not_flag_entry_point():
    now = datetime(2026, 1, 1)
    files = [
        FileNode(path="main.py", is_entry_point=True, last_commit_date=(now - timedelta(days=400)).isoformat()),
    ]
    graph = DependencyGraph(files, [])
    assert find_dead_code_candidates(graph, cutoff_days=180, now=now) == []


def test_does_not_flag_file_with_no_commit_date():
    now = datetime(2026, 1, 1)
    files = [FileNode(path="unknown.py", last_commit_date=None)]
    graph = DependencyGraph(files, [])
    assert find_dead_code_candidates(graph, cutoff_days=180, now=now) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/analysis/test_dead_code.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'riskagent.analysis.dead_code'`

- [ ] **Step 3: Write implementation**

```python
# src/riskagent/analysis/dead_code.py
from datetime import datetime
from typing import Optional

from riskagent.analysis.graph import DependencyGraph
from riskagent.models import DeadCodeCandidate


def find_dead_code_candidates(
    graph: DependencyGraph, cutoff_days: int = 180, now: Optional[datetime] = None
) -> list[DeadCodeCandidate]:
    now = now or datetime.utcnow()
    candidates = []
    for node in graph.files:
        if node.is_entry_point:
            continue
        if graph.direct_dependents(node.path):
            continue
        if not node.last_commit_date:
            continue
        commit_dt = datetime.fromisoformat(node.last_commit_date)
        if (now - commit_dt).days < cutoff_days:
            continue
        candidates.append(
            DeadCodeCandidate(
                file_path=node.path,
                reason=f"No inbound imports and no commits in over {cutoff_days} days",
            )
        )
    return candidates
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/analysis/test_dead_code.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add src/riskagent/analysis/dead_code.py tests/analysis/test_dead_code.py
git commit -m "feat: add deterministic dead-code candidate detection"
```

---

### Task 6: GitHub read client

**Files:**
- Create: `src/riskagent/github/__init__.py`
- Create: `src/riskagent/github/client.py`
- Test: `tests/github/test_client.py`

**Interfaces:**
- Produces: `GitHubClient(token: str, base_url: str = "https://api.github.com")` with methods `get_repo_tree(owner, repo, branch="main") -> list[str]`, `get_file_content(owner, repo, path, ref="main") -> str`, `get_codeowners(owner, repo) -> str | None`, `get_commit_history(owner, repo, path) -> list[dict]` (each `{"author": str, "date": str}`), `get_open_pull_requests(owner, repo) -> list[dict]` (each `{"number": int, "files_changed": list[str], "diff_summary": str}`), `post_pr_comment(owner, repo, pr_number, body) -> dict`, `create_issue(owner, repo, title, body, assignee=None, labels=None) -> dict`, in `riskagent.github.client`.

- [ ] **Step 1: Write the failing test**

```python
# tests/github/test_client.py
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/github/test_client.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'riskagent.github'`

- [ ] **Step 3: Write implementation**

```python
# src/riskagent/github/__init__.py
```

```python
# src/riskagent/github/client.py
import base64
from typing import Optional

import requests


class GitHubClient:
    def __init__(self, token: str, base_url: str = "https://api.github.com"):
        self.token = token
        self.base_url = base_url.rstrip("/")

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}", "Accept": "application/vnd.github+json"}

    def get_repo_tree(self, owner: str, repo: str, branch: str = "main") -> list[str]:
        url = f"{self.base_url}/repos/{owner}/{repo}/git/trees/{branch}"
        resp = requests.get(url, headers=self._headers(), params={"recursive": "1"})
        resp.raise_for_status()
        data = resp.json()
        return [
            item["path"]
            for item in data.get("tree", [])
            if item.get("type") == "blob" and item["path"].endswith(".py")
        ]

    def get_file_content(self, owner: str, repo: str, path: str, ref: str = "main") -> str:
        url = f"{self.base_url}/repos/{owner}/{repo}/contents/{path}"
        resp = requests.get(url, headers=self._headers(), params={"ref": ref})
        resp.raise_for_status()
        data = resp.json()
        return base64.b64decode(data["content"]).decode("utf-8")

    def get_codeowners(self, owner: str, repo: str) -> Optional[str]:
        for path in (".github/CODEOWNERS", "CODEOWNERS", "docs/CODEOWNERS"):
            try:
                return self.get_file_content(owner, repo, path)
            except requests.HTTPError as e:
                if e.response is not None and e.response.status_code == 404:
                    continue
                raise
        return None

    def get_commit_history(self, owner: str, repo: str, path: str) -> list[dict]:
        url = f"{self.base_url}/repos/{owner}/{repo}/commits"
        resp = requests.get(url, headers=self._headers(), params={"path": path})
        resp.raise_for_status()
        commits = resp.json()
        return [
            {"author": c["commit"]["author"]["name"], "date": c["commit"]["author"]["date"]}
            for c in commits
        ]

    def get_open_pull_requests(self, owner: str, repo: str) -> list[dict]:
        url = f"{self.base_url}/repos/{owner}/{repo}/pulls"
        resp = requests.get(url, headers=self._headers(), params={"state": "open"})
        resp.raise_for_status()
        prs = resp.json()
        result = []
        for pr in prs:
            files_url = f"{self.base_url}/repos/{owner}/{repo}/pulls/{pr['number']}/files"
            files_resp = requests.get(files_url, headers=self._headers())
            files_resp.raise_for_status()
            files = [f["filename"] for f in files_resp.json()]
            result.append({"number": pr["number"], "files_changed": files, "diff_summary": pr.get("title", "")})
        return result

    def post_pr_comment(self, owner: str, repo: str, pr_number: int, body: str) -> dict:
        url = f"{self.base_url}/repos/{owner}/{repo}/issues/{pr_number}/comments"
        resp = requests.post(url, headers=self._headers(), json={"body": body})
        resp.raise_for_status()
        return resp.json()

    def create_issue(
        self,
        owner: str,
        repo: str,
        title: str,
        body: str,
        assignee: Optional[str] = None,
        labels: Optional[list[str]] = None,
    ) -> dict:
        url = f"{self.base_url}/repos/{owner}/{repo}/issues"
        payload = {"title": title, "body": body}
        if assignee:
            payload["assignees"] = [assignee]
        if labels:
            payload["labels"] = labels
        resp = requests.post(url, headers=self._headers(), json=payload)
        resp.raise_for_status()
        return resp.json()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/github/test_client.py -v`
Expected: PASS (7 passed)

- [ ] **Step 5: Commit**

```bash
git add src/riskagent/github tests/github/test_client.py
git commit -m "feat: add GitHub read/writeback API client"
```

---

### Task 7: LLM client interface, fake client, and AIP Logic prompt specs

**Files:**
- Create: `src/riskagent/agent/__init__.py`
- Create: `src/riskagent/agent/llm_client.py`
- Create: `src/riskagent/agent/prompts.py`
- Test: `tests/agent/test_llm_client.py`

**Interfaces:**
- Produces: `LLMClient` (Protocol with `complete(system_prompt: str, user_prompt: str) -> str`), `FakeLLMClient(responder: Callable[[str, str], str])` with `.complete(...)` and `.calls` (list of `(system_prompt, user_prompt)` tuples), in `riskagent.agent.llm_client`. Also `DEAD_CODE_JUDGMENT_SYSTEM_PROMPT`, `OWNER_TIEBREAK_SYSTEM_PROMPT`, `RISK_JUSTIFICATION_SYSTEM_PROMPT` (str constants) in `riskagent.agent.prompts` — these are the literal system prompts to paste into the real AIP Logic agent configuration.

- [ ] **Step 1: Write the failing test**

```python
# tests/agent/test_llm_client.py
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/agent/test_llm_client.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'riskagent.agent'`

- [ ] **Step 3: Write implementation**

```python
# src/riskagent/agent/__init__.py
```

```python
# src/riskagent/agent/llm_client.py
from typing import Callable, Protocol


class LLMClient(Protocol):
    def complete(self, system_prompt: str, user_prompt: str) -> str: ...


class FakeLLMClient:
    def __init__(self, responder: Callable[[str, str], str]):
        self.responder = responder
        self.calls = []

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        self.calls.append((system_prompt, user_prompt))
        return self.responder(system_prompt, user_prompt)
```

```python
# src/riskagent/agent/prompts.py
"""
These are the literal system prompts to configure on the corresponding
AIP Logic functions in Foundry. Each documents the exact JSON response
schema the calling code (riskagent.agent.judgment) expects back.
"""

DEAD_CODE_JUDGMENT_SYSTEM_PROMPT = """You are reviewing a Python file that a deterministic \
static-analysis pass flagged as a dead-code candidate (no other file in the repository imports \
it, and it has not been committed to in a long time). Your job is to catch false positives that \
the static analysis cannot see: the file may be an entry point invoked by a process runner, a \
plugin loaded dynamically (e.g. via importlib or a plugin-registration decorator), referenced \
only from setup.py/pyproject.toml, or a route/handler registered via a decorator rather than a \
direct import.

Respond with a single JSON object and nothing else, in the form:
{"verdict": "dead" | "false_positive", "justification": "<one or two sentences explaining your reasoning, referencing specific evidence from the file>"}
"""

OWNER_TIEBREAK_SYSTEM_PROMPT = """You are picking who should be asked to review a change, given a \
file with no CODEOWNERS entry and multiple contributors tied for the most commits. Consider commit \
recency and any evidence of specialization implied by the file path or contributor names available \
to you, and pick exactly one.

Respond with a single JSON object and nothing else, in the form:
{"owner": "<handle from the candidate list>", "justification": "<one sentence explaining the choice>"}
"""

RISK_JUSTIFICATION_SYSTEM_PROMPT = """You are writing a short, clear comment for a pull request \
reviewer, explaining why a change was flagged as risky. You will be given the PR's changed files, \
a numeric blast-radius score, the list of files transitively affected, and their owners. Write \
plain, specific prose a busy engineer can read in a few seconds - name the riskiest affected files \
and why, not just the score.

Respond with a single JSON object and nothing else, in the form:
{"justification": "<the comment text>"}
"""
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/agent/test_llm_client.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add src/riskagent/agent/__init__.py src/riskagent/agent/llm_client.py src/riskagent/agent/prompts.py tests/agent/test_llm_client.py
git commit -m "feat: add LLM client interface, fake client, and AIP Logic prompt specs"
```

---

### Task 8: Agent judgment functions (dead-code verdict, owner tiebreak, risk justification)

**Files:**
- Create: `src/riskagent/agent/judgment.py`
- Test: `tests/agent/test_judgment.py`

**Interfaces:**
- Consumes: `DeadCodeCandidate`, `RiskFlag`, `PullRequest` from `riskagent.models` (Task 1); `LLMClient`/`FakeLLMClient` (Task 7); prompt constants (Task 7).
- Produces: `judge_dead_code_candidate(candidate: DeadCodeCandidate, file_content: str, llm: LLMClient) -> DeadCodeCandidate`, `resolve_owner_tiebreak(file_path: str, candidate_owners: list[str], llm: LLMClient) -> str`, `write_risk_justification(risk_flag: RiskFlag, pr: PullRequest, llm: LLMClient) -> RiskFlag`, in `riskagent.agent.judgment`.

- [ ] **Step 1: Write the failing test**

```python
# tests/agent/test_judgment.py
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/agent/test_judgment.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'riskagent.agent.judgment'`

- [ ] **Step 3: Write implementation**

```python
# src/riskagent/agent/judgment.py
import json

from riskagent.agent.llm_client import LLMClient
from riskagent.agent.prompts import (
    DEAD_CODE_JUDGMENT_SYSTEM_PROMPT,
    OWNER_TIEBREAK_SYSTEM_PROMPT,
    RISK_JUSTIFICATION_SYSTEM_PROMPT,
)
from riskagent.models import DeadCodeCandidate, PullRequest, RiskFlag


def judge_dead_code_candidate(candidate: DeadCodeCandidate, file_content: str, llm: LLMClient) -> DeadCodeCandidate:
    user_prompt = (
        f"File path: {candidate.file_path}\n"
        f"Reason flagged: {candidate.reason}\n"
        f"File content:\n{file_content}"
    )
    raw = llm.complete(DEAD_CODE_JUDGMENT_SYSTEM_PROMPT, user_prompt)
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(f"Agent returned non-JSON response for dead-code judgment: {raw!r}") from e
    candidate.verdict = parsed["verdict"] == "dead"
    candidate.justification = parsed["justification"]
    candidate.status = "pending" if candidate.verdict else "rejected"
    return candidate


def resolve_owner_tiebreak(file_path: str, candidate_owners: list[str], llm: LLMClient) -> str:
    user_prompt = f"File path: {file_path}\nTied candidate owners: {', '.join(candidate_owners)}"
    raw = llm.complete(OWNER_TIEBREAK_SYSTEM_PROMPT, user_prompt)
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(f"Agent returned non-JSON response for owner tiebreak: {raw!r}") from e
    return parsed["owner"]


def write_risk_justification(risk_flag: RiskFlag, pr: PullRequest, llm: LLMClient) -> RiskFlag:
    user_prompt = (
        f"PR #{pr.number}: {pr.diff_summary}\n"
        f"Risk score: {risk_flag.score}\n"
        f"Affected files: {', '.join(risk_flag.affected_files)}\n"
        f"Affected owners: {', '.join(risk_flag.affected_owners)}"
    )
    raw = llm.complete(RISK_JUSTIFICATION_SYSTEM_PROMPT, user_prompt)
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(f"Agent returned non-JSON response for risk justification: {raw!r}") from e
    risk_flag.justification = parsed["justification"]
    return risk_flag
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/agent/test_judgment.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add src/riskagent/agent/judgment.py tests/agent/test_judgment.py
git commit -m "feat: add agent judgment functions for dead-code, ownership, and risk justification"
```

---

### Task 9: GitHub writeback actions

**Files:**
- Create: `src/riskagent/actions/__init__.py`
- Create: `src/riskagent/actions/writeback.py`
- Test: `tests/actions/test_writeback.py`

**Interfaces:**
- Consumes: `GitHubClient` (Task 6), `RiskFlag`, `DeadCodeCandidate` from `riskagent.models` (Task 1).
- Produces: `post_risk_comment(client: GitHubClient, owner: str, repo: str, risk_flag: RiskFlag) -> RiskFlag`, `file_dead_code_issue(client: GitHubClient, owner: str, repo: str, candidate: DeadCodeCandidate, assignee: str | None = None) -> DeadCodeCandidate`, in `riskagent.actions.writeback`.

- [ ] **Step 1: Write the failing test**

```python
# tests/actions/test_writeback.py
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/actions/test_writeback.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'riskagent.actions'`

- [ ] **Step 3: Write implementation**

```python
# src/riskagent/actions/__init__.py
```

```python
# src/riskagent/actions/writeback.py
from typing import Optional

from riskagent.github.client import GitHubClient
from riskagent.models import DeadCodeCandidate, RiskFlag


def post_risk_comment(client: GitHubClient, owner: str, repo: str, risk_flag: RiskFlag) -> RiskFlag:
    body = (
        f"**Automated risk assessment** (score: {risk_flag.score})\n\n"
        f"Affected files: {', '.join(risk_flag.affected_files)}\n"
        f"Affected owners: {', '.join(risk_flag.affected_owners)}\n\n"
        f"{risk_flag.justification}"
    )
    client.post_pr_comment(owner, repo, risk_flag.pr_number, body)
    risk_flag.status = "posted"
    return risk_flag


def file_dead_code_issue(
    client: GitHubClient, owner: str, repo: str, candidate: DeadCodeCandidate, assignee: Optional[str] = None
) -> DeadCodeCandidate:
    title = f"Cleanup candidate: {candidate.file_path}"
    body = f"{candidate.justification}\n\nFlagged by automated dead-code analysis."
    client.create_issue(owner, repo, title, body, assignee=assignee, labels=["cleanup-candidate"])
    candidate.status = "issue_filed"
    return candidate
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/actions/test_writeback.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add src/riskagent/actions tests/actions/test_writeback.py
git commit -m "feat: add GitHub PR comment and issue writeback actions"
```

---

### Task 10: End-to-end pipeline orchestration

**Files:**
- Create: `src/riskagent/pipeline.py`
- Test: `tests/test_pipeline.py`

**Interfaces:**
- Consumes: everything from Tasks 1-9 (`FileNode`, `PullRequest`, `RiskFlag`, `build_dependency_edges`, `DependencyGraph`, `parse_codeowners`, `resolve_owner`, `find_dead_code_candidates`, `judge_dead_code_candidate`, `resolve_owner_tiebreak`, `write_risk_justification`, `GitHubClient`-shaped object, `LLMClient`-shaped object).
- Produces: `analyze_repo(github_client, llm_client, owner: str, repo: str, branch: str = "main") -> dict` with keys `"graph"` (`DependencyGraph`), `"risk_flags"` (`list[RiskFlag]`), `"dead_code_candidates"` (`list[DeadCodeCandidate]`), in `riskagent.pipeline`. This is the function a Foundry Code Repository transform or a Workshop-triggered Function wraps directly.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_pipeline.py
import json
from unittest.mock import Mock

from riskagent.pipeline import analyze_repo
from riskagent.agent.llm_client import FakeLLMClient


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
            return [{"author": "bob", "date": "2020-01-01T00:00:00"}]
        return [{"author": "alice", "date": "2026-01-01T00:00:00"}]

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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_pipeline.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'riskagent.pipeline'`

- [ ] **Step 3: Write implementation**

```python
# src/riskagent/pipeline.py
from riskagent.models import FileNode, PullRequest, RiskFlag
from riskagent.parsing.import_parser import build_dependency_edges
from riskagent.analysis.graph import DependencyGraph
from riskagent.analysis.ownership import parse_codeowners, resolve_owner
from riskagent.analysis.dead_code import find_dead_code_candidates
from riskagent.agent.judgment import (
    judge_dead_code_candidate,
    resolve_owner_tiebreak,
    write_risk_justification,
)
from riskagent.agent.llm_client import LLMClient
from riskagent.github.client import GitHubClient


def analyze_repo(
    github_client: GitHubClient, llm_client: LLMClient, owner: str, repo: str, branch: str = "main"
) -> dict:
    paths = github_client.get_repo_tree(owner, repo, branch)
    file_sources = {p: github_client.get_file_content(owner, repo, p, branch) for p in paths}
    codeowners_text = github_client.get_codeowners(owner, repo) or ""
    codeowners = parse_codeowners(codeowners_text)

    file_nodes = []
    for p in paths:
        commits = github_client.get_commit_history(owner, repo, p)
        last_commit_date = commits[0]["date"] if commits else None
        authors = [c["author"] for c in commits]
        resolved_owner, ties = resolve_owner(p, codeowners, authors)
        if ties:
            resolved_owner = resolve_owner_tiebreak(p, ties, llm_client)
        is_entry = p.endswith("__init__.py") or p.endswith("main.py")
        file_nodes.append(
            FileNode(path=p, is_entry_point=is_entry, last_commit_date=last_commit_date, primary_owner=resolved_owner)
        )

    edges = build_dependency_edges(file_sources)
    graph = DependencyGraph(file_nodes, edges)

    prs_raw = github_client.get_open_pull_requests(owner, repo)
    risk_flags = []
    for pr_raw in prs_raw:
        pr = PullRequest(
            number=pr_raw["number"], files_changed=pr_raw["files_changed"], diff_summary=pr_raw["diff_summary"]
        )
        affected = graph.affected_files(pr.files_changed) - set(pr.files_changed)
        owners = sorted({fn.primary_owner for fn in file_nodes if fn.path in affected and fn.primary_owner})
        score = graph.blast_radius_score(pr.files_changed)
        risk_flag = RiskFlag(
            pr_number=pr.number, score=score, affected_files=sorted(affected), affected_owners=owners
        )
        risk_flag = write_risk_justification(risk_flag, pr, llm_client)
        risk_flags.append(risk_flag)

    candidates = find_dead_code_candidates(graph)
    judged_candidates = []
    for candidate in candidates:
        content = file_sources.get(candidate.file_path, "")
        judged_candidates.append(judge_dead_code_candidate(candidate, content, llm_client))

    return {"graph": graph, "risk_flags": risk_flags, "dead_code_candidates": judged_candidates}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_pipeline.py -v`
Expected: PASS (1 passed)

- [ ] **Step 5: Run the full test suite**

Run: `pytest -v`
Expected: All tests across every task pass (46 passed).

- [ ] **Step 6: Commit**

```bash
git add src/riskagent/pipeline.py tests/test_pipeline.py
git commit -m "feat: wire full analyze_repo pipeline end-to-end"
```

---

### Task 11: Foundry/AIP mapping documentation

**Files:**
- Create: `docs/foundry_mapping.md`

**Interfaces:**
- Consumes: knowledge of every module built in Tasks 1-10 and the ontology defined in the spec (section 5).
- Produces: a written mapping document; no code interface.

- [ ] **Step 1: Write the mapping document**

```markdown
# Mapping this codebase onto Foundry / AIP

This package is the portable logic behind the Foundry build. Each module maps to a specific
Foundry/AIP construct as follows:

| Local module | Foundry/AIP construct | Notes |
|---|---|---|
| `riskagent.github.client.GitHubClient` (read methods) | Foundry **Code Repository transform** (ingestion) | Wrap `get_repo_tree`, `get_file_content`, `get_codeowners`, `get_commit_history`, `get_open_pull_requests` in a Python transform triggered on-demand by the Workshop button; write results into Foundry datasets. |
| `riskagent.parsing.import_parser` + `riskagent.analysis.*` | Foundry **Code Repository transform** (batch logic) | Runs after ingestion, in the same or a downstream transform, to populate ontology objects below from the raw datasets. |
| `riskagent.models.FileNode` | Ontology object type **File** | properties: path, is_entry_point, last_commit_date, primary_owner |
| `riskagent.models.DependencyEdge` | Ontology **link type** between two File objects | represents an import relationship |
| `riskagent.models.PullRequest` | Ontology object type **PullRequest** | properties: number, files_changed, diff_summary, status |
| `riskagent.models.Owner` | Ontology object type **Owner** | properties: handle, files_owned |
| `riskagent.models.RiskFlag` | Ontology object type **RiskFlag**, linked to a PullRequest | properties: score, affected_files, affected_owners, justification, status |
| `riskagent.models.DeadCodeCandidate` | Ontology object type **DeadCodeCandidate**, linked to a File | properties: reason, verdict, justification, status |
| `riskagent.agent.prompts` (`DEAD_CODE_JUDGMENT_SYSTEM_PROMPT`, `OWNER_TIEBREAK_SYSTEM_PROMPT`, `RISK_JUSTIFICATION_SYSTEM_PROMPT`) | **AIP Logic agent** system prompts | Paste each verbatim into the corresponding AIP Logic function's system prompt field. |
| `riskagent.agent.judgment` functions | **AIP Logic function** call sites | Each function's `llm.complete(...)` call becomes a call to the deployed AIP Logic function from the same Code Repository transform; the `LLMClient` Protocol is the seam — swap `FakeLLMClient` for the real AIP Logic SDK client. |
| `riskagent.actions.writeback` functions | Foundry **Actions** (writeback) | Each becomes an Ontology Action backed by a Function that calls the GitHub API; exposed as a button in the Workshop app next to each RiskFlag/DeadCodeCandidate. |
| `riskagent.pipeline.analyze_repo` | The overall **Workshop app "Analyze" button** handler | Orchestration logic; in Foundry this becomes the sequence of transform + Ontology write + Action-eligibility, triggered when the user clicks Analyze. |

## What still needs building directly in Foundry/AIP (no local equivalent)

- The Ontology itself (object types, link types, and the Actions above) — created in the Ontology Manager.
- The AIP Logic agents — created in AIP Logic Studio, using the prompts in `riskagent.agent.prompts` as their system prompts, with the response JSON schemas documented in the same file.
- The Workshop app — repo-URL input widget, GitHub OAuth/admin-access confirmation, "Analyze" trigger button, results tables for open PRs and dead-code candidates, and per-row "Post comment" / "File issue" Action buttons.
- Wiring the GitHub OAuth App used for admin-level repo access, and storing its token as a Foundry credential the Code Repository transform can read.
```

- [ ] **Step 2: Commit**

```bash
git add docs/foundry_mapping.md
git commit -m "docs: map local modules to Foundry/AIP constructs"
```

---

## Post-plan note (do not act on this during execution — for the final questions round only)

This plan builds and tests the portable logic only. It does not create anything inside the actual Foundry/AIP platform (Ontology, AIP Logic agents, Workshop app, GitHub OAuth App) because those are external SaaS resources with no local API surface — that wiring has to happen by hand in the Foundry/AIP web UI, using `docs/foundry_mapping.md` as the guide, before the demo video can be recorded.
