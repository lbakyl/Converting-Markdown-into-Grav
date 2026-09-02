# Changelog

All notable changes to this repo's scripts are recorded here. Versioning starts with this file, `v1.0.0` is a retroactive tag on the state the repo was already in before this file existed, not a claim that every change before it was individually documented.

## [1.2.0] - 2026-09-02

### Added
- `publish_inbox.py`: optional `date:` YAML frontmatter field, an explicit override for a page's displayed date, verified against the article's real original publish date where one exists elsewhere (e.g. an older blog). Falls back to a Notion export's own `backed_up:` timestamp if present (closer to a real date than nothing), then to this script's own git first-commit-date as the last resort, unchanged from before.
- `publish_inbox.py`: optional `summary:` YAML frontmatter field, a hand-written one-line excerpt written straight through into the generated page's own frontmatter (read back by a theme template as `page.header.summary`). Exists because Grav's own auto-computed `page.summary()` reads a page's *rendered* content by default, so a `[TOC]` widget rendering before any real prose leaked its own link text into any auto-generated summary.

### Fixed
- `publish_inbox.py`: every source file is now read with `encoding="utf-8-sig"` instead of plain `"utf-8"`, so a leading UTF-8 byte-order-mark (three bytes, EF BB BF, silently written by some tools, e.g. PowerShell's `Set-Content`/`Out-File` default to BOM'd UTF-8 unless told otherwise) no longer breaks frontmatter parsing. Previously, a BOM'd file's `---...---` block failed to match (the string starts with U+FEFF, not `-`) and fell through as literal, visible body text on the live page.
- `publish_inbox.py`: fixed a double-escaping bug where a frontmatter value already containing an escaped apostrophe (`it''s`, YAML's own single-quote escape) got escaped a second time on every subsequent read-then-write pass, visibly leaking as a doubled apostrophe (`it''''s`) on the live page. `extract_frontmatter()` now properly unescapes a single-quoted value on read, instead of just trimming the outer quote characters.

## [1.1.0] - 2026-09-02

### Added
- `clean_code_fences.py`: strips a stray leading space or tab from a fenced code block's first line, but only when every other line in that same block has none. Wired into `publish_vault.py`, runs automatically on every publish right after the image pass.
- `publish_inbox.py`: optional `category`/`tags` YAML frontmatter support. An article tagged `category: OPNSense` / `tags: [firewall, vlan]` gets that written into its Grav `taxonomy:` frontmatter, powering a categorized blog-style homepage (a Grav `blog` template + native taxonomy, not covered by this repo directly since it's a theme file, but the script-side support for it lives here).
- `publish_inbox.py`: raw HTML `<img>` tags (the shape some import scripts emit instead of Markdown syntax) are now converted to Markdown image syntax before the normal image-resolution pass, so they resolve and copy correctly instead of 404ing.
- `publish_inbox.py`: Obsidian callout syntax (`> [!info] Title`) is rewritten to GitHub's own alert syntax, rendered by the `github-markdown-alerts` Grav plugin instead of showing as a plain blockquote with literal `[!info]` text.
- `publish_inbox.py`: writes a plain-text `.txt` download copy of each article's original markdown alongside the generated page.
- `publish_inbox.py`: a series folder with exactly one `.md` part now collapses to a direct single page instead of an index page + one-item "Parts in this series" list. Keeps the *folder's* own slug as the URL (not the part's title-derived one), so this never changes a URL that's already live.
- `publish_inbox.py`: `Home.md`, `Search Articles.md` (formerly `All Articles.md`), and now also `About.md` are reserved vault-root filenames, each special-cased to overwrite a specific reserved Grav page rather than becoming an ordinary numbered article.

### Changed
- `README.md` updated throughout to match the above.

## [1.0.0] - 2026-08-30

Baseline snapshot: the pipeline as it stood after the initial build-out (documented in the "Self-host Obsidian and publish tutorials via an automated pipeline to Grav CMS" tutorial series, Parts 2 and 3). `optimize_images.py`, `publish_vault.py`, `publish_inbox.py`, and the Commit and Publish Obsidian plugin, all in their original form.
