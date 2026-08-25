from datetime import datetime, timezone
from typing import Optional

from riskagent.analysis.graph import DependencyGraph, _parse_commit_date
from riskagent.models import DeadCodeCandidate


def find_dead_code_candidates(
    graph: DependencyGraph, cutoff_days: int = 180, now: Optional[datetime] = None
) -> list[DeadCodeCandidate]:
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    candidates = []
    for node in graph.files:
        if node.is_entry_point:
            continue
        if graph.direct_dependents(node.path):
            continue
        if not node.last_commit_date:
            continue
        commit_dt = _parse_commit_date(node.last_commit_date)
        if (now - commit_dt).days < cutoff_days:
            continue
        candidates.append(
            DeadCodeCandidate(
                file_path=node.path,
                reason=f"No inbound imports and no commits in over {cutoff_days} days",
            )
        )
    return candidates
