#!/usr/bin/env python3
"""Conventional Commits commit-msg validation hook.

Validates that commit messages adhere to Conventional Commits v1.0.0.
On failure, prints actionable diagnostic output and the explicit specification URL:
https://www.conventionalcommits.org/
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

# Pattern matching Conventional Commits: type(scope optional)[!]?: subject
CONVENTIONAL_PATTERN = re.compile(
    r"^(?P<type>feat|fix|docs|style|refactor|perf|test|build|ci|chore|revert)"
    r"(\((?P<scope>[a-zA-Z0-9_\-\./]+)\))?"
    r"(?P<breaking>!)?"
    r":\s+"
    r"(?P<subject>[^\n\r]+)"
)

# Automated tooling, git pull, and merge commit bypass patterns
BYPASS_PATTERNS = [
    re.compile(r"^Merge (remote-tracking )?branch .*"),
    re.compile(r"^Merge branches? .*"),
    re.compile(r"^Merge pull request .*"),
    re.compile(r"^Merge tag .*"),
    re.compile(r"^Revert \".*\""),
]


def main() -> int:
    if hasattr(sys.stderr, "reconfigure"):
        try:
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    if len(sys.argv) < 2:
        sys.stderr.write("Error: commit message file path not provided.\n")
        return 1

    msg_file = Path(sys.argv[1])
    try:
        content = msg_file.read_text(encoding="utf-8").strip()
    except Exception as e:
        sys.stderr.write(f"Error reading commit message file: {e}\n")
        return 1

    # Extract first non-comment, non-empty line
    lines = [
        line.strip()
        for line in content.splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    if not lines:
        sys.stderr.write("Error: Empty commit message.\n")
        return 1

    first_line = lines[0]

    # Allow merge and revert commits
    for bp in BYPASS_PATTERNS:
        if bp.match(first_line):
            return 0

    if not CONVENTIONAL_PATTERN.match(first_line):
        sys.stderr.write("\n" + "=" * 70 + "\n")
        sys.stderr.write("❌ [COMMIT REJECTED] Non-Compliant Commit Message Format\n")
        sys.stderr.write("=" * 70 + "\n\n")
        sys.stderr.write(f'Your commit message header was:\n  "{first_line}"\n\n')
        sys.stderr.write(
            "Harness Bridge strictly enforces the Conventional Commits specification.\n"
        )
        sys.stderr.write(
            "Allowed types: feat, fix, docs, style, refactor, perf, test, build, ci, chore, revert\n\n"
        )
        sys.stderr.write("Format:\n")
        sys.stderr.write("  <type>[optional scope][!]: <description>\n\n")
        sys.stderr.write("Examples:\n")
        sys.stderr.write("  feat(drivers): add Claude Code streaming protocol handler\n")
        sys.stderr.write("  fix(session): prevent pipe deadlock on large subprocess diffs\n")
        sys.stderr.write("  feat(server)!: breaking redesign of MCP registration endpoint\n")
        sys.stderr.write("  docs(contributing): document local git hooks and CI gating\n\n")
        sys.stderr.write("👉 For complete specification rules and guidelines, visit:\n")
        sys.stderr.write("   https://www.conventionalcommits.org/\n")
        sys.stderr.write("=" * 70 + "\n\n")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
