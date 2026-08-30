# Your Checklist — what only you can do

Everything in `docs/superpowers/plans/2026-08-30-local-runnable-demo.md` is code I can write and test without you. This file is the rest: the parts that need your accounts, your credentials, the Foundry web UI, or a camera. Work top to bottom.

---

## Part A — Validate the logic locally (~30 min)

Do this first. It proves the analysis is correct before you spend hours wiring Foundry.

- [ ] **A1. Get a GitHub token.**
  1. Go to <https://github.com/settings/tokens> → **Generate new token** → **Fine-grained** (or classic).
  2. Scope: for read-only analysis, `public_repo` (classic) or **Public repositories, read-only** (fine-grained) is enough. If you also want to test `--post` on a repo you own, give it **write** access to Issues and Pull requests on that one repo.
  3. Copy the token. In your terminal:
     ```bash
     export GITHUB_TOKEN=ghp_xxxxxxxxxxxxxxxxxxxx
     ```

- [ ] **A2. Set your Gemini key** (you already have one):
  ```bash
  export GEMINI_API_KEY=your-key-here
  ```
  If you ever need a new one: <https://aistudio.google.com/apikey>.

- [ ] **A3. Install dependencies:**
  ```bash
  cd /Users/parthmohan/Desktop/PalantirProject
  pip install -r requirements.txt
  ```

- [ ] **A4. Run the offline dry run** (no Gemini calls — checks the GitHub + graph half works):
  ```bash
  python -m riskagent pallets/click --dry-run --max-files 40
  ```
  You should see "Files analyzed: 40", an "Open PR risk flags" section, and a "Dead-code candidates" section.

- [ ] **A5. Run for real** (Gemini writes the verdicts and justifications):
  ```bash
  python -m riskagent https://github.com/pallets/click --max-files 40
  ```
  Read the output. Do the risk justifications name real files? Do the dead-code verdicts look sane (entry points / plugins marked `false-positive (skipped)`, genuinely unused files marked `DEAD`)? This is the moment to catch logic bugs.

- [ ] **A6. Pick your demo repo.** You want a small-to-medium **public Python** repo that has **at least one open PR** and ideally an obviously-stale file. Try a few:
  ```bash
  python -m riskagent <owner/repo> --max-files 60
  ```
  Note which repo gives the most convincing before/after story for the video.

- [ ] **A7. (Optional) Test a real writeback** on a throwaway repo **you own**:
  ```bash
  python -m riskagent your-name/your-test-repo --post
  ```
  It prints what it will do and waits for `y`. Confirm the comment/issue actually appears on GitHub, then delete them.

**If A5/A6 output looks wrong:** tell me what's off and I'll fix the analysis code before you move on.

---

## Part B — Build it in Foundry / AIP (the actual submission)

Reference doc while you do this: `docs/foundry_mapping.md` (it maps every local module to the Foundry thing it becomes). The design is in `docs/specs/2026-08-24-codebase-risk-agent-design.md` §5–§10.

- [ ] **B1. Confirm the Terms of Service** allow a GitHub integration with **write** scope (posting comments / issues). Spec §12 flags this as an open question. If write-back isn't allowed, the demo becomes "show the drafted comment" instead of "post it live" — decide this now, it changes B6 and the video.

- [ ] **B2. Create a GitHub OAuth App (or a PAT for the demo).**
  1. <https://github.com/settings/developers> → **New OAuth App** (or reuse the PAT from A1 if a full OAuth App is overkill for a demo).
  2. It needs scope to read repo contents + commits + PRs, and (if B1 allows) write Issues and PR comments.
  3. In Foundry, store the token as a **credential** the Code Repository transform can read. (Foundry: *Data Connection* / *credential store* — exact location depends on your enrollment.)

- [ ] **B3. Build the Ontology** (Foundry → **Ontology Manager**). Create these object types with the properties from spec §5 / `docs/foundry_mapping.md`:
  - **Repository** — url, default_branch, last_analyzed_at
  - **File** — path, is_entry_point, last_commit_date, primary_owner
  - **PullRequest** — number, files_changed, diff_summary, status
  - **Owner** — handle, files_owned
  - **RiskFlag** — score, affected_files, affected_owners, justification, status *(link to PullRequest)*
  - **DeadCodeCandidate** — reason, verdict, justification, status *(link to File)*
  - **DependencyEdge** — a **link type** between two File objects (represents an import)

