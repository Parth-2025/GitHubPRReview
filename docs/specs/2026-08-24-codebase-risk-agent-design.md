# Codebase Change-Risk & Dead-Code Agent — Design Spec

**Date:** 2026-08-24
**Status:** Draft — pending review
**Context:** Palantir AIP Now developer-account submission project. Must be a functional workflow built on Foundry + AIP, not an analytics/visualization exercise — needs a real ontology, an AIP agent that reasons and takes a writeback action, and a clear operational decision informed for a real user.

## 1. Problem

Developers reviewing a pull request often have no easy way to see what else in the codebase a change might break, or who should actually be reviewing it — they either guess or ask around. Separately, codebases accumulate files nobody uses anymore and nobody feels safe deleting, because nobody can quickly tell "definitely dead" from "looks dead but is actually a plugin entry point."

## 2. Users & decisions informed

- **PR author / reviewer**: "Is this change riskier than it looks, and who else needs to weigh in before merge?"
- **Repo maintainer / tech lead**: "Which files are safe to delete as part of cleanup, and who should confirm that?"

The tool doesn't just surface information — it takes the next concrete step (a PR comment, a filed issue) that moves the decision forward, while still leaving the final call (merge, delete) to a human.

## 3. Scope

- Input: a public GitHub repository URL, submitted by a user with admin-level access to that repo (via GitHub OAuth/App authorization).
- Language support: Python only, for v1 (dependency parsing via Python's `ast` module).
- Trigger: on-demand, via a button in a Foundry Workshop app. (Webhook-driven, automatic-on-PR-open triggering is noted as future work, not built for this submission.)
- Out of scope for v1: multi-language support, automatic/webhook triggering, private repos, human-approval step before writeback (writeback fires on a manual button click per finding, which itself is the human-in-the-loop checkpoint).

## 4. Architecture

```
GitHub repo (public URL)
   → Foundry ingestion (Python Code Repository transform, triggered on-demand from Workshop)
   → Ontology (Repository, File, DependencyEdge, PullRequest, Owner, RiskFlag, DeadCodeCandidate)
   → Deterministic analysis functions (blast radius, ownership resolution, dead-code candidate detection)
   → AIP Logic agent (judgment calls + justification writing)
   → Foundry Action → GitHub API (PR comment / GitHub issue)
   → Workshop app (repo input, trigger, results view, writeback buttons)
```

## 5. Ontology (data model)

| Object | Key properties |
|---|---|
| **Repository** | url, default_branch, last_analyzed_at |
| **File** | path, is_entry_point, last_commit_date, primary_owner |
| **DependencyEdge** | link type between two Files, representing an import relationship |
| **PullRequest** | number, files_changed, diff_summary, status |
| **Owner** | handle/name, files_owned |
| **RiskFlag** | linked to a PullRequest; score, justification text, status (pending / posted) |
| **DeadCodeCandidate** | linked to a File; justification text, status (pending / issue_filed / rejected) |

## 6. Ingestion pipeline

A Python transform, triggered on-demand (not scheduled), does the following when the user clicks "Analyze" in the Workshop app:

1. Fetch repo file tree and file contents via the GitHub API.
2. Parse `import` / `from ... import` statements with Python's `ast` module to build `File` and `DependencyEdge` objects.
3. Read `CODEOWNERS` if present; otherwise compute ownership from `git log`/blame (most commits on a file in the last N months).
4. Pull open PRs and their changed-files lists into `PullRequest` objects.

## 7. Deterministic analysis

These run as plain code (Foundry Functions), not the agent, because they need to be exact and reproducible:

- **Blast radius**: BFS/DFS over `DependencyEdge` from each file changed in a PR, counting reachable dependents. Score weights dependents that have recent commit activity more heavily (actively-worked-on code is riskier to break).
- **Ownership resolution**: CODEOWNERS match first; fallback to most-commits-in-last-N-months via blame.
- **Dead-code candidate detection**: files with zero inbound `DependencyEdge`s reachable from any entry point, and no commits in over 6 months, are flagged as *candidates* — not final verdicts.

## 8. Agent design (AIP Logic)

The agent is invoked only where judgment is genuinely required — not for anything the deterministic layer can already answer exactly:

1. **Dead-code judgment**: given a candidate file (path, content preview, why it looks orphaned), decide true-dead vs. false-positive (e.g. `main.py`/`__init__.py`, a dynamically-imported plugin, something referenced in `setup.py`/config, a decorated route handler the static import graph can't see) — with stated reasoning.
2. **Owner tiebreak**: when ownership resolution is ambiguous (no CODEOWNERS match, multiple owners with comparable recent activity), the agent picks and justifies who to notify.
3. **Justification writing**: converts the risk score / blast-radius list, or the dead-code verdict, into a clear, human-readable comment or issue body.

## 9. Actions (writeback)

- **Risk action**: posts a comment on the GitHub PR containing the risk score, the list of affected downstream files and their owners, and the agent's reasoning.
- **Dead-code action**: opens a GitHub issue tagged `cleanup-candidate`, assigned to the resolved owner, with the agent's reasoning in the body.

Both actions fire from a manual button click on a specific finding in the Workshop app — this is the human-in-the-loop checkpoint: the agent proposes, a person triggers the actual write to GitHub.

## 10. Workshop app / user flow

Single-page Workshop app:

1. User pastes a repo URL and confirms GitHub authorization (admin-level access).
2. Clicks "Analyze" → ingestion pipeline + deterministic analysis + agent judgment run.
3. Results view shows two lists:
   - **Open PRs** with risk scores, affected files/owners, agent reasoning, and a "Post comment" button.
   - **Dead-code candidates** with agent verdicts and reasoning, and a "File issue" button (only shown for candidates the agent confirmed, not rejected).

## 11. Demo narrative (< 4 min video)

1. Open on the pain: reviewing a PR with no visibility into what else it touches; codebases quietly accumulating dead files nobody trusts to delete.
2. Paste a real public repo into the app.
3. Show the ontology/graph being built from real data.
4. Show the agent flagging a specific risky PR with its reasoning; click "Post comment" — live on GitHub.
5. Show a dead-code candidate the agent correctly distinguished from a false-positive-looking file (e.g. an entry point); click "File issue" — live on GitHub.
6. Close on impact: time saved per review cycle, safer merges, cleaner codebase over time.

## 12. Open questions / risks

- GitHub API rate limits on larger repos — may need to cap analysis to a subset of files/PRs for the demo.
- Python `ast`-based import parsing won't catch fully dynamic imports (`importlib.import_module(variable)`) — acceptable false-negative for v1, and is itself a good example of exactly the ambiguity the agent's dead-code judgment step is meant to catch.
- Need a GitHub OAuth App (or personal access token for demo purposes) with repo write scope (comments, issues) — must confirm this is permitted under the AIP Now Terms of Service before building.
