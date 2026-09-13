# Changelog

All notable changes to this repo's scripts are recorded here. Versioning starts with this file, `v1.0.0` is a retroactive tag on the state the repo was already in before this file existed, not a claim that every change before it was individually documented.

## [1.7.0] - 2026-09-13

### Added
- `publish_inbox.py`: every real article (a standalone page, or one of a series' own parts) now gets `comments: true` written into its frontmatter automatically - the one switch the community Comments Pro plugin (installed separately, not part of this repo) needs before it will render anything on that page. Left off a series' own overview page and the home/search/about special pages, matching the same set of pages the existing "More in category" and support-frame template blocks already exclude.

## [1.6.0] - 2026-09-12

### Added
- `publish_inbox.py`: an embedded SVG now gets the same lightbox click-to-enlarge as a raster screenshot, built as a hand-written raw HTML anchor (`rel="lightbox" data-featherlight="image"`) rather than through Grav's own image querystring action, which can't rasterize a real thumbnail from a vector image and would show a generic icon in the popup instead. Its `href`/`src` is computed as the page's own absolute route (a new `page_route()` helper, stripping each folder's leading `NN.` order prefix the same way Grav's routing does) rather than a bare filename - a bare filename resolves through the *browser's* relative-URL rules instead of Grav's page-media-aware ones, landing one directory too shallow on a nested (series part) route. Confirmed live, both the failure and the fix, on a real architecture diagram.

### Fixed
- `publish_inbox.py`: a standard Markdown image's alt text is now stripped of a trailing `|<width>` (or `|<width>x<height>`) suffix, Obsidian's own live preview silently appends this to the alt text whenever the embed is resized by dragging its corner, so what's meant to be a real, human-written description was leaking an internal pixel hint that changes every time the image is casually resized again. Confirmed live on the same diagram above.

## [1.5.0] - 2026-09-12

### Added
- `publish_inbox.py`: the generated homepage now carries a `content:` collection header (every top-level page, newest first) and `feed: skip: true`, and the generated search/about pages get `feed: skip: true` too. Together these are the only two things the community Feed plugin needs to serve a real RSS/Atom feed of every article, without the search/about listing pages themselves showing up as fake articles in it. The plugin itself isn't part of this repo (`bin/gpm install feed`), just the frontmatter that activates it.

## [1.4.0] - 2026-09-12

### Added
- `publish_inbox.py`: an optional `redirects:` frontmatter field (a list, same two shapes as `tags:`) of old URLs that should render this same page instead of 404ing, via Grav's own `routes: aliases:` (a 200, not a real 301, but enough to stop a dead link). Added after a pre-migration WordPress permalink was found live-broken: a single-part series' slug is deliberately taken from its *folder* name rather than its title (so a later title edit never changes an already-live URL), and here the folder name and title had drifted apart (`PVE 8x` vs `PVE 8.x`), leaving the site's own live slug one hyphen short of what the title, and the old WordPress permalink Google had indexed, would have produced.

### Fixed
- `publish_inbox.py`: an SVG exported at a percentage width with no height at all (common from diagramming tools built for their own inline, responsive use, Mermaid's own "Export as SVG" included) rendered at the browser's generic fallback size once embedded as a plain `<img>` instead, confirmed live on a real architecture diagram: a near-square image showed as a tiny 150x150 square inline, and collapsed to zero height entirely inside the theme's lightbox popup. Every copied `.svg` now has its root `width`/`height` rewritten to explicit pixel values taken from its own `viewBox`, so this fixes itself instead of requiring the source file to be hand-edited before it can be dropped in.

## [1.3.2] - 2026-09-12

### Fixed
- `publish_inbox.py`: every embedded image, SVG included, got the same `?classes=thumb-half&lightbox=3000,3000` treatment as a raster screenshot. Grav has no way to rasterize a thumbnail from an SVG, so wrapping one in the lightbox action rendered `media.yaml`'s generic vector-file icon in place of the actual diagram on click, confirmed live against a real architecture diagram. `.svg` files now keep the same inline sizing class but skip the lightbox action, so they display directly instead.

## [1.3.1] - 2026-09-12

### Fixed
- `publish_inbox.py`: `PART_NUM_RE` only matched "part" followed by whitespace then a digit, so a slug-style series folder like `part-1-some-long-title` (hyphen, not whitespace, between "part" and the number) never matched at all. Both parts of a 2-part series fell through to the same fallback sort key and ended up in whatever arbitrary order the filesystem listed them, not the real part sequence - confirmed live, this displayed Part 2 before Part 1 with no error anywhere. Now accepts whitespace, `_`, or `-` between "part" and the digit.

## [1.3.0] - 2026-09-11

### Added
- A new Grav plugin, `gh-file-embed`, adding a `[gh-file repo="owner/repo" path="path/to/file.yml"]` shortcode that embeds a live preview of a file from a public GitHub repo directly in a page, fetched client side, with an optional `lines="N"` preview and expand button. Not part of the publish pipeline itself, included under `grav-theme-extras/` since it was built and documented in the same session as the rest of this repo. See the new README section for the full write-up.

### Fixed
- A backup copy of the shortcode's own PHP file left inside `classes/shortcodes/` (the directory `shortcode-core` blindly `require_once`s every file from) caused a site-wide fatal error, "Cannot declare class ..., because the name is already in use." Backups now go outside any directory a plugin scans.
- The theme's `.button-secondary` class overrides the browser's native `hidden` attribute behavior (no `:not([hidden])` guard on its `display: inline-block`), so the shortcode's "Show full file" button rendered as an empty box even when it had nothing to expand. Fixed with an explicit `.gh-file-embed-toggle[hidden] { display: none !important; }` rule.
- Grav's `system.yaml` now sets `assets.enable_asset_timestamp: true`, so a CSS/JS deploy always gets a new URL instead of risking a CDN serving a stale cached copy of the old one past its own declared cache lifetime (observed directly: a stale hit 2301 seconds past a declared 1800 second max-age).

## [1.2.2] - 2026-09-07

### Fixed
- `publish_inbox.py`: `part_sort_key()` only ever looked at a part's own filename for "Part N", never its containing folder. Once every part in a series gets renamed to the same generic filename (e.g. `index.md`, no "Part N" left to find), they all collapse to the same fallback sort key and end up ordered by whatever the filesystem happened to list them in, not the real part sequence - confirmed live, this scrambled a 4-part series' order (both the site's own "Parts in this series" list and the series' actual part-folder numbering). Now falls back to the parent folder's own name, which still says "Part N - <title>" even when the file inside doesn't.

## [1.2.1] - 2026-09-07

### Fixed
- `clean_code_fences.py`: `clean_vault()` walks the tree with `rglob()`, which lists a file's path lazily and only reads it a moment later as the loop reaches it. If Obsidian renames a file (or LiveSync is still mid-sync) in that window, the read hit a bare `FileNotFoundError` and crashed the whole publish over one file that no longer existed under its old name. Now caught and skipped per-file with a note, instead of aborting the run.

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
