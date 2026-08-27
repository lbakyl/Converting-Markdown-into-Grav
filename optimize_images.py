#!/usr/bin/env python3
"""
Standalone housekeeping script for the Obsidian vault's Published/ folder.
Run it directly (`python optimize_images.py`), or on a schedule (Windows
Task Scheduler etc.) - it's meant to run *before* Obsidian Git's own next
auto-commit, so whatever it changes just rides along in that commit like
any other edit. It does not touch git at all itself (see "Why not a git
hook" below).

Scans the whole vault for images and, for each one found:

- Downscales it if wider than MAX_WIDTH, preserving aspect ratio. This is
  what actually fixes oversized screenshots in Gitea's own file preview -
  plain Markdown image syntax has no width attribute the way raw HTML
  does, so the only way to make Gitea's preview reasonable is to make the
  file itself smaller. Grav's own rendering is unaffected either way: it
  sizes images by relative CSS percentage of the page column, not fixed
  pixels, so a smaller source file just means less to download, not a
  different displayed size. Already-small images are a fast no-op, so
  this is safe to re-check on every run.
- Renames EVERY image it can find a note reference for (not just
  Obsidian's auto-generated "Pasted image <timestamp>.png" names - a
  deliberately-named file gets the same treatment) to
  Part-N-Heading-Slug-NN.ext: N is the part number from the referencing
  note's own filename (e.g. "Part 2 - ..."), Heading-Slug is the nearest
  H2 above the image (falling back to the nearest heading of any level
  if there's no H2 above it in that note), and NN is a two-digit,
  1-indexed counter scoped to that exact (part, heading) combination -
  the first image under a given H2 is 01, the second under that same H2
  is 02, and so on. Case is preserved from the heading text (SEO-style
  naming, not lowercased). Moves the file into an assets/ folder next to
  that note (matching the convention already used in this vault,
  independent of whatever folder name Obsidian's own attachment setting
  actually drops new pastes into). Idempotent: a file already named
  exactly what this run would produce is left alone, so re-running never
  reshuffles numbers or touches unrelated images, and numbering picks up
  correctly from existing files rather than restarting at 01 across
  separate runs. An image with no note referencing it at all (an orphan)
  is skipped - there's no heading context to build a name from.
- Rewrites every reference to a renamed file, in every .md file in the
  vault, to point at the new path (both the Obsidian wikilink-embed form
  and standard Markdown image syntax, URL-encoded or not).

Why not a git hook: this used to be a pre-commit hook, but Obsidian Git
does not invoke local git hooks when it makes its own automatic commits
(confirmed empirically - a real "add" commit went through with the
original file, completely untouched, no hook output at all). Most likely
it commits through its own bundled JS git implementation rather than
shelling out to the real git binary, even on desktop. A hook can only
ever fire for a commit made with the real binary, so it's the wrong
mechanism here regardless of the exact cause. Running independently, on
a timer or by hand, sidesteps the problem entirely: it doesn't matter how
the eventual commit gets made, only that the files are already fixed up
on disk by the time it happens.

AI-based naming (as in the Notion script's `self.ai.name_image(...)`) is
deliberately not wired in here - flip AI_NAMING below and fill in
ai_name_image() once a provider/API key is actually chosen. Until then,
every eligible image gets the heading-slug fallback name.

Scope, deliberately kept narrow for v1:
- .gif and .svg are left alone entirely (animated frames and vector data
  don't resize the way a raster screenshot does).
- If two different notes reference the same auto-named image (unusual -
  Obsidian gives every paste its own unique filename), only the first
  one found is used to pick the new name and folder.
"""
import re
import sys
from pathlib import Path
from urllib.parse import quote, unquote

from PIL import Image

VAULT_ROOT = Path(__file__).resolve().parent  # run this script from Published/ itself,
# or edit this line to point at wherever your vault's Published/ folder is.

MAX_WIDTH = 1600  # pixels; images narrower than this are left untouched
JPEG_QUALITY = 85
RESIZE_EXTS = {".png", ".jpg", ".jpeg", ".webp"}
AI_NAMING = False  # flip once ai_name_image() actually calls a real provider
ASSETS_DIRNAME = "assets"
IGNORED_DIRS = {".git", ".obsidian"}

