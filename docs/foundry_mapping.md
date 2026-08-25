# Mapping this codebase onto Foundry / AIP

This package is the portable logic behind the Foundry build. Each module maps to a specific
Foundry/AIP construct as follows:

| Local module | Foundry/AIP construct | Notes |
|---|---|---|
| `riskagent.github.client.GitHubClient` (read methods) | Foundry **Code Repository transform** (ingestion) | Wrap `get_repo_tree`, `get_file_content`, `get_codeowners`, `get_commit_history`, `get_open_pull_requests` in a Python transform triggered on-demand by the Workshop button; write results into Foundry datasets. |
| `riskagent.parsing.import_parser` + `riskagent.analysis.*` | Foundry **Code Repository transform** (batch logic) | Runs after ingestion, in the same or a downstream transform, to populate ontology objects below from the raw datasets. |
| `riskagent.models.FileNode` | Ontology object type **File** | properties: path, is_entry_point, last_commit_date, primary_owner |
| `riskagent.models.DependencyEdge` | Ontology **link type** between two File objects | represents an import relationship |
| `riskagent.models.PullRequest` | Ontology object type **PullRequest** | properties: number, files_changed, diff_summary, status |
| `riskagent.models.Owner` | Ontology object type **Owner** | properties: handle, files_owned |
| `riskagent.models.RiskFlag` | Ontology object type **RiskFlag**, linked to a PullRequest | properties: score, affected_files, affected_owners, justification, status |
| `riskagent.models.DeadCodeCandidate` | Ontology object type **DeadCodeCandidate**, linked to a File | properties: reason, verdict, justification, status |
| `riskagent.agent.prompts` (`DEAD_CODE_JUDGMENT_SYSTEM_PROMPT`, `OWNER_TIEBREAK_SYSTEM_PROMPT`, `RISK_JUSTIFICATION_SYSTEM_PROMPT`) | **AIP Logic agent** system prompts | Paste each verbatim into the corresponding AIP Logic function's system prompt field. |
| `riskagent.agent.judgment` functions | **AIP Logic function** call sites | Each function's `llm.complete(...)` call becomes a call to the deployed AIP Logic function from the same Code Repository transform; the `LLMClient` Protocol is the seam — swap `FakeLLMClient` for the real AIP Logic SDK client. |
| `riskagent.actions.writeback` functions | Foundry **Actions** (writeback) | Each becomes an Ontology Action backed by a Function that calls the GitHub API; exposed as a button in the Workshop app next to each RiskFlag/DeadCodeCandidate. |
| `riskagent.pipeline.analyze_repo` | The overall **Workshop app "Analyze" button** handler | Orchestration logic; in Foundry this becomes the sequence of transform + Ontology write + Action-eligibility, triggered when the user clicks Analyze. |

## What still needs building directly in Foundry/AIP (no local equivalent)

- The Ontology itself (object types, link types, and the Actions above) — created in the Ontology Manager.
- The AIP Logic agents — created in AIP Logic Studio, using the prompts in `riskagent.agent.prompts` as their system prompts, with the response JSON schemas documented in the same file.
- The Workshop app — repo-URL input widget, GitHub OAuth/admin-access confirmation, "Analyze" trigger button, results tables for open PRs and dead-code candidates, and per-row "Post comment" / "File issue" Action buttons.
- Wiring the GitHub OAuth App used for admin-level repo access, and storing its token as a Foundry credential the Code Repository transform can read.
