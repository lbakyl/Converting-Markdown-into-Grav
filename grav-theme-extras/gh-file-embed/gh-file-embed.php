<?php
namespace Grav\Plugin;

use Grav\Common\Plugin;

/**
 * Class GhFileEmbedPlugin
 *
 * Registers the [gh-file] shortcode, which renders a placeholder <div> that
 * custom.js fills in client-side by fetching a file straight from a public
 * GitHub repo (raw.githubusercontent.com). Kept deliberately simple, no
 * server-side GitHub API calls or caching - the browser does the fetch, so
 * the vault never needs a second, easily-stale copy of the file's content.
 */
class GhFileEmbedPlugin extends Plugin
{
    public static function getSubscribedEvents()
    {
        return [
            'onShortcodeHandlers' => ['onShortcodeHandlers', 0],
        ];
    }

    public function onShortcodeHandlers()
    {
        $this->grav['shortcode']->registerAllShortcodes(__DIR__ . '/classes/shortcodes');
    }
}
