from riskagent.models import FileNode, PullRequest, RiskFlag
from riskagent.parsing.import_parser import build_dependency_edges
from riskagent.analysis.graph import DependencyGraph
from riskagent.analysis.ownership import parse_codeowners, resolve_owner
from riskagent.analysis.dead_code import find_dead_code_candidates
from riskagent.agent.judgment import (
    judge_dead_code_candidate,
    resolve_owner_tiebreak,
    write_risk_justification,
)
from riskagent.agent.llm_client import LLMClient
from riskagent.github.client import GitHubClient


def analyze_repo(
    github_client: GitHubClient, llm_client: LLMClient, owner: str, repo: str, branch: str = "main"
) -> dict:
    paths = github_client.get_repo_tree(owner, repo, branch)
    file_sources = {p: github_client.get_file_content(owner, repo, p, branch) for p in paths}
    codeowners_text = github_client.get_codeowners(owner, repo) or ""
    codeowners = parse_codeowners(codeowners_text)

    file_nodes = []
    for p in paths:
        commits = github_client.get_commit_history(owner, repo, p)
        last_commit_date = commits[0]["date"] if commits else None
        authors = [c["author"] for c in commits]
        resolved_owner, ties = resolve_owner(p, codeowners, authors)
        if ties:
            resolved_owner = resolve_owner_tiebreak(p, ties, llm_client)
        is_entry = p == "main.py" or p.endswith("/main.py") or p.endswith("__init__.py")
        file_nodes.append(
            FileNode(path=p, is_entry_point=is_entry, last_commit_date=last_commit_date, primary_owner=resolved_owner)
        )

    edges = build_dependency_edges(file_sources)
    graph = DependencyGraph(file_nodes, edges)

    prs_raw = github_client.get_open_pull_requests(owner, repo)
    risk_flags = []
    for pr_raw in prs_raw:
        pr = PullRequest(
            number=pr_raw["number"], files_changed=pr_raw["files_changed"], diff_summary=pr_raw["diff_summary"]
        )
        affected = graph.affected_files(pr.files_changed) - set(pr.files_changed)
        owners = sorted({fn.primary_owner for fn in file_nodes if fn.path in affected and fn.primary_owner})
        score = graph.blast_radius_score(pr.files_changed)
        risk_flag = RiskFlag(
            pr_number=pr.number, score=score, affected_files=sorted(affected), affected_owners=owners
        )
        risk_flag = write_risk_justification(risk_flag, pr, llm_client)
        risk_flags.append(risk_flag)

    candidates = find_dead_code_candidates(graph)
    judged_candidates = []
    for candidate in candidates:
        content = file_sources.get(candidate.file_path, "")
        judged_candidates.append(judge_dead_code_candidate(candidate, content, llm_client))

    return {"graph": graph, "risk_flags": risk_flags, "dead_code_candidates": judged_candidates}