HEADING_RE = re.compile(r"^#{1,6}\s+(.+?)\s*$", re.MULTILINE)
H2_RE = re.compile(r"^##[ \t]+(.+?)[ \t]*$", re.MULTILINE)  # exactly H2: the
# third char after the leading ## must be whitespace, not another #, so this
# never matches H3+ headings.
WIKI_EMBED_RE = re.compile(r"!\[\[([^\]|]+)(?:\|[^\]]+)?\]\]")
MD_IMAGE_RE = re.compile(
    r"!\[([^\]]*)\]\(([^)\s]+\.(?:png|jpe?g|gif|webp))(?:\s+\"[^\"]*\")?\)",
    re.IGNORECASE,
)
PART_NUM_RE = re.compile(r"\bpart[\s-]*(\d+)\b", re.IGNORECASE)


def ai_name_image(image_path: Path, heading) -> str:
    """Stub. Return a descriptive slug (no extension) for image_path, or
    None to fall back to the heading-slug default. Wire up a real vision
    call here and flip AI_NAMING to True to use it."""
    return None


def iter_files(root: Path, exts: set):
    for p in root.rglob("*"):
        if p.is_file() and p.suffix.lower() in exts and not any(part in IGNORED_DIRS for part in p.parts):
            yield p


def dashify(text: str, max_len: int = 60) -> str:
    """Case-preserving slug for the SEO-style naming scheme (unlike
    slugify-style helpers elsewhere in this project, which lowercase
    everything - this deliberately keeps the heading's original casing,
    e.g. "Deploy the Obsidian container" -> "Deploy-the-Obsidian-container")."""
    s = text.strip()
    s = re.sub(r"[^A-Za-z0-9]+", "-", s)
    s = re.sub(r"-+", "-", s).strip("-")
    return s[:max_len].rstrip("-") or "Image"


def _closest_match(pattern: re.Pattern, md_text: str, ref_pos: int):
    best = None
    for m in pattern.finditer(md_text):
        if m.start() > ref_pos:
            break
        best = m.group(1)
    return best


def nearest_heading(md_text: str, ref_pos: int):
    """Nearest H2 above ref_pos; falls back to the nearest heading of any
    level if there's no H2 above it in this note at all."""
    return _closest_match(H2_RE, md_text, ref_pos) or _closest_match(HEADING_RE, md_text, ref_pos)


def find_part_number(md_path: Path):
    """'2' for a note named like "Part 2 - Whatever.md", None if the
    filename doesn't look like part of a numbered series."""
    m = PART_NUM_RE.search(md_path.stem)
    return m.group(1) if m else None


def build_prefix(part_num, heading: str) -> str:
    if part_num and heading:
        # Avoid "Part-1-Part-1-..." - happens when there's no H2 above the
        # image and this fell back to the note's own H1, which in this
        # vault's convention already starts with "Part N - ..." itself.
        heading = PART_NUM_RE.sub("", heading, count=1).strip(" -:")
    heading_part = dashify(heading) if heading else "Image"
    return f"Part-{part_num}-{heading_part}" if part_num else heading_part


def already_named(img_path: Path, prefix: str) -> bool:
    """True if img_path already looks exactly like what this run would
    produce for this prefix - the idempotency check that lets this script
    re-run safely without reshuffling numbers or renaming things twice."""
    return re.match(re.escape(prefix) + r"-\d+$", img_path.stem, re.IGNORECASE) is not None


def next_numbered_path(dest_dir: Path, prefix: str, ext: str) -> Path:
    """Next unused NN (two-digit, 1-indexed) for this exact prefix,
    continuing from whatever's already in dest_dir rather than always
    restarting at 01 - so numbering stays correct across separate runs,
    not just within a single one."""
    pattern = re.compile(re.escape(prefix) + r"-(\d+)$", re.IGNORECASE)
    highest = 0
    for f in dest_dir.glob(f"*{ext}"):
        m = pattern.match(f.stem)
        if m:
            highest = max(highest, int(m.group(1)))
    return dest_dir / f"{prefix}-{highest + 1:02d}{ext}"


