#!/usr/bin/env python3
"""
SERVER SIDE: Pulls the curated Obsidian "Published" content from an isolated git clone
(NOT inside Grav's user/ tree - deliberately separate after Git Sync's
bidirectional sync destroyed the live pages/ folder twice) and converts it
into real Grav pages under user/pages/.

Layout expected at the repo root (Obsidian Git's "Custom base path" is
already set to the vault's Published/ folder, so the repo root *is* that
folder - no extra nesting subfolder needed):
  - Loose *.md files at the top level -> single-part pages.
  - Subfolders -> multi-part series. Each .md inside becomes a child page;
    parts are ordered by a leading "Part N" in the filename if present,
    otherwise alphabetically. Any image files anywhere in a series' folder
    tree (e.g. an "Attachments" subfolder) are available to every part in
    that series.

- Title: first '# Heading' line in the file (stripped from the body after),
  ignoring any that fall inside a fenced ``` code block (e.g. a numbered
  bash comment like "# 1. Do the thing" must never be mistaken for the
  page title). Falls back to the filename if no real heading is found.
- Top-level ordering: each entry's earliest git commit date, newest first.
- Wikilinks: [[Note Name]] / [[Note Name|Display]] rewritten to relative
  Grav links using a title->slug map built across the whole batch.
- Image embeds: ![[image.png]] (Obsidian's embed syntax, with an optional
  |width suffix which is dropped) rewritten to real ![](image.png) markdown
  images, and the actual image file copied alongside the generated page so
  the relative reference resolves.
- Cleanup: pages this script previously created but whose source has since
  disappeared get removed, tracked via a manifest. Anything not in the
  manifest (Grav's own default pages) is never touched. This applies both
  to whole top-level entries AND to individual parts within a series - a
  renamed or removed part's old folder is deleted, not left behind as an
  orphan alongside the new one.
- Fenced code blocks and inline code spans: pulled out before wikilink/image
  rewriting runs, so nothing inside one (a mermaid subroutine shape like
  [[Foo]], a bash comment, or a literal `[[Note Name]]` given as a syntax
  example) is mistaken for real Obsidian syntax. A ```mermaid fence is
  translated into the mermaid-diagrams Grav plugin's own
  [mermaid]...[/mermaid] shortcode, since that plugin has no idea what a
  fenced code block is; everything else is put back exactly as written.
- Home.md at the vault root is a special case: it overwrites Grav's own
  reserved homepage (01.home/default.md) directly, instead of becoming a
  numbered page like every other standalone article. Without this, a note
  called Home.md would just get silently renamed to "home-post" by the
  RESERVED_SLUGS check below, to avoid colliding with Grav's own default
  page, and never actually update the real homepage. Only touches
  01.home if Home.md is actually present in a given run; never deletes or
  resets that page if the note is removed, since automatically wiping
  Grav's own default page unattended is too risky.
- All Articles.md at the vault root is the same idea, for 02.articles.
  Only ever writes that page's title and intro text though - the actual
  article listing there is generated live by a custom Twig template, not
  stored as page content anywhere, so there's nothing else to sync.
- Ownership: this script runs as root (via the systemd service), so
  anything it writes is root-owned by default. Grav's own admin UI edits
  and deletes pages as the container's www-data user, a different UID,
  so a root-owned page fails with a permission error the moment someone
  tries to touch it from the admin UI. Every run re-chowns the whole
  pages/ tree to that UID/GID (see WWW_DATA_UID/WWW_DATA_GID below), so
  this self-heals on the very next pull regardless of what actually
  changed that run.
"""
import json
import os
import re
import shutil
import struct
import subprocess
import sys
from pathlib import Path
from urllib.parse import quote, unquote

SHORT_IMAGE_HEIGHT_THRESHOLD = 250  # shorter than this -> shown at 75%, not 50%
# A fixed-width thumbnail's *rendered height* scales with the source image's
# own aspect ratio - a wide-but-short screenshot (a terminal snippet, a
# narrow toolbar) ends up a tiny sliver at 50% width even if its native
# width is huge, because height is what actually shrinks. Height, not
# width, is the signal that tracks "looks too small" here.


