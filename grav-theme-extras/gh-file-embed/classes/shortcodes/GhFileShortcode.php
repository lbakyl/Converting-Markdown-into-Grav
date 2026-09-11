<?php
namespace Grav\Plugin\Shortcodes;

use Thunder\Shortcode\Shortcode\ShortcodeInterface;

/**
 * [gh-file repo="owner/repo" path="path/to/file.yml" branch="main" lines="50" lang="yaml"]
 *
 * Renders a placeholder that custom.js fills in by fetching the raw file
 * straight from GitHub in the visitor's own browser - see
 * initGhFileEmbeds() in learn2/js/custom.js. Only `repo` and `path` are
 * required; `branch` defaults to main, and `lang` is guessed from the
 * file extension if omitted (only affects which `language-*` CSS class
 * the <code> block gets, there's no highlighter).
 *
 * `lines` is deliberately NOT defaulted: omit it and the whole file
 * shows with no "Show full file" button at all (right for a short
 * snippet, e.g. ping.yml, where there's nothing worth collapsing) -
 * only set `lines="N"` when you actually want a preview + expand
 * button for a longer file. data-lines is only emitted when the author
 * set it, and custom.js treats a missing data-lines as "show it all,
 * no toggle" rather than falling back to some default cutoff.
 */
class GhFileShortcode extends Shortcode
{
    public function init()
    {
        $this->shortcode->getHandlers()->add('gh-file', function (ShortcodeInterface $sc) {
            $repo       = trim((string) $sc->getParameter('repo', ''), '/');
            $path       = trim((string) $sc->getParameter('path', ''), '/');
            $branch     = (string) $sc->getParameter('branch', 'main');
            $linesParam = $sc->getParameter('lines', null);
            $lines      = $linesParam !== null ? max(1, (int) $linesParam) : null;
            $lang       = (string) $sc->getParameter('lang', $this->guessLang($path));

            if ($repo === '' || $path === '') {
                return '<p><em>[gh-file] shortcode needs both a repo and a path attribute, e.g. '
                     . '[gh-file repo="owner/repo" path="templates/example.yml"]</em></p>';
            }

            $repoEsc   = self::escAttr($repo);
            $pathEsc   = self::escAttr($path);
            $branchEsc = self::escAttr($branch);
            $langEsc   = self::escAttr($lang);
            $fileName  = self::escAttr(basename($path));
            $blobUrl   = self::escAttr('https://github.com/' . $repo . '/blob/' . $branch . '/' . $path);
            $linesAttr = $lines !== null ? ' data-lines="' . $lines . '"' : '';

            return '<div class="gh-file-embed" data-repo="' . $repoEsc . '" data-path="' . $pathEsc
                 . '" data-branch="' . $branchEsc . '"' . $linesAttr . '">'
                 . '<div class="gh-file-embed-header">'
                 . '<span class="gh-file-embed-path">' . $fileName . '</span>'
                 . '<span class="gh-file-embed-actions">'
                 . '<button type="button" class="gh-file-embed-copy" title="Copy to clipboard">Copy</button>'
                 . '<a class="gh-file-embed-link" href="' . $blobUrl . '" target="_blank" rel="noopener">View on GitHub &#8599;</a>'
                 . '</span></div>'
                 . '<pre class="gh-file-embed-code"><code class="language-' . $langEsc . '">Loading from GitHub&hellip;</code></pre>'
                 . '<button type="button" class="button-secondary gh-file-embed-toggle" hidden></button>'
                 . '</div>';
        });
    }

    private function guessLang(string $path): string
    {
        $ext = strtolower(pathinfo($path, PATHINFO_EXTENSION));
        $map = [
            'yml' => 'yaml', 'yaml' => 'yaml',
            'sh' => 'bash', 'bash' => 'bash',
            'json' => 'json',
            'py' => 'python',
            'js' => 'javascript',
            'md' => 'markdown',
        ];
        return $map[$ext] ?? 'text';
    }
}
