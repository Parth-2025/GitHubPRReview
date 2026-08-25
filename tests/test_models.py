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