def image_height(path: Path) -> int | None:
    """PNG/JPEG height in pixels, no external dependency. None if unknown."""
    try:
        data = path.read_bytes()
    except OSError:
        return None
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return struct.unpack(">I", data[20:24])[0]
    if data[:2] == b"\xff\xd8":  # JPEG
        i = 2
        while i < len(data) - 9:
            if data[i] != 0xFF:
                i += 1
                continue
            marker = data[i + 1]
            if marker in (0xC0, 0xC1, 0xC2, 0xC3):
                return struct.unpack(">H", data[i + 5:i + 7])[0]
            if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:
                i += 2
                continue
            seg_len = struct.unpack(">H", data[i + 2:i + 4])[0]
            i += 2 + seg_len
        return None
    return None

SOURCE_REPO = Path("/opt/grav_source/repo")
PAGES_DIR = Path("/opt/grav/user/pages")
MANIFEST_PATH = Path("/opt/grav/.publish_manifest.json")
START_INDEX = 10  # leaves 01/02 free for Grav's own default pages
RESERVED_SLUGS = {"home", "typography"}
IGNORED_TOP_LEVEL = {".git", ".gitignore", ".htaccess"}
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"}
HOME_FILENAME = "Home.md"  # special-cased below: overwrites Grav's own
# 01.home/default.md directly, instead of becoming a numbered page like
# every other standalone article. Excluded from single_files entirely so
# it's never *also* generated as a separate "home-post" page.
ARTICLES_FILENAME = "All Articles.md"  # same idea as HOME_FILENAME, for
# 02.articles/default.md. Only ever controls that page's title and intro
# text though - the actual article listing is generated live by a custom
# Twig template (articles.html.twig, not part of this pipeline at all),
# walking Grav's page tree directly, so there's no listing content here
# to sync in the first place.
WWW_DATA_UID = 1000  # the grav container's www-data user, confirmed with
# `docker exec grav id www-data` - not necessarily 1000 on a different
# setup, check yours before reusing this. Files this script writes need
# to end up owned by this UID, not root, or Grav's own admin UI (which
# edits/deletes pages as this user, from inside the container) fails
# with a permission error.
WWW_DATA_GID = 33

TITLE_RE = re.compile(r"^#\s+(.+?)\s*$", re.MULTILINE)
CODE_FENCE_RE = re.compile(r"^```.*?^```", re.MULTILINE | re.DOTALL)
# Same fence shape as CODE_FENCE_RE, but capturing the language tag and the
# inner content, used by process_body() below to both protect fenced blocks
# from wikilink/image rewriting and to translate ```mermaid blocks into the
# Grav mermaid-diagrams plugin's own [mermaid]...[/mermaid] shortcode (it
# has no idea what a fenced code block is, it only matches that literal tag).
FENCE_CAPTURE_RE = re.compile(r"^```(\w*)[ \t]*\n(.*?)^```[ \t]*$", re.MULTILINE | re.DOTALL)
INLINE_CODE_RE = re.compile(r"`[^`\n]+`")
# Matches EITHER Obsidian's bracket embed syntax (![[name]] or ![[name|300]])
# OR standard markdown image syntax with any path prefix (![alt](assets/name.png)).
# Both get resolved by filename alone and rewritten the same way, so it
# doesn't matter which convention Obsidian is currently configured to write.
IMAGE_REF_RE = re.compile(
    r"!\[\[([^\]|]+)(?:\|[^\]]+)?\]\]"
    r"|!\[([^\]]*)\]\(([^)\s]+\.(?:png|jpe?g|gif|webp|svg))(?:\s+\"[^\"]*\")?\)",
    re.IGNORECASE,
)
WIKILINK_RE = re.compile(r"(?<!!)\[\[([^\]|]+)(?:\|([^\]]+))?\]\]")
PART_NUM_RE = re.compile(r"part\s*(\d+)", re.IGNORECASE)


def slugify(name: str) -> str:
    s = name.lower().strip()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    s = re.sub(r"-+", "-", s).strip("-")
    if s in RESERVED_SLUGS:
        s = f"{s}-post"
    return s or "untitled"


def git_pull() -> None:
    subprocess.run(["git", "-C", str(SOURCE_REPO), "pull", "--quiet"], check=True)


def first_commit_date(path: Path) -> str:
    rel = path.relative_to(SOURCE_REPO)
    out = subprocess.run(
        ["git", "log", "--format=%aI", "--", str(rel)],
        cwd=SOURCE_REPO, capture_output=True, text=True, check=True,
    ).stdout.strip().splitlines()
    return out[-1] if out else "1970-01-01T00:00:00+00:00"


