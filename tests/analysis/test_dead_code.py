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


def test_handles_z_suffixed_timezone_aware_commit_date():
    # Real GitHub API dates are RFC 3339 with a trailing "Z" (e.g.
    # "2025-06-01T00:00:00Z"), which datetime.fromisoformat parses as
    # timezone-aware. This must not raise when compared against `now`.
    now = datetime(2026, 1, 1)
    files = [FileNode(path="orphan.py", last_commit_date="2025-01-01T00:00:00Z")]
    graph = DependencyGraph(files, [])
    candidates = find_dead_code_candidates(graph, cutoff_days=180, now=now)
    assert len(candidates) == 1
    assert candidates[0].file_path == "orphan.py"