def resize_in_place(path: Path) -> bool:
    """Downscale to MAX_WIDTH if wider. Returns True if the file changed."""
    if path.suffix.lower() not in RESIZE_EXTS:
        return False
    try:
        with Image.open(path) as im:
            if im.width <= MAX_WIDTH:
                return False
            ratio = MAX_WIDTH / im.width
            new_size = (MAX_WIDTH, max(1, round(im.height * ratio)))
            resized = im.convert("RGB").resize(new_size, Image.LANCZOS) if im.mode in ("P", "CMYK") else im.resize(new_size, Image.LANCZOS)
            save_kwargs = {"optimize": True}
            if path.suffix.lower() in (".jpg", ".jpeg"):
                save_kwargs["quality"] = JPEG_QUALITY
            resized.save(path, **save_kwargs)
        return True
    except Exception as e:
        print(f"  warning: could not resize {path.name}: {e}", file=sys.stderr)
        return False


def find_reference(md_texts: dict, image_name: str):
    """(md_path, position, heading) for the first note that references
    image_name, or (None, None, None) if none do."""
    for md_path, text in md_texts.items():
        for m in WIKI_EMBED_RE.finditer(text):
            if Path(m.group(1).strip()).name == image_name:
                return md_path, m.start(), nearest_heading(text, m.start())
        for m in MD_IMAGE_RE.finditer(text):
            if Path(unquote(m.group(2))).name == image_name:
                return md_path, m.start(), nearest_heading(text, m.start())
    return None, None, None


def rewrite_references(md_texts: dict, old_name: str, new_path: Path) -> set:
    """Replace every reference to old_name (matched by filename alone, any
    path prefix) with the correct path to new_path *relative to each
    referencing note* - a plain filename swap would leave a stale
    directory prefix behind if the file also moved folders (e.g.
    Attachments/ -> assets/), pointing at nothing."""
    import os
    changed = set()
    for md_path, text in md_texts.items():
        rel = Path(os.path.relpath(new_path, md_path.parent)).as_posix()

        def wiki_repl(m: re.Match) -> str:
            if Path(m.group(1).strip()).name != old_name:
                return m.group(0)
            return f"![[{rel}]]"

        def md_repl(m: re.Match) -> str:
            if Path(unquote(m.group(2))).name != old_name:
                return m.group(0)
            return f"![{m.group(1)}]({quote(rel)})"

        updated = WIKI_EMBED_RE.sub(wiki_repl, text)
        updated = MD_IMAGE_RE.sub(md_repl, updated)
        if updated != text:
            md_texts[md_path] = updated
            changed.add(md_path)
    return changed


def process_vault(root: Path) -> bool:
    """Run the full resize/rename/rewrite pass over root. Returns True if
    anything on disk actually changed. Importable so publish_vault.py can
    call this directly and then commit+push in one combined action,
    rather than this script needing to run as a separate, independently
    triggered step."""
    all_images = list(iter_files(root, RESIZE_EXTS))
    if not all_images:
        print("No images found.")
        return False

    md_paths = [p for p in iter_files(root, {".md"})]
    md_texts = {p: p.read_text(encoding="utf-8") for p in md_paths}

    changed_md = set()
    any_change = False

    for img_path in all_images:
        if not img_path.exists():  # may have been moved earlier this run
            continue

        resized = resize_in_place(img_path)
        current_path = img_path

        md_path, pos, heading = find_reference(md_texts, img_path.name)
        if md_path:  # no reference found at all -> orphan, nothing to name it from
            part_num = find_part_number(md_path)
            slug = ai_name_image(img_path, heading) if AI_NAMING else None
            prefix = slug if slug else build_prefix(part_num, heading)

            if not already_named(img_path, prefix):
                dest_dir = md_path.parent / ASSETS_DIRNAME
                dest_dir.mkdir(exist_ok=True)
                new_path = next_numbered_path(dest_dir, prefix, img_path.suffix.lower())
                if new_path != img_path:
                    old_name = img_path.name
                    old_parent = img_path.parent
                    img_path.rename(new_path)
                    changed_md |= rewrite_references(md_texts, old_name, new_path)
                    print(f"  renamed {old_name} -> {new_path.relative_to(root)}")
                    current_path = new_path
                    any_change = True
                    try:
                        old_parent.rmdir()
                        print(f"  removed now-empty {old_parent.relative_to(root)}")
                    except OSError:
                        pass

        if resized:
            print(f"  resized {current_path.name} to max {MAX_WIDTH}px wide")
            any_change = True

    for md_path in changed_md:
        md_path.write_text(md_texts[md_path], encoding="utf-8")

    if not any_change:
        print("Nothing to do.")
    return any_change


def main() -> int:
    process_vault(VAULT_ROOT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