def find_title_match(content: str) -> re.Match | None:
    """First '# Heading' line, skipping any that fall inside a fenced code
    block - a bash comment like "# 1. Run a throwaway instance" must never
    be mistaken for the document title just because it starts a line."""
    fenced_spans = [m.span() for m in CODE_FENCE_RE.finditer(content)]
    for m in TITLE_RE.finditer(content):
        if not any(start <= m.start() < end for start, end in fenced_spans):
            return m
    return None


def extract_title(content: str, fallback: str) -> tuple[str, str]:
    m = find_title_match(content)
    if not m:
        return fallback, content
    title = m.group(1).strip()
    body = content[: m.start()] + content[m.end():]
    return title, body.lstrip("\n")


def part_sort_key(filename: str):
    m = PART_NUM_RE.search(filename)
    return (0, int(m.group(1))) if m else (1, filename.lower())


def find_images(search_root: Path) -> dict:
    """basename -> Path, for every image file under search_root."""
    return {p.name: p for p in search_root.rglob("*") if p.suffix.lower() in IMAGE_EXTS}


def process_body(text: str, slug_map: dict, image_map: dict, dest_folder: Path) -> str:
    # Pull every fenced code block out before wikilink/image rewriting runs,
    # so nothing inside a fence (a mermaid subroutine shape like [[Foo]], a
    # bash comment, whatever) is mistaken for Obsidian syntax. A ```mermaid
    # fence specifically becomes the mermaid-diagrams plugin's own
    # [mermaid]...[/mermaid] shortcode; every other fence is put back
    # untouched, just protected in the meantime.
    fences = []

    def stash_fence(m: re.Match) -> str:
        lang, inner = m.group(1).lower(), m.group(2)
        if lang == "mermaid":
            replacement = f"[mermaid]\n{inner}[/mermaid]"
        else:
            replacement = m.group(0)
        token = f"\x00FENCE{len(fences)}\x00"
        fences.append(replacement)
        return token

    text = FENCE_CAPTURE_RE.sub(stash_fence, text)

    # Same idea for inline code spans: `[[Note Name]]` or `![[image.png]]`
    # written as a literal syntax example (documentation about the syntax
    # itself, not real Obsidian syntax) must not get rewritten either.
    def stash_inline_code(m: re.Match) -> str:
        token = f"\x00FENCE{len(fences)}\x00"
        fences.append(m.group(0))
        return token

    text = INLINE_CODE_RE.sub(stash_inline_code, text)

    def image_repl(m: re.Match) -> str:
        # Group 1 = Obsidian bracket embed (![[name]]); groups 2/3 = standard
        # markdown image (![alt](path/name.ext)). Either way, resolve by
        # filename alone - the source path prefix (if any) is discarded,
        # since the file always gets copied flat into dest_folder. Standard
        # Markdown syntax (unlike Obsidian's own bracket embed) is commonly
        # URL-encoded by the editor that wrote it (spaces as %20, etc.), so
        # that has to be undone before the filename can match anything in
        # image_map, which is keyed by real, unencoded filenames on disk.
        if m.group(1) is not None:
            name = Path(m.group(1).strip()).name
            alt = name
        else:
            name = Path(unquote(m.group(3))).name
            alt = m.group(2) or name

        src = image_map.get(name)
        if src is None:
            print(f"    warning: embedded image not found anywhere in this series: {name}")
            return f"*(missing image: {name})*"
        shutil.copy2(src, dest_folder / src.name)
        height = image_height(src)
        # See user/themes/learn2/css/custom.css for both classes.
        css_class = "thumb-large" if height is not None and height < SHORT_IMAGE_HEIGHT_THRESHOLD else "thumb-half"
        # ?lightbox=3000,3000 is generously large rather than a real crop -
        # every screenshot handled so far is well under that, so this
        # effectively just triggers Grav's built-in Featherlight popup at
        # full original size on click, without constraining anything.
        return f"![{alt}]({quote(src.name)}?classes={css_class}&lightbox=3000,3000)"

    text = IMAGE_REF_RE.sub(image_repl, text)

    def link_repl(m: re.Match) -> str:
        target, display = m.group(1).strip(), m.group(2)
        slug = slug_map.get(target.lower())
        label = (display or target).strip()
        if slug is None:
            print(f"    warning: wikilink target not found in this batch: [[{target}]]")
            return label
        return f"[{label}]({slug})"

    text = WIKILINK_RE.sub(link_repl, text)

    return re.sub(r"\x00FENCE(\d+)\x00", lambda m: fences[int(m.group(1))], text)


