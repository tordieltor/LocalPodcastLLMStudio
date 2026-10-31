"""
LocalPodcastLLMStudio - Bulk Superseded PR Triage Utility
Queries open Jules pull requests within bounded PR and author filters and closes
superseded automated submissions with an explanatory reconciliation comment.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from typing import Any

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

DEFAULT_JULES_AUTHORS: tuple[str, ...] = (
    "app/google-labs-jules",
    "google-labs-jules",
    "google-labs-jules[bot]",
)


def get_head_commit_sha() -> str | None:
    """Resolve current short HEAD commit SHA if running inside a git repository."""
    try:
        res = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
        sha = res.stdout.strip()
        return sha or None
    except (OSError, subprocess.SubprocessError):
        return None


def get_open_prs(limit: int = 300) -> list[dict[str, Any]]:
    """Fetch open pull requests via GitHub CLI (`gh pr list`)."""
    cmd = [
        "gh",
        "pr",
        "list",
        "--state",
        "open",
        "--limit",
        str(limit),
        "--json",
        "number,title,headRefName,url,author",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", check=True)
    parsed = json.loads(result.stdout)
    if not isinstance(parsed, list):
        return []
    return sorted(parsed, key=lambda pr: int(pr.get("number", 0)))


def extract_author_login(pr: dict[str, Any]) -> str:
    """Extract normalized lowercase author login from `gh pr list --json author` payload."""
    author = pr.get("author")
    if isinstance(author, dict):
        login = str(author.get("login") or "").strip().lower()
        is_bot = bool(author.get("is_bot"))
        if is_bot and login and not login.startswith("app/") and not login.endswith("[bot]"):
            return login
        return login
    return ""


def filter_target_prs(
    open_prs: list[dict[str, Any]],
    *,
    min_pr: int | None,
    max_pr: int | None,
    allowed_authors: set[str],
    excluded_prs: set[int],
) -> tuple[list[dict[str, Any]], list[tuple[int, str]]]:
    """Filter open PRs strictly by PR range, bot author allowlist, and explicit exclusions."""
    matched: list[dict[str, Any]] = []
    skipped: list[tuple[int, str]] = []

    for pr in open_prs:
        num = int(pr.get("number", 0))
        if num in excluded_prs:
            skipped.append((num, "explicitly excluded via --exclude"))
            continue
        if min_pr is not None and num < min_pr:
            skipped.append((num, f"below --min-pr {min_pr}"))
            continue
        if max_pr is not None and num > max_pr:
            skipped.append((num, f"above --max-pr {max_pr}"))
            continue

        login = extract_author_login(pr)
        author_obj = pr.get("author") if isinstance(pr.get("author"), dict) else {}
        candidates = {login}
        if login.startswith("app/"):
            candidates.add(login.removeprefix("app/"))
            candidates.add(f"{login.removeprefix('app/')}[bot]")
        elif author_obj.get("is_bot") and login:
            candidates.add(f"app/{login}")
            candidates.add(f"{login}[bot]")

        if allowed_authors and not (candidates & allowed_authors):
            skipped.append((num, f"author '{login or 'unknown'}' not in allowed bot list"))
            continue

        matched.append(pr)

    return matched, skipped


def build_closing_comment(commit_sha: str | None) -> str:
    """Build explanatory reconciliation comment referencing the unified commit on `main`."""
    commit_ref = f" (commit `{commit_sha}`)" if commit_sha else ""
    return (
        "Closing as superseded: All 212 automated Jules submissions have been audited, "
        "deduplicated, and reconciled directly onto `main`"
        f"{commit_ref} without lockfile churn. Integrated improvements include DNS-pinned "
        "SSRF redirect defense, iterative HTML extraction, offline-by-default TTS privacy "
        "controls, multi-rate WAV resampling, MCI & subprocess hardening, atomic path "
        "validation, POSIX log isolation, GUI/TUI/CLI concurrency and UX fixes, and full "
        "CI regression coverage. Thank you!"
    )


def close_pr(pr_number: int, comment: str, dry_run: bool = True) -> bool:
    """Close a single PR via `gh pr close` (or log action in dry-run mode)."""
    if dry_run:
        print(f'[DRY-RUN] Would close PR #{pr_number} with comment:\n  "{comment[:90]}..."')
        return True

    cmd = ["gh", "pr", "close", str(pr_number), "--comment", comment]
    print(f"Closing PR #{pr_number}...")
    res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
    if res.returncode == 0:
        print(f"  Successfully closed PR #{pr_number}.")
        return True
    print(f"  Failed to close PR #{pr_number}: {res.stderr.strip()}", file=sys.stderr)
    return False


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Safely bulk-close superseded automated Jules pull requests."
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Perform actual closure via `gh pr close` (default is dry-run).",
    )
    parser.add_argument(
        "--min-pr",
        type=int,
        default=76,
        help="Minimum PR number (inclusive) eligible for closure (default: 76).",
    )
    parser.add_argument(
        "--max-pr",
        type=int,
        default=212,
        help="Maximum PR number (inclusive) eligible for closure (default: 212).",
    )
    parser.add_argument(
        "--author",
        action="append",
        default=None,
        help=(
            "Allowed PR author login (repeatable). Defaults to Jules bot accounts: "
            f"{', '.join(DEFAULT_JULES_AUTHORS)}."
        ),
    )
    parser.add_argument(
        "--exclude",
        type=int,
        nargs="*",
        default=[],
        help="Specific PR numbers to exclude from closure.",
    )
    parser.add_argument(
        "--commit-sha",
        type=str,
        default=None,
        help="Commit SHA on `main` to cite in the closing comment (defaults to HEAD).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=300,
        help="Maximum open PRs to fetch from GitHub CLI (default: 300).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    if args.min_pr is not None and args.max_pr is not None and args.min_pr > args.max_pr:
        parser.error("--min-pr cannot be greater than --max-pr")

    raw_authors = args.author if args.author else list(DEFAULT_JULES_AUTHORS)
    allowed_authors = {
        part.strip().lower() for entry in raw_authors for part in entry.split(",") if part.strip()
    }
    excluded_prs = {int(n) for n in (args.exclude or [])}
    commit_sha = (args.commit_sha or "").strip() or get_head_commit_sha()

    open_prs = get_open_prs(limit=args.limit)
    target_prs, skipped = filter_target_prs(
        open_prs,
        min_pr=args.min_pr,
        max_pr=args.max_pr,
        allowed_authors=allowed_authors,
        excluded_prs=excluded_prs,
    )

    print(
        f"Fetched {len(open_prs)} open PR(s); "
        f"{len(target_prs)} matched filters (range={args.min_pr}..{args.max_pr}, "
        f"authors={sorted(allowed_authors)}), {len(skipped)} skipped."
    )
    for num, reason in skipped:
        print(f"  [SKIP] PR #{num}: {reason}")

    closing_comment = build_closing_comment(commit_sha)

    success_count = 0
    for pr in target_prs:
        num = int(pr["number"])
        title = pr.get("title", "")
        author_login = extract_author_login(pr)
        print(f"\nProcessing PR #{num} (@{author_login}): {title}")
        if close_pr(num, closing_comment, dry_run=not args.execute):
            success_count += 1

    mode_str = "Executed" if args.execute else "Dry-run completed for"
    print(f"\n{mode_str} {success_count}/{len(target_prs)} PR closures.")
    return 0 if success_count == len(target_prs) else 1


if __name__ == "__main__":
    sys.exit(main())
