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


def test_blast_radius_score_handles_z_suffixed_timezone_aware_commit_date():
    # Real GitHub API dates are RFC 3339 with a trailing "Z" (e.g.
    # "2025-12-20T00:00:00Z"), which datetime.fromisoformat parses as
    # timezone-aware. This must not raise when compared against `now`.
    now = datetime(2026, 1, 1)
    files = [
        FileNode(path="a.py"),
        FileNode(path="b.py", last_commit_date="2025-12-20T00:00:00Z"),
    ]
    edges = [DependencyEdge(importer="b.py", imported="a.py")]
    g = DependencyGraph(files, edges)
    score = g.blast_radius_score(["a.py"], recent_activity_days=90, now=now)
    assert score == 2.0