def process_home_page(all_titles: dict) -> None:
    """Home.md at the vault root, if present, overwrites Grav's own
    01.home/default.md directly (see the module docstring for why).
    Deliberately a no-op, not a deletion, if Home.md is missing - never
    resets Grav's own default page unattended just because its source
    note isn't in this particular pull."""
    home_path = SOURCE_REPO / HOME_FILENAME
    if not home_path.exists():
        return
    raw = home_path.read_text(encoding="utf-8")
    title, body = extract_title(raw, fallback="Home")
    home_folder = PAGES_DIR / "01.home"
    home_folder.mkdir(parents=True, exist_ok=True)
    images = find_images(home_path.parent)
    body = process_body(body, all_titles, images, home_folder)
    date = first_commit_date(home_path)
    (home_folder / "default.md").write_text(
        frontmatter(title, date) + body, encoding="utf-8")
    print(f"  wrote 01.home/default.md  <-  {home_path.name}")


def process_articles_page(all_titles: dict) -> None:
    """All Articles.md at the vault root, if present, overwrites Grav's
    own 02.articles/default.md title and intro directly (see the module
    docstring for why this doesn't cover the actual listing). Deliberately
    preserves the menu/template frontmatter fields that page needs to keep
    working - the generic frontmatter() helper doesn't know about those,
    it's built for ordinary pages. Same no-op-if-absent safety as
    process_home_page()."""
    articles_path = SOURCE_REPO / ARTICLES_FILENAME
    if not articles_path.exists():
        return
    raw = articles_path.read_text(encoding="utf-8")
    title, body = extract_title(raw, fallback="All Articles")
    articles_folder = PAGES_DIR / "02.articles"
    articles_folder.mkdir(parents=True, exist_ok=True)
    images = find_images(articles_path.parent)
    body = process_body(body, all_titles, images, articles_folder).strip()
    safe_title = title.replace("'", "''")
    content = (
        "---\n"
        f"title: '{safe_title}'\n"
        f"menu: '{safe_title}'\n"
        "template: articles\n"
        "---\n\n"
        f"{body}\n"
    )
    (articles_folder / "default.md").write_text(content, encoding="utf-8")
    print(f"  wrote 02.articles/default.md  <-  {articles_path.name}")


def fix_ownership() -> None:
    """Recursively chown everything under PAGES_DIR to the container's
    www-data UID/GID. This script runs as root, so anything it writes
    would otherwise stay root-owned, and Grav's own admin UI (editing or
    deleting a page as www-data, from inside the container) fails with a
    permission error the moment it touches one. Runs unconditionally on
    every pull, not just over newly-written files, so ownership drift
    self-heals on the next run regardless of what actually changed."""
    for root, dirs, files in os.walk(PAGES_DIR):
        for name in dirs + files:
            path = os.path.join(root, name)
            try:
                os.chown(path, WWW_DATA_UID, WWW_DATA_GID)
            except OSError as e:
                print(f"  warning: could not chown {path}: {e}", file=sys.stderr)
    try:
        os.chown(PAGES_DIR, WWW_DATA_UID, WWW_DATA_GID)
    except OSError as e:
        print(f"  warning: could not chown {PAGES_DIR}: {e}", file=sys.stderr)


def load_manifest() -> dict:
    return json.loads(MANIFEST_PATH.read_text()) if MANIFEST_PATH.exists() else {}


def save_manifest(manifest: dict) -> None:
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2, sort_keys=True))


def frontmatter(title: str, date: str) -> str:
    safe_title = title.replace("'", "''")
    return (
        "---\n"
        f"title: '{safe_title}'\n"
        f"date: '{date}'\n"
        "visible: true\n"
        "process:\n"
        "    twig: false\n"
        "---\n\n"
    )


