from typing import Optional

from riskagent.github.client import GitHubClient
from riskagent.models import DeadCodeCandidate, RiskFlag


def post_risk_comment(client: GitHubClient, owner: str, repo: str, risk_flag: RiskFlag) -> RiskFlag:
    body = (
        f"**Automated risk assessment** (score: {risk_flag.score})\n\n"
        f"Affected files: {', '.join(risk_flag.affected_files)}\n"
        f"Affected owners: {', '.join(risk_flag.affected_owners)}\n\n"
        f"{risk_flag.justification}"
    )
    client.post_pr_comment(owner, repo, risk_flag.pr_number, body)
    risk_flag.status = "posted"
    return risk_flag


def file_dead_code_issue(
    client: GitHubClient, owner: str, repo: str, candidate: DeadCodeCandidate, assignee: Optional[str] = None
) -> DeadCodeCandidate:
    if candidate.verdict is False or candidate.status == "rejected":
        raise ValueError("Cannot file an issue for a rejected dead-code candidate")
    title = f"Cleanup candidate: {candidate.file_path}"
    body = f"{candidate.justification}\n\nFlagged by automated dead-code analysis."
    client.create_issue(owner, repo, title, body, assignee=assignee, labels=["cleanup-candidate"])
    candidate.status = "issue_filed"
    return candidate
