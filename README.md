# riskagent — Codebase Change-Risk & Dead-Code Agent (portable core)

The portable Python logic behind a Palantir AIP submission: given a public
GitHub repo it builds a Python import graph, scores how far each open PR's
changes could ripple, resolves file owners, flags stale unreferenced files
as dead-code candidates, and uses an LLM to separate true-dead files from
false positives and to write human-readable justifications. It can then
post a PR comment / file a cleanup issue on GitHub.

In the Foundry build these modules map onto a Code Repository transform, an
Ontology, AIP Logic agents, and Workshop Actions — see
`docs/foundry_mapping.md`. This repo is the logic, runnable locally.

## Install

    pip install -e .

(or `pip install -r requirements.txt`, which does the same editable install
plus pytest). After this, `python -m riskagent ...` works from anywhere — no
`PYTHONPATH=src` needed.

Tests (no network, no API keys needed):

    pytest -q

## Run the CLI

Set credentials as environment variables:

    export GITHUB_TOKEN=ghp_...            # https://github.com/settings/tokens
    export GEMINI_API_KEY=...              # https://aistudio.google.com/apikey

Analyze a repo (Gemini does the judgment calls):

    python -m riskagent https://github.com/pallets/click --max-files 40

Dry run — no Gemini key, canned verdicts, exercises the GitHub + graph half:

    python -m riskagent pallets/click --dry-run --max-files 40

> **Gemini rate limits:** `analyze_repo` makes one LLM call per open PR, per
> dead-code candidate, and per owner tie. On a free-tier Gemini key a
> rate-limit response (HTTP 429) aborts the run. Use `--max-files` to shrink
> the graph (fewer calls) or `--dry-run` to avoid Gemini entirely.

Actually post findings to GitHub (needs a token with `repo` / `public_repo`
write scope; prompts before writing unless `--yes`):

    python -m riskagent your-name/your-repo --post

### Flags

| Flag | Meaning |
|---|---|
| `--branch NAME` | Branch to analyze (default: the repo's default branch) |
| `--max-files N` | Only analyze the first N Python files (rate-limit safety); truncating the tree disables dead-code detection (needs the full import graph) |
| `--risk-threshold X` | Only write a justification for PRs scoring >= X |
| `--dry-run` | Use the offline scripted LLM client (no `GEMINI_API_KEY`) |
| `--model NAME` | Gemini model (default `gemini-2.0-flash`; `gemini-1.5-flash` also works) |
| `--post` | Post PR comments / file issues for findings |
| `--yes` | Skip the `--post` confirmation prompt |

## The LLM seam

`riskagent.agent.judgment` calls an `LLMClient` — a one-method Protocol,
`complete(system_prompt, user_prompt) -> str`. Implementations:

- `GeminiLLMClient` — live, calls the Gemini API.
- `ScriptedLLMClient` — offline canned responses for `--dry-run`.
- `FakeLLMClient` — test-only, driven by a responder callback.

To move to Foundry, write one more implementation backed by the AIP Logic
SDK and pass it wherever the CLI passes `GeminiLLMClient`. Nothing else
changes. The exact system prompts to configure the AIP Logic agents with
are in `src/riskagent/agent/prompts.py`.
