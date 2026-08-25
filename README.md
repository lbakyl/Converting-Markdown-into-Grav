# publish_inbox.py

A small, dependency-free Python script that converts a folder of Markdown files (an Obsidian vault's `Published/` folder, synced through git) into real pages for [Grav CMS](https://getgrav.org/), a flat-file, database-less CMS.

It exists because Grav's own official plugin for this, **Git Sync**, turned out to be unreliable enough (a corrupting admin UI, and twice deleting the entire live `pages/` directory) that it got fully uninstalled and replaced with this script instead. No plugin holds write access to live content anymore; this script is the only thing that writes to `user/pages/`, and it only ever writes pages it created itself.

Full write-up, including why Git Sync was dropped and the exact deploy key and systemd setup this runs under, is in Part 2 and Part 3 of the ["Self-host Obsidian and publish tutorials via an automated pipeline to Grav CMS"](https://tutorials.bachelor-tech.com) series.

## What it does

On each run, the script:

1. Pulls the latest content from an isolated git clone (kept entirely outside Grav's own `user/` tree, so nothing about it can touch Grav's actual content by accident).
2. Walks that clone's top level:
   - Loose `.md` files become single, standalone pages.
   - Subfolders become multi-part series, with each `.md` file inside becoming one part.
3. Converts each file's content into a Grav page: extracts a title, rewrites Obsidian-style wikilinks and image embeds, copies referenced images alongside the generated page, and writes proper Grav frontmatter.
4. Removes any page it previously created whose source has since been renamed or deleted, so nothing is ever left behind as a stale duplicate.
5. Clears Grav's cache so the change is visible immediately.

## Expected repo layout

The script assumes the git clone's root *is* the vault's `Published/` folder (no extra nesting), laid out like this:

```
repo-root/
├── Some Standalone Article.md          -> one single-part page
└── A Multi-Part Series/
    ├── Part 1 - Introduction.md        -> becomes part 01 of the series
    ├── Part 2 - Deep Dive.md           -> becomes part 02
    └── Attachments/
        └── screenshot.png              -> available to every part in the series
```

Parts within a series are ordered by a leading "Part N" in the filename where present, alphabetically otherwise. Any image anywhere under a series folder (including nested subfolders) is available to every part in that series, matched by filename alone.

## Conversion rules

- **Title**: the first genuine `# Heading` line in the file, stripped from the body afterward. Headings that fall inside a fenced ` ``` ` code block are correctly ignored (a bash comment like `# 1. Do the thing` is never mistaken for the page title). If no real heading exists anywhere, the filename is used instead.
- **Wikilinks**: `[[Note Name]]` and `[[Note Name|Display text]]` are rewritten to relative Grav links, resolved through a title-to-slug map built once across the entire batch before any page is written, so cross-references between articles in the same run always resolve correctly.
- **Images**: both Obsidian's embed syntax (`![[image.png]]`, with an optional `|width` suffix which is dropped) and plain Markdown image syntax (`![alt](path/image.png)`) are rewritten to a normal `![alt](image.png)` reference, resolved by filename regardless of the original path. The image itself is copied alongside the generated page, and given a lightbox link plus a size class chosen from the image's own pixel height (a short, wide screenshot doesn't end up as a tiny sliver at a fixed width).
- **Ordering**: top-level pages (both standalone articles and whole series) are sorted newest first, by each entry's earliest git commit date.
- **Cleanup**: tracked through a manifest file (see below). Applies both to whole top-level entries and to individual parts inside a series, so a renamed or deleted part never leaves its old folder behind as an orphaned duplicate.

## Configuration

Everything is a constant near the top of the file, no config file or environment variables:

| Constant | Meaning |
|---|---|
| `SOURCE_REPO` | Path to the isolated git clone this script reads from. |
| `PAGES_DIR` | Grav's `user/pages/` directory, where generated pages are written. |
| `MANIFEST_PATH` | Where the script records what it has previously created, for cleanup. |
| `START_INDEX` | First numeric prefix used for generated top-level page folders (default `10`, leaving `01`/`02` free for Grav's own default pages). |
| `RESERVED_SLUGS` | Slugs the script must never generate, because Grav already uses them (its own default `home`/`typography` pages). A colliding title gets `-post` appended to its slug instead. |
| `IGNORED_TOP_LEVEL` | Entries at the repo root the script skips outright (`.git`, `.gitignore`, `.htaccess`). |
| `IMAGE_EXTS` | File extensions treated as images when resolving embeds. |

## Requirements

- Python 3.10 or newer (uses `X | None` type hints). No third-party packages; only the standard library.
- `git` on `PATH`, with read access already configured for `SOURCE_REPO` (an SSH deploy key, scoped read-only, is what this is meant to run with).
- `docker` on `PATH`, with a running container named `grav`, for the final cache-clear step. This step is best-effort: its output is captured and ignored if it fails, so a missing container doesn't stop the page conversion itself from completing.

## Running it

Meant to run unattended, on a schedule, not manually. The reference deployment uses a systemd timer:

```ini
# /etc/systemd/system/grav-publish.timer
[Unit]
Description=Run grav-publish.service every 5 minutes

[Timer]
OnBootSec=2min
OnUnitActiveSec=5min
AccuracySec=30s

[Install]
WantedBy=timers.target
```

```ini
# /etc/systemd/system/grav-publish.service
[Unit]
Description=Convert Grav _inbox/ content into published pages
After=docker.service

[Service]
Type=oneshot
ExecStart=/usr/bin/python3 /opt/grav/publish_inbox.py
```

Polling on a timer was chosen deliberately over a webhook receiver: no inbound endpoint to secure, and a host that was offline when a push happened simply catches up on its next tick, rather than needing that push replayed.

Running it by hand for testing:

```bash
python3 publish_inbox.py
```

It prints one line per page written, one line per stale page or part removed, and a final summary. Safe to run repeatedly; a run with nothing changed just reports the same pages again.

## Notes and limitations

- Only `.md` files are ever converted into pages. Any other file type placed in a series folder (a script, a JSON blueprint, and so on) is silently ignored, it is neither a part nor an image, so the script has no rule for it. Link to such files from within the Markdown instead (a plain link to wherever they're actually hosted); the wikilink and image rewriting rules don't touch ordinary Markdown links, so they pass through untouched.
- The manifest (`MANIFEST_PATH`) is what makes cleanup possible. Deleting it doesn't break anything on the next run, but it does mean the script loses track of what it previously created, so nothing gets cleaned up until the next rename or deletion happens naturally after that.
- No file locking. Two overlapping runs (a very short interval combined with a very large batch) could in theory race on `PAGES_DIR`. Not a concern at the default 5-minute interval against a personal tutorial archive's content volume, worth knowing if this gets adapted for something with much heavier publishing throughput.
