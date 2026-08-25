from collections import deque
from datetime import datetime, timezone
from typing import Optional

from riskagent.models import FileNode, DependencyEdge


def _parse_commit_date(date_str: str) -> datetime:
    """Parse a commit date string into a timezone-aware UTC datetime.

    Handles both RFC 3339 strings with a trailing "Z" (as returned by the
    real GitHub API) and naive ISO-format strings (as used by some test
    fixtures), normalizing both to timezone-aware UTC so comparisons never
    mix naive and aware datetimes.
    """
    dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


class DependencyGraph:
    def __init__(self, files: list[FileNode], edges: list[DependencyEdge]):
        self.files = files
        self.edges = edges
        self._file_by_path = {f.path: f for f in files}
        self._reverse = {f.path: set() for f in files}
        for e in edges:
            self._reverse.setdefault(e.imported, set()).add(e.importer)

    def direct_dependents(self, path: str) -> set[str]:
        return set(self._reverse.get(path, set()))

    def dependents_of(self, path: str) -> set[str]:
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

    def affected_files(self, changed_files: list[str]) -> set[str]:
        affected = set(changed_files)
        for cf in changed_files:
            affected |= self.dependents_of(cf)
        return affected

    def blast_radius_score(self, changed_files: list[str], recent_activity_days: int = 90, now: Optional[datetime] = None) -> float:
        now = now or datetime.now(timezone.utc)
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        affected = self.affected_files(changed_files) - set(changed_files)
        score = 0.0
        for path in affected:
            node = self._file_by_path.get(path)
            weight = 1.0
            if node and node.last_commit_date:
                commit_dt = _parse_commit_date(node.last_commit_date)
                if (now - commit_dt).days <= recent_activity_days:
                    weight = 2.0
            score += weight
        return score
