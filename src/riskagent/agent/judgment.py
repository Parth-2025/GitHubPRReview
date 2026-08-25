import json

from riskagent.agent.llm_client import LLMClient
from riskagent.agent.prompts import (
    DEAD_CODE_JUDGMENT_SYSTEM_PROMPT,
    OWNER_TIEBREAK_SYSTEM_PROMPT,
    RISK_JUSTIFICATION_SYSTEM_PROMPT,
)
from riskagent.models import DeadCodeCandidate, PullRequest, RiskFlag


def _require_schema(parsed: object, required_keys: list, raw: str, context: str) -> dict:
    """Validate that a parsed LLM response is a dict with the required keys.

    Raises a ValueError in the same style as the existing JSON-decode error
    messages (including the raw response) if the shape is wrong.
    """
    if not isinstance(parsed, dict):
        raise ValueError(f"Agent returned malformed JSON for {context} (expected an object): {raw!r}")
    missing = [key for key in required_keys if key not in parsed]
    if missing:
        raise ValueError(f"Agent returned malformed JSON for {context} (missing {missing}): {raw!r}")
    return parsed


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
    parsed = _require_schema(parsed, ["verdict", "justification"], raw, "dead-code judgment")
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
    parsed = _require_schema(parsed, ["owner"], raw, "owner tiebreak")
    owner = parsed["owner"]
    if owner not in candidate_owners:
        raise ValueError(
            f"Agent chose an owner not in the candidate list: {owner!r} not in {candidate_owners!r}"
        )
    return owner


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
    parsed = _require_schema(parsed, ["justification"], raw, "risk justification")
    risk_flag.justification = parsed["justification"]
    return risk_flag
