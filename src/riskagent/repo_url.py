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
