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
