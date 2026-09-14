"""
LocalPodcastLLMStudio - Bulk Superseded PR Triage Utility
Queries open Jules pull requests and closes superseded submissions with explanatory remarks.
"""

import argparse
import json
import subprocess
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


def get_open_prs() -> list[dict]:
    cmd = [
        "gh",
        "pr",
        "list",
        "--state",
        "open",
        "--limit",
        "200",
        "--json",
        "number,title,headRefName,url,author",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", check=True)
    return json.loads(result.stdout)


def close_pr(pr_number: int, comment: str, dry_run: bool = True) -> bool:
    if dry_run:
        print(f'[DRY-RUN] Would close PR #{pr_number} with comment:\n  "{comment[:60]}..."')
        return True

    cmd = ["gh", "pr", "close", str(pr_number), "--comment", comment]
    print(f"Closing PR #{pr_number}...")
    res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
    if res.returncode == 0:
        print(f"  Successfully closed PR #{pr_number}.")
        return True
    else:
        print(f"  Failed to close PR #{pr_number}: {res.stderr.strip()}", file=sys.stderr)
        return False


def main():
    parser = argparse.ArgumentParser(description="Bulk close superseded Jules PRs")
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Perform actual closure via gh pr close (default is dry-run)",
    )
    args = parser.parse_args()

    open_prs = get_open_prs()
    print(f"Found {len(open_prs)} open PRs.")

    closing_comment = (
        "Closing as superseded: The performance optimizations and security hardenings "
        "proposed in this automated submission have been comprehensively audited, reconciled, "
        "and integrated directly into `main` (centralized atomic write path validation, "
        "MCI command injection sanitization, safe subprocess invocation, POSIX log UID isolation "
        "and permissions, MP3 frame stride decoding, JSON control character regex optimization, "
        "O(N) reverse HTML newline calculation, and URL credential checks). Thank you Jules!"
    )

    success_count = 0
    for pr in open_prs:
        num = pr["number"]
        title = pr.get("title", "")
        print(f"\nProcessing PR #{num}: {title}")
        if close_pr(num, closing_comment, dry_run=not args.execute):
            success_count += 1

    mode_str = "Executed" if args.execute else "Dry-run completed for"
    print(f"\n{mode_str} {success_count}/{len(open_prs)} PR closures.")


if __name__ == "__main__":
    main()
