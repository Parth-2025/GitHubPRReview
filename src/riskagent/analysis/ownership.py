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