def main() -> None:
    if not SOURCE_REPO.exists():
        print(f"Isolated source repo missing at {SOURCE_REPO} - clone it first.")
        return

    git_pull()

    single_files = sorted(
        p for p in SOURCE_REPO.glob("*.md")
        if p.name not in IGNORED_TOP_LEVEL and p.name not in (HOME_FILENAME, ARTICLES_FILENAME)
    )
    series_dirs = sorted(
        p for p in SOURCE_REPO.iterdir()
        if p.is_dir() and p.name not in IGNORED_TOP_LEVEL
    )

    top_entries = []
    all_titles = {}

    for f in single_files:
        raw = f.read_text(encoding="utf-8")
        title, body = extract_title(raw, fallback=f.stem)
        slug = slugify(title)
        all_titles[title.lower()] = slug
        top_entries.append({
            "kind": "single", "title": title, "slug": slug,
            "date": first_commit_date(f), "body": body, "source": f.name,
            "images": find_images(f.parent),
        })

    for d in series_dirs:
        parts = sorted(
            (p for p in d.rglob("*.md")), key=lambda p: part_sort_key(p.name)
        )
        # only .md files directly under the series root or one level of
        # subfolders count as "parts" - an Attachments subfolder full of
        # images won't have any .md in it, so this naturally excludes it.
        if not parts:
            continue
        series_images = find_images(d)
        parsed_parts = []
        for p in parts:
            raw = p.read_text(encoding="utf-8")
            title, body = extract_title(raw, fallback=p.stem)
            slug = slugify(title)
            all_titles[title.lower()] = slug
            parsed_parts.append({
                "title": title, "slug": slug, "body": body,
                "date": first_commit_date(p), "source": p.name,
            })
        series_date = min(pp["date"] for pp in parsed_parts)
        top_entries.append({
            "kind": "series", "title": d.name, "slug": slugify(d.name),
            "date": series_date, "parts": parsed_parts, "source": d.name,
            "images": series_images,
        })

    top_entries.sort(key=lambda e: e["date"], reverse=True)

    process_home_page(all_titles)
    process_articles_page(all_titles)

    manifest = load_manifest()
    new_manifest = {}
    current_top_slugs = set()

    for i, e in enumerate(top_entries):
        folder_name = f"{START_INDEX + i:02d}.{e['slug']}"
        folder_path = PAGES_DIR / folder_name
        current_top_slugs.add(e["slug"])

        old_folder = manifest.get(e["slug"], {}).get("folder")
        if old_folder and old_folder != folder_name and (PAGES_DIR / old_folder).exists():
            (PAGES_DIR / old_folder).rename(folder_path)
        folder_path.mkdir(parents=True, exist_ok=True)

        if e["kind"] == "single":
            body = process_body(e["body"], all_titles, e["images"], folder_path)
            (folder_path / "default.md").write_text(
                frontmatter(e["title"], e["date"]) + body, encoding="utf-8")
            new_manifest[e["slug"]] = {"folder": folder_name, "source": e["source"]}
            print(f"  wrote {folder_name}/default.md  <-  {e['source']}")
        else:
            index_body = "\n".join(f"- [{p['title']}]({p['slug']})" for p in e["parts"])
            (folder_path / "default.md").write_text(
                frontmatter(e["title"], e["date"])
                + "Parts in this series:\n\n" + index_body + "\n",
                encoding="utf-8",
            )
            current_part_folders = set()
            for j, p in enumerate(e["parts"]):
                part_folder_name = f"{j+1:02d}.{p['slug']}"
                current_part_folders.add(part_folder_name)
                part_folder = folder_path / part_folder_name
                part_folder.mkdir(parents=True, exist_ok=True)
                body = process_body(p["body"], all_titles, e["images"], part_folder)
                (part_folder / "default.md").write_text(
                    frontmatter(p["title"], p["date"]) + body, encoding="utf-8")
                print(f"  wrote {folder_name}/{part_folder.name}/default.md  <-  {e['source']}/{p['source']}")

            # A part whose title (and therefore slug/folder name) changed
            # since the last run - or that was removed outright - leaves
            # its old folder behind under a name no longer in
            # current_part_folders. Parts aren't tracked individually in
            # the manifest, so this diffs the folder listing itself rather
            # than relying on manifest state.
            for child in folder_path.iterdir():
                if child.is_dir() and child.name not in current_part_folders:
                    shutil.rmtree(child)
                    print(f"  removed stale part {folder_name}/{child.name} (source renamed or removed)")

            new_manifest[e["slug"]] = {"folder": folder_name, "source": e["source"]}

    for slug, info in manifest.items():
        if slug not in current_top_slugs:
            stale = PAGES_DIR / info["folder"]
            if stale.exists():
                shutil.rmtree(stale)
                print(f"  removed stale page {info['folder']} (source no longer present)")

    save_manifest(new_manifest)
    fix_ownership()
    subprocess.run(["docker", "exec", "grav", "bin/grav", "clearcache"], capture_output=True)
    print(f"Done. {len(top_entries)} top-level page(s) processed, cache cleared.")


if __name__ == "__main__":
    main()
