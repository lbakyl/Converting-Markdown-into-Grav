# publish_vault.py, optimize_images.py, and the Commit and Publish plugin

Three pieces that together replace Obsidian Git's own commit button as the way this vault's `Published/` folder gets published: they resize and rename images, then commit and push, all in one deliberate action, triggered by a single Obsidian command instead of a background timer.

They exist because Obsidian Git's own commits don't invoke local git hooks (confirmed by testing directly: a real commit went through with an untouched file, no hook output at all, most likely because Obsidian Git commits through its own bundled JavaScript git implementation rather than the system's `git` binary). A pre-commit hook, the obvious first approach, simply never fires for it. Driving `git` directly from a plain script sidesteps the problem entirely.

Full write-up, including the scheduled-task attempt that got abandoned for flashing a console window, and every gotcha hit along the way, is in Part 3 of the ["Self-host Obsidian and publish tutorials via an automated pipeline to Grav CMS"](https://tutorials.bachelor-tech.com) series.

## What each piece does

- **`optimize_images.py`**: scans the vault for images and, for each one, downscales it if it's wider than a set maximum, and renames it to a consistent, SEO-friendly filename based on the nearest heading above it. Importable, no side effects of its own beyond the file operations, so it can be run standalone (`python optimize_images.py`) or called from another script.
- **`publish_vault.py`**: calls `optimize_images.py`, then commits and pushes whatever changed, using `git` directly rather than any Obsidian plugin. Meant to be run whenever you're ready to publish, not on a schedule.
- **The `Commit and Publish` Obsidian plugin** (`manifest.json` + `main.js`): adds one command to Obsidian's command palette that runs `publish_vault.py` in the background (no console window) and shows a short result notification, so the whole thing is a single keypress once a hotkey is set for it.

## How images get renamed

`Part-N-Heading-Slug-NN.ext`:

- `N` is the part number, read from the referencing note's own filename (a note called "Part 2 - Whatever.md" gives `N = 2`; a note with no "Part N" in its name is left without that prefix).
- `Heading-Slug` is the nearest H2 heading above the image in that note, falling back to the nearest heading of any level if there's no H2 above it. Case is preserved from the heading text on purpose (`Deploy the Obsidian container` becomes `Deploy-the-Obsidian-container`, not lowercased), since the goal is a real, readable filename, not a generic slug.
- `NN` is a two-digit, 1-indexed counter scoped to that exact heading. The first image under a given H2 is `01`, the second under that same H2 is `02`.

The file is moved into an `assets/` folder next to the note that references it. This applies to every image the script can find a note reference for, not just Obsidian's own auto-generated `Pasted image <timestamp>.png` names, a deliberately-placed diagram or icon gets renamed the same way.

Idempotent by design: a file already named exactly what a run would produce is left alone, so running this repeatedly never reshuffles numbers or touches an image twice, and numbering continues correctly from whatever's already on disk rather than restarting at `01` across separate runs.

An image with no note referencing it at all is skipped, there's no heading to build a name from.

## Configuration

Everything is a constant near the top of `optimize_images.py`, no config file or environment variables:

| Constant | Meaning |
|---|---|
| `VAULT_ROOT` | Root folder to scan. Defaults to the script's own folder, so it's meant to sit directly inside `Published/`. |
| `MAX_WIDTH` | Images wider than this get downscaled, preserving aspect ratio. |
| `JPEG_QUALITY` | Quality setting used when resizing a `.jpg`/`.jpeg` (PNG resizing has no equivalent lossy setting). |
| `RESIZE_EXTS` | File extensions treated as raster images. `.gif` and `.svg` are deliberately excluded, animated frames and vector data don't resize the same way. |
| `ASSETS_DIRNAME` | Folder name renamed images get moved into, next to whichever note references them. |
| `AI_NAMING` | Off by default. Flip to `True` and fill in `ai_name_image()` to use a real vision model for naming instead of the heading-based fallback; the function is stubbed but not wired up to any provider yet. |

`publish_vault.py` has one constant of its own worth knowing: the commit message template, `vault backup: <timestamp>`, matching the style Obsidian Git's own auto-commits already use.

## Requirements

- Python 3.10 or newer, plus [Pillow](https://pypi.org/project/Pillow/) (`pip install Pillow`), the only third-party dependency, needed for the actual resizing.
- `git` on `PATH`, with push access already configured for the repo (an SSH deploy key, scoped write, is what this is meant to run with, the same pattern used on the read-only pull side documented alongside `publish_inbox.py`).
- On Windows specifically, the plugin expects `python.exe`/`pythonw.exe` at a fixed absolute path (`C:\Python311\pythonw.exe` by default), edit the `PYTHONW` constant in `main.js` if your install lives elsewhere. An absolute path is used deliberately rather than relying on `PATH`, since a plain `python` command isn't guaranteed to resolve correctly inside the environment Obsidian spawns for a plugin, and Windows' own `python.exe` App Execution Alias stub can silently shadow a real install if relied on instead.

## Running it

Not on a schedule. A background timer was the first approach, it worked, but launching a console-subsystem process every few minutes flashes a window on screen, disruptive during anything full-screen. The whole idea got replaced with one deliberate action instead:

1. Install the plugin: copy `manifest.json` and `main.js` into `<vault>/.obsidian/plugins/commit-and-publish/`, add `"commit-and-publish"` to `.obsidian/community-plugins.json`, then restart Obsidian (or reload without saving).
2. Set a hotkey: Settings → Hotkeys → search "Commit and Publish" → click the **+** next to it → press your chosen key combination. Obsidian doesn't ship a default for this, or for Obsidian Git's own commit command either, community plugin commands never get one automatically, so there's nothing existing to match.
3. From then on, press that hotkey (or run the command from the palette) whenever you're ready to publish.

Running `publish_vault.py` by hand for testing works too, from a terminal, inside the repo:

```bash
python publish_vault.py
```

## Debugging

The plugin writes `debug.log` inside its own folder (`.obsidian/plugins/commit-and-publish/debug.log`), cleared at the start of every run so it only ever holds the latest one. Two entries per run: `start` (the resolved paths and whether each one actually exists on disk, useful if something's misconfigured) and `result` (the full stdout/stderr from `publish_vault.py`, plus any error Node itself reported trying to launch it).

## Notes and limitations, and gotchas worth knowing if you adapt this yourself

- **`__pycache__` pollution.** Importing `optimize_images` from `publish_vault.py` creates a `.pyc` cache file inside the vault by default. `sys.dont_write_bytecode = True`, set before the import, stops it; a `.gitignore` entry for `__pycache__/` is a second layer of protection if anything else ever triggers it (a plain `python -m py_compile` run against the file, for instance, ignores that flag entirely).
- **Git subprocess calls need `creationflags=subprocess.CREATE_NO_WINDOW` on Windows**, not just a windowless Python interpreter for the outer process. `publish_vault.py` spawns several `git` subprocesses (pull, add, commit, push, plus two status checks), and each one briefly flashes its own console window regardless of what launched the parent, unless that flag is passed explicitly to every one of them.
- **Node's `child_process.execFile` needs a backslash-style path for the executable itself on Windows**, confirmed by testing directly, a forward-slash path to the same, genuinely-existing file fails with `ENOENT`. This is the opposite of what git's own `core.sshCommand` needs elsewhere in this project (forward slashes there, since that string is interpreted by Git for Windows' bundled `sh.exe` rather than passed to Windows' process creation directly).
- **`__dirname` isn't reliable inside an Obsidian plugin.** Obsidian loads plugins through its own mechanism, not Node's normal `require()`, and `__dirname` isn't guaranteed to resolve correctly there. Build any in-plugin file paths from `app.vault.adapter.getBasePath()` instead.
- **Checking only for uncommitted changes isn't enough**, since Obsidian Git's own auto-commit (its auto-push, not auto-commit, is what's disabled) can commit locally before `publish_vault.py` ever runs, leaving nothing for `git add` to pick up despite there being a genuinely unpushed commit sitting there. `publish_vault.py` checks `git rev-list @{u}..HEAD --count` as a separate condition and pushes if either that or the ordinary uncommitted-changes check comes back true.
- **Renaming applies retroactively to every image, including ones already live and published**, not just newly added ones. That was a deliberate choice for this vault (a consistently-named `assets/` folder mattered more than preserving old URLs), not an inherent requirement, gate the rename on the filename still looking auto-generated if you'd rather it only apply going forward.
