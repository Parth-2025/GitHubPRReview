# src/riskagent/cli.py
import argparse
import os

from riskagent.actions.writeback import file_dead_code_issue, post_risk_comment
from riskagent.agent.gemini_client import GeminiLLMClient
from riskagent.agent.scripted_client import ScriptedLLMClient
from riskagent.github.client import GitHubClient
from riskagent.pipeline import analyze_repo
from riskagent.repo_url import parse_repo_url


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="riskagent",
        description="Analyze a public GitHub repo for change-risk and dead code.",
    )
    parser.add_argument("repo", help="GitHub repo URL or owner/repo shorthand")
    parser.add_argument(
        "--branch", default=None, help="Branch to analyze (default: the repo's default branch)"
    )
    parser.add_argument(
        "--max-files",
        type=int,
        default=None,
        help=(
            "Only analyze the first N Python files. Truncating the tree disables "
            "dead-code detection, which needs the full import graph."
        ),
    )
    parser.add_argument(
        "--risk-threshold",
        type=float,
        default=0.0,
        help="Only write a justification for PRs scoring at or above this",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Use the offline scripted LLM client (no GEMINI_API_KEY needed)",
    )
    parser.add_argument("--model", default="gemini-3.6-flash", help="Gemini model name")
    parser.add_argument(
        "--timeout",
        type=int,
        default=120,
        help="Per-call Gemini HTTP timeout in seconds (thinking models can be slow)",
    )
    parser.add_argument(
        "--post",
        action="store_true",
        help="Post PR comments / file issues for findings (needs a write-scoped token)",
    )
    parser.add_argument(
        "--yes", action="store_true", help="Skip the confirmation prompt for --post"
    )
    return parser


def _make_github(args) -> GitHubClient:
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        raise SystemExit(
            "GITHUB_TOKEN is not set. Create a token at "
            "https://github.com/settings/tokens and `export GITHUB_TOKEN=...`."
        )
    return GitHubClient(token=token)


def _make_llm(args):
    if args.dry_run:
        return ScriptedLLMClient()
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        raise SystemExit(
            "GEMINI_API_KEY is not set. Get one at https://aistudio.google.com/apikey "
            "and `export GEMINI_API_KEY=...`, or pass --dry-run to use the offline client."
        )
    return GeminiLLMClient(api_key=key, model=args.model, timeout=args.timeout)


def format_report(result: dict) -> str:
    lines = [f"Files analyzed: {len(result['graph'].files)}", "", "== Open PR risk flags =="]
    if not result["risk_flags"]:
        lines.append("  (none)")
    for rf in result["risk_flags"]:
        lines.append(f"  PR #{rf.pr_number}  score={rf.score}  status={rf.status}")
        lines.append(f"    affected files: {', '.join(rf.affected_files) or '(none)'}")
        lines.append(f"    affected owners: {', '.join(rf.affected_owners) or '(none)'}")
        if rf.justification:
            lines.append(f"    reasoning: {rf.justification}")
    lines += ["", "== Dead-code candidates =="]
    if result.get("dead_code_skipped"):
        lines.append(
            "  (skipped: --max-files truncated the import graph, dead-code "
            "detection needs the full repo)"
        )
    elif not result["dead_code_candidates"]:
        lines.append("  (none)")
    for c in result["dead_code_candidates"]:
        if c.status == "rejected":
            lines.append(f"  {c.file_path}  verdict=false-positive (skipped)")
        else:
            lines.append(f"  {c.file_path}  verdict=DEAD")
        if c.justification:
            lines.append(f"    reasoning: {c.justification}")
    return "\n".join(lines)


def _run_writeback(args, github, owner, repo, result) -> None:
    flags = [rf for rf in result["risk_flags"] if rf.status != "below_threshold"]
    candidates = [c for c in result["dead_code_candidates"] if c.status != "rejected"]
    print(
        f"\n--post will comment on {len(flags)} PR(s) and file "
        f"{len(candidates)} issue(s) on {owner}/{repo}."
    )
    if not args.yes:
        reply = input("Proceed? [y/N] ").strip().lower()
        if reply not in ("y", "yes"):
            print("Aborted; nothing was written to GitHub.")
            return
    for rf in flags:
        post_risk_comment(github, owner, repo, rf)
        print(f"  commented on PR #{rf.pr_number}")
    for c in candidates:
        node = result["graph"].file(c.file_path)
        assignee = node.primary_owner if node else None
        file_dead_code_issue(github, owner, repo, c, assignee=assignee)
        print(f"  filed issue for {c.file_path}")


def main(argv=None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    if args.dry_run and args.post:
        parser.error(
            "--dry-run cannot be combined with --post: --dry-run only fakes the "
            "LLM, GitHub writeback would still be live"
        )
    try:
        owner, repo = parse_repo_url(args.repo)
    except ValueError as e:
        raise SystemExit(str(e))
    github = _make_github(args)
    llm = _make_llm(args)
    branch = args.branch or github.get_default_branch(owner, repo)
    result = analyze_repo(
        github,
        llm,
        owner,
        repo,
        branch,
        max_files=args.max_files,
        risk_score_threshold=args.risk_threshold,
    )
    print(format_report(result))
    if args.post:
        _run_writeback(args, github, owner, repo, result)
    return 0
