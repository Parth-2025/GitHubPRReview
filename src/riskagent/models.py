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
