# gh-file-embed

A small Grav plugin adding a `[gh-file]` shortcode that embeds a live
preview of a file from a public GitHub repo directly in a page, so a
template that is really maintained in Gitea or GitHub never needs a
second, easily-stale copy pasted into the vault.

See the main repo's [README.md](../../README.md) for the full write-up,
including what it does, how it is built, and the gotchas hit along the
way.

## Install

1. Copy `gh-file-embed.php`, `gh-file-embed.yaml`, `blueprints.yaml`, and
   `classes/` into `user/plugins/gh-file-embed/` on the Grav site. The
   `shortcode-core` plugin must already be installed and enabled.
2. Add `theme-snippets/custom.js.snippet.js`'s function to the theme's own
   `custom.js` (or equivalent), and call it alongside the theme's other
   init functions.
3. Add `theme-snippets/custom.css.snippet.css`'s rules to the theme's own
   `custom.css` (or equivalent), swapping in plain color values if the
   theme has no CSS custom properties of its own.
4. Clear Grav's cache (`bin/grav clearcache`).

## Usage

```text
[gh-file repo="owner/repo" path="path/to/file.yml"]
```

Optional attributes: `branch` (default `main`), `lines="N"` (show only
the first N lines with a "Show full file" button underneath; leave it
off to show the whole file with no button at all), `lang` (guessed from
the file extension if left out, only affects the code block's CSS
class, there is no syntax highlighter built in).