- [ ] **B4. Create the two writeback Actions** (Ontology Manager → Actions), each backed by a Function that calls the GitHub API:
  - *Post risk comment* — takes a RiskFlag, posts a PR comment (mirrors `riskagent.actions.writeback.post_risk_comment`).
  - *File dead-code issue* — takes a DeadCodeCandidate, opens a `cleanup-candidate` issue assigned to the owner (mirrors `file_dead_code_issue`).

- [ ] **B5. Create the 3 AIP Logic functions** (Foundry → **AIP Logic**). For each, paste the matching system prompt **verbatim** from `src/riskagent/agent/prompts.py` and set the output to the JSON shape documented right next to that prompt:
  - `DEAD_CODE_JUDGMENT_SYSTEM_PROMPT` → returns `{"verdict": "dead"|"false_positive", "justification": "..."}`
  - `OWNER_TIEBREAK_SYSTEM_PROMPT` → returns `{"owner": "...", "justification": "..."}`
  - `RISK_JUSTIFICATION_SYSTEM_PROMPT` → returns `{"justification": "..."}`

- [ ] **B6. Build the Code Repository transform** (Foundry → **Code Repositories**, Python):
  1. Copy `src/riskagent/` into the repo (or `pip install` it as a package).
  2. Write one small class implementing `complete(system_prompt, user_prompt) -> str` that calls your 3 AIP Logic functions from B5. This replaces `GeminiLLMClient` — it's the only swap.
  3. Call `analyze_repo(github_client, aip_logic_client, owner, repo, branch)` and write the results into the B3 ontology objects.
  4. Set the transform to run **on-demand** (triggered from Workshop), not scheduled.

- [ ] **B7. Build the Workshop app** (Foundry → **Workshop**), one page:
  1. A text input for the repo URL + a note confirming GitHub authorization.
  2. An **"Analyze"** button that triggers the B6 transform.
  3. A table of **open PRs** — score, affected files/owners, agent reasoning, and a **"Post comment"** button wired to the B4 action.
  4. A table of **dead-code candidates** — verdict + reasoning, and a **"File issue"** button (show it only for candidates whose `status` is not `rejected`).

- [ ] **B8. End-to-end test in Foundry.** Paste your A6 demo repo, click Analyze, confirm the ontology fills, the agent verdicts appear, and one Post-comment / File-issue click writes to GitHub.

---

## Part C — Record the demo video (< 4 min)

Follow the beats in spec §11. Shot list:

- [ ] **C1.** 20–30s on the pain: a PR with no visibility into what it touches; codebases hoarding files nobody trusts to delete.
- [ ] **C2.** Paste your demo repo URL into the Workshop app, confirm auth.
- [ ] **C3.** Click **Analyze**; show the ontology/graph populating from real data.
- [ ] **C4.** Open a flagged risky PR; read the agent's reasoning aloud; click **Post comment**; cut to the live comment on GitHub.
- [ ] **C5.** Show a dead-code candidate the agent **correctly kept** as DEAD, and one it **correctly rejected** as a false positive (entry point / plugin). Click **File issue** on the real one; cut to the live GitHub issue.
- [ ] **C6.** 15s close on impact: faster review cycles, safer merges, cleaner codebase over time.

- [ ] **C7.** Submit: video + repo link + a short write-up pointing at `docs/specs/...` and `docs/foundry_mapping.md`.

---

## Quick status of everything

| Piece | State |
|---|---|
| Portable Python core (`src/riskagent/`) | ✅ done, 57 tests green |
| Local CLI + Gemini backend + dry-run | ⏳ in the plan I just wrote — I build it next |
| Foundry Ontology / AIP Logic / transform / Workshop | ⬜ Part B — your web-UI work |
| GitHub OAuth App + ToS check | ⬜ B1–B2 — your accounts |
| Demo video | ⬜ Part C — you |
