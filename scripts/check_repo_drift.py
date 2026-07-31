#!/usr/bin/env python3
"""Report local/remote Git drift without merging or modifying history."""

from __future__ import annotations

import subprocess
from datetime import datetime, timezone
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPORT_PATH = PROJECT_ROOT / "reports/repo_drift_status.md"


def run_git(args: list[str]) -> tuple[int, str, str]:
    proc = subprocess.run(
        ["git", *args],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    return proc.returncode, proc.stdout.strip(), proc.stderr.strip()


def git_output(args: list[str]) -> str:
    rc, stdout, stderr = run_git(args)
    if rc != 0:
        return f"ERROR: {stderr or stdout}"
    return stdout


def main() -> int:
    fetch_rc, _, fetch_err = run_git(["fetch", "--prune", "origin"])
    branch = git_output(["branch", "--show-current"]) or "unknown"
    status = git_output(["status", "--short"])
    head = git_output(["rev-parse", "--short", "HEAD"])
    upstream = git_output(["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"])
    ahead_behind = "unknown"
    if upstream and not upstream.startswith("ERROR"):
        ahead_behind = git_output(["rev-list", "--left-right", "--count", f"HEAD...{upstream}"])

    dirty = bool(status and not status.startswith("ERROR"))
    fetch_status = "ok" if fetch_rc == 0 else "failed"
    lines = [
        "# Repo drift status",
        "",
        f"Generated: {datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')}",
        "",
        f"- Fetch: {fetch_status}",
        f"- Branch: `{branch}`",
        f"- HEAD: `{head}`",
        f"- Upstream: `{upstream}`",
        f"- Ahead/behind: `{ahead_behind}`",
        f"- Dirty working tree: {'yes' if dirty else 'no'}",
        "",
    ]
    if fetch_err:
        lines.extend(["## Fetch stderr", "", "```text", fetch_err[:4000], "```", ""])
    lines.extend(["## Status", "", "```text", status or "(clean)", "```"])
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"repo_drift_fetch={fetch_status}")
    print(f"dirty_working_tree={'yes' if dirty else 'no'}")
    print(f"ahead_behind={ahead_behind}")
    return 0 if fetch_rc == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
