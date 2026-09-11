/* Add this function to the theme's own custom.js (or equivalent) and call
   it once, alongside whatever other init functions already run on
   DOMContentLoaded. It does nothing on a page with no .gh-file-embed
   element, so it is safe to call unconditionally on every page. */

/* --- GitHub file-embed widgets: each .gh-file-embed div (rendered by
   the [gh-file] shortcode) carries data-repo/data-path/data-branch/
   data-lines attributes but no content of its own - the actual file
   is fetched here, client-side, from GitHub's raw content endpoint
   (public repos serve that with Access-Control-Allow-Origin: *, so a
   plain fetch() from any origin works, no proxy needed). This keeps
   the vault from ever holding a second, easily-stale copy of a
   template that's really maintained in Gitea/GitHub. Preview shows
   the first data-lines lines; the toggle button swaps in the rest
   (already fetched, no second request) and back. --- */
function initGhFileEmbeds() {
    var embeds = document.querySelectorAll('.gh-file-embed');
    if (!embeds.length) return;

    embeds.forEach(function (el) {
        var repo = el.getAttribute('data-repo');
        var path = el.getAttribute('data-path');
        var branch = el.getAttribute('data-branch') || 'main';
        // No data-lines at all (author left `lines` off the shortcode)
        // means "show the whole file, no expand button" - a preview
        // cutoff is only wanted when the author actually asked for one.
        var previewLines = el.hasAttribute('data-lines')
            ? (parseInt(el.getAttribute('data-lines'), 10) || 50)
            : null;
        var codeEl = el.querySelector('code');
        var toggleBtn = el.querySelector('.gh-file-embed-toggle');
        var copyBtn = el.querySelector('.gh-file-embed-copy');
        if (!repo || !path || !codeEl) return;

        var rawUrl = 'https://raw.githubusercontent.com/' + repo + '/' + branch + '/' + path;
        var allLines = null;

        function render(expanded) {
            var shown = expanded ? allLines : allLines.slice(0, previewLines);
            codeEl.textContent = shown.join('\n');
            if (allLines.length > previewLines) {
                toggleBtn.hidden = false;
                toggleBtn.textContent = expanded
                    ? 'Show less'
                    : 'Show full file (' + (allLines.length - previewLines) + ' more lines)';
            }
        }

        fetch(rawUrl)
            .then(function (response) {
                if (!response.ok) throw new Error('HTTP ' + response.status);
                return response.text();
            })
            .then(function (text) {
                allLines = text.replace(/\n$/, '').split('\n');
                if (previewLines === null) {
                    // No `lines` attribute: show it all, toggle stays
                    // hidden (its CSS also forces this, see custom.css.snippet.css).
                    codeEl.textContent = allLines.join('\n');
                    return;
                }
                render(false);
                toggleBtn.addEventListener('click', function () {
                    render(toggleBtn.textContent === 'Show less' ? false : true);
                });
            })
            .catch(function (err) {
                codeEl.textContent = 'Could not load this file from GitHub (' + err.message +
                    '). You can still open it directly, see the "View on GitHub" link above.';
            });

        if (copyBtn) {
            copyBtn.addEventListener('click', function () {
                if (!allLines) return;
                var text = codeEl.textContent;
                var done = function () {
                    var original = copyBtn.textContent;
                    copyBtn.textContent = 'Copied!';
                    setTimeout(function () { copyBtn.textContent = original; }, 1500);
                };
                if (navigator.clipboard && navigator.clipboard.writeText) {
                    navigator.clipboard.writeText(text).then(done, function () {});
                }
            });
        }
    });
}

/* Call it wherever the theme's other page-load init functions run, for
   example:

   if (document.readyState === 'loading') {
       document.addEventListener('DOMContentLoaded', function () {
           initGhFileEmbeds();
       });
   } else {
       initGhFileEmbeds();
   }
*/
