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
