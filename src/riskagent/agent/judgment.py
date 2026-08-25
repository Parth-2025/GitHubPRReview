import json

from riskagent.agent.llm_client import LLMClient
from riskagent.agent.prompts import (
    DEAD_CODE_JUDGMENT_SYSTEM_PROMPT,
    OWNER_TIEBREAK_SYSTEM_PROMPT,
    RISK_JUSTIFICATION_SYSTEM_PROMPT,
)
from riskagent.models import DeadCodeCandidate, PullRequest, RiskFlag


def judge_dead_code_candidate(candidate: DeadCodeCandidate, file_content: str, llm: LLMClient) -> DeadCodeCandidate:
    user_prompt = (
        f"File path: {candidate.file_path}\n"
        f"Reason flagged: {candidate.reason}\n"
        f"File content:\n{file_content}"
    )
    raw = llm.complete(DEAD_CODE_JUDGMENT_SYSTEM_PROMPT, user_prompt)
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(f"Agent returned non-JSON response for dead-code judgment: {raw!r}") from e
    candidate.verdict = parsed["verdict"] == "dead"
    candidate.justification = parsed["justification"]
    candidate.status = "pending" if candidate.verdict else "rejected"
    return candidate


def resolve_owner_tiebreak(file_path: str, candidate_owners: list[str], llm: LLMClient) -> str:
    user_prompt = f"File path: {file_path}\nTied candidate owners: {', '.join(candidate_owners)}"
    raw = llm.complete(OWNER_TIEBREAK_SYSTEM_PROMPT, user_prompt)
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(f"Agent returned non-JSON response for owner tiebreak: {raw!r}") from e
    return parsed["owner"]


def write_risk_justification(risk_flag: RiskFlag, pr: PullRequest, llm: LLMClient) -> RiskFlag:
    user_prompt = (
        f"PR #{pr.number}: {pr.diff_summary}\n"
        f"Risk score: {risk_flag.score}\n"
        f"Affected files: {', '.join(risk_flag.affected_files)}\n"
        f"Affected owners: {', '.join(risk_flag.affected_owners)}"
    )
    raw = llm.complete(RISK_JUSTIFICATION_SYSTEM_PROMPT, user_prompt)
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(f"Agent returned non-JSON response for risk justification: {raw!r}") from e
    risk_flag.justification = parsed["justification"]
    return risk_flag
