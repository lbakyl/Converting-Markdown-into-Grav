#!/usr/bin/env python3
"""
Standalone housekeeping script for the vault's Published/ folder, the same
shape as its sibling optimize_images.py: importable, no side effects beyond
the file rewrites, safe to run standalone (`python clean_code_fences.py`) or
call from publish_vault.py as part of the normal publish pass.

What it fixes: a fenced code block whose first content line has a stray
leading space or tab that no other line in the same block has - e.g.

    ```bash
     python3 backup.py
    ```

renders with only that first row looking shifted one character right,
indistinguishable at a glance from an actual rendering bug (it isn't one:
confirmed directly against the live site - raw HTML byte-for-byte matches
the source, computed CSS padding/text-indent is zero, no JS touches it).
Traced to real, so far, each time: a single stray character that slipped in
on the Notion side of the pipeline (present in the original Notion export
too, not introduced anywhere in this repo), most likely from how Notion's
rich-text blocks get joined back into a single code string when a block
happens to start with an empty/whitespace-only run. Since it's kept
recurring across separate Notion imports, this is the retroactive-cleanup
+ prevention step for it, the same idea as optimize_images.py doing image
renaming retroactively rather than only for newly pasted images.

Deliberately conservative about what counts as "stray": only strips the
first line's leading whitespace when every OTHER non-blank line in that
same block has none at all. A block that's genuinely, consistently
indented throughout (a real nested code sample, a YAML/Python snippet
where indentation is syntax) is left completely untouched, since in that
case the first line sharing the same indent as its neighbours is normal,
not a one-off typo.
"""
import re
import sys
from pathlib import Path

VAULT_ROOT = Path(__file__).resolve().parent
IGNORED_DIRS = {".git", ".obsidian"}

# Mirrors the fence-matching shape already used by publish_inbox.py on the
# server side, with the open/close fence lines captured separately so the
# original block can be reconstructed exactly except for the one line that
# actually changes.
FENCE_RE = re.compile(r"(^```[^\n]*\n)(.*?)(^```[ \t]*$)", re.MULTILINE | re.DOTALL)


def iter_md_files(root: Path):
    for p in root.rglob("*.md"):
        if not any(part in IGNORED_DIRS for part in p.parts):
            yield p


def _fix_fence(m: re.Match, changed: list) -> str:
    open_line, inner, close_line = m.group(1), m.group(2), m.group(3)
    lines = inner.split("\n")
    if len(lines) < 2:
        return m.group(0)  # single-line block, nothing to compare against

    first = lines[0]
    if not first[:1] in (" ", "\t"):
        return m.group(0)  # first line already flush - nothing to fix

    rest_nonblank = [ln for ln in lines[1:] if ln.strip()]
    if not rest_nonblank:
        return m.group(0)  # only one real content line total, no baseline

    if any(ln[:1] in (" ", "\t") for ln in rest_nonblank):
        return m.group(0)  # other lines share indentation too - looks
        # intentional (real nested code), leave the whole block alone

    lines[0] = first.lstrip(" \t")
    changed.append(True)
    return open_line + "\n".join(lines) + close_line


def clean_text(text: str) -> tuple[str, bool]:
    """Returns (possibly-modified text, whether anything changed)."""
    changed: list = []
    new_text = FENCE_RE.sub(lambda m: _fix_fence(m, changed), text)
    return new_text, bool(changed)


def clean_vault(root: Path) -> bool:
    """Run the cleanup pass over every .md file in root. Returns True if
    anything on disk actually changed. Importable so publish_vault.py can
    call this directly, the same pattern optimize_images.py already uses."""
    any_change = False
    for md_path in iter_md_files(root):
        text = md_path.read_text(encoding="utf-8")
        new_text, changed = clean_text(text)
        if changed:
            md_path.write_text(new_text, encoding="utf-8")
            print(f"  cleaned stray code-block indent in {md_path.relative_to(root)}")
            any_change = True
    if not any_change:
        print("No stray code-block indentation found.")
    return any_change


def main() -> int:
    clean_vault(VAULT_ROOT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
