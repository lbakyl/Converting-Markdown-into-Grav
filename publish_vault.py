#!/usr/bin/env python3
"""
Run this yourself whenever you want to publish: resizes/renames images
(see optimize_images.py), strips stray leading whitespace from fenced
code blocks (see clean_code_fences.py), then commits and pushes, all in
one pass, the same pattern as the sibling Notion -> Gitea backup script.
Meant to be run on demand, not on any timer.

Why this exists rather than relying on Obsidian Git alone: Obsidian Git's
own commits don't invoke local git hooks (confirmed empirically - see
optimize_images.py's docstring), so nothing can hook into "the moment it
saves to Gitea" from that side. Driving git directly from this script
sidesteps that: the image pass and the commit+push happen together, in
one deliberate action, only when you actually run it (typically via the
"Commit and Publish" command from the sibling Obsidian plugin, or the
Publish.bat launcher).

This pushes if there's EITHER something new to commit OR commits that
are already made but not yet pushed - not just the former. That second
case matters because Obsidian Git's own auto-commit keeps running
independently in the background (its auto-push is what's disabled, not
auto-commit), so by the time this script runs, changes may already be
committed locally with nothing left to `git add`, but still genuinely
unpushed. Checking only "is anything uncommitted" would silently skip
the push in that case.
"""
import sys

sys.dont_write_bytecode = True  # importing optimize_images below would
# otherwise create a __pycache__/*.pyc file right inside the vault repo,
# which git would then see as a new untracked file and happily commit -
# caught this happening for real during testing.

import subprocess
from datetime import datetime

from optimize_images import process_vault, VAULT_ROOT
from clean_code_fences import clean_vault


NO_WINDOW = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
# Without this, each git subprocess (pull, add, commit, push, plus the two
# status checks below) briefly flashes its own console window - Python
# doesn't suppress that just because the parent (pythonw.exe) has none of
# its own. This is what actually eliminates it, not the pythonw.exe choice
# alone.


def run(*args, check=True):
    return subprocess.run(
        args, cwd=VAULT_ROOT, capture_output=True, text=True, check=check,
        creationflags=NO_WINDOW,
    )


def has_uncommitted_changes() -> bool:
    return bool(run("git", "status", "--porcelain").stdout.strip())


def has_unpushed_commits() -> bool:
    result = run("git", "rev-list", "@{u}..HEAD", "--count", check=False)
    if result.returncode != 0:
        return True  # no upstream tracking info or similar - err toward trying to push
    return int(result.stdout.strip() or "0") > 0


def main() -> int:
    print("== optimizing images ==")
    process_vault(VAULT_ROOT)

    print("\n== cleaning stray code-block indentation ==")
    clean_vault(VAULT_ROOT)

    if not has_uncommitted_changes() and not has_unpushed_commits():
        print("\nNothing to commit or push.")
        return 0

    print("\n== pulling first (avoids a rejected push if something else already pushed) ==")
    pull = run("git", "pull", "--quiet", check=False)
    if pull.returncode != 0:
        print(pull.stdout)
        print(pull.stderr, file=sys.stderr)
        print("\nPull failed, most likely a real merge conflict. Stopping here rather than"
              " guessing - resolve it (in Obsidian Git's UI or a terminal), then run this again.")
        return 1

    if has_uncommitted_changes():
        print("\n== committing ==")
        run("git", "add", "-A")
        message = f"vault backup: {datetime.now():%Y-%m-%d %H:%M:%S}"
        commit = run("git", "commit", "--quiet", "-m", message, check=False)
        if commit.returncode != 0:
            print(commit.stdout)
            print(commit.stderr, file=sys.stderr)
            return 1
        print(message)
    else:
        print("\n== nothing new to commit (already committed, e.g. by Obsidian Git) ==")

    print("\n== pushing ==")
    push = run("git", "push", "--quiet", check=False)
    if push.returncode != 0:
        print(push.stdout)
        print(push.stderr, file=sys.stderr)
        return 1

    print("\nDone.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
