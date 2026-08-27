const { Plugin, Notice } = require("obsidian");
const { execFile } = require("child_process");
const path = require("path");
const fs = require("fs");

// Absolute interpreter path, and the windowless variant specifically:
// pythonw.exe has no console subsystem at all, so there's nothing to
// flash on screen. It's only safe to use because this plugin captures
// its stdout/stderr through Node's own pipes (confirmed working -
// pythonw.exe's sys.stdout is a real stream in that case, not None, so
// publish_vault.py's normal print() calls don't crash it).
//
// Backslashes, deliberately - confirmed by testing directly that Node's
// child_process.execFile fails with ENOENT on this exact path when given
// forward slashes instead, even though the file genuinely exists. This
// is the opposite requirement from git's core.sshCommand elsewhere in
// this project (which needs forward slashes because it's interpreted by
// Git for Windows' bundled sh.exe); execFile here calls Windows' process
// creation directly, no shell involved, so it needs native path syntax.
const PYTHONW = "C:\\Python311\\pythonw.exe";

// Hardcoded, not read from Obsidian Git's settings: this plugin is meant
// to work whether or not Obsidian Git is even enabled (that was the
// whole point of not routing through its commit command), so the repo
// folder can't depend on asking a plugin that might not be running.
// Confirmed by testing: when Obsidian Git was disabled, reading its
// settings for this silently fell back to the vault root instead, and
// publish_vault.py genuinely wasn't there.
const REPO_SUBPATH = "Published";

// Deliberately NOT using __dirname here: Obsidian doesn't load plugins
// through Node's normal require(), it uses its own loader, and __dirname
// isn't guaranteed to resolve correctly in that context (this may be
// exactly why the first version of this logging never produced a file
// at all). Built instead from the vault's own confirmed-working base
// path, so there's no dependency on module-loading internals.
function logPath(app) {
  const adapter = app.vault.adapter;
  const vaultBase = typeof adapter.getBasePath === "function" ? adapter.getBasePath() : adapter.basePath;
  return path.join(vaultBase, ".obsidian", "plugins", "commit-and-publish", "debug.log");
}

// Cleared at the start of every publish() call (see clearLog below), so
// the file only ever holds the current run's entries rather than growing
// forever - within one run, log() still appends, so a run's "start" and
// "result" entries both survive together.
function clearLog(app) {
  try {
    fs.writeFileSync(logPath(app), "");
  } catch (e) {
    console.error("[commit-and-publish] failed to clear debug.log", e);
  }
}

function log(app, ...parts) {
  const line = `[${new Date().toISOString()}] ` + parts.map(p =>
    typeof p === "string" ? p : JSON.stringify(p, Object.getOwnPropertyNames(p || {}))
  ).join(" ") + "\n";
  try {
    fs.appendFileSync(logPath(app), line);
  } catch (e) {
    console.error("[commit-and-publish] failed to write debug.log", e);
    // Last-resort fallback: at least try to leave *something* on disk,
    // right next to the vault root, in case the plugin-folder path
    // itself is somehow the problem.
    try {
      fs.appendFileSync(path.join(app.vault.adapter.getBasePath(), "commit-and-publish-debug.log"), line);
    } catch (e2) {}
  }
}

module.exports = class CommitAndPublishPlugin extends Plugin {
  onload() {
    this.addCommand({
      id: "commit-and-publish",
      name: "Commit and Publish",
      callback: () => this.publish(),
    });
  }

  publish() {
    clearLog(this.app);
    try {
      const adapter = this.app.vault.adapter;
      const vaultBase = typeof adapter.getBasePath === "function" ? adapter.getBasePath() : adapter.basePath;
      const repoPath = path.join(vaultBase, REPO_SUBPATH);

      log(this.app, "start", {
        vaultBase,
        repoPath,
        cwdExists: fs.existsSync(repoPath),
        scriptExists: fs.existsSync(path.join(repoPath, "publish_vault.py")),
        pythonwExists: fs.existsSync(PYTHONW),
      });

      new Notice("Publishing...");
      execFile(
        PYTHONW,
        ["publish_vault.py"],
        { cwd: repoPath, windowsHide: true, timeout: 60000 },
        (error, stdout, stderr) => {
          log(this.app, "result", {
            error: error ? { message: error.message, code: error.code, errno: error.errno } : null,
            stdout,
            stderr,
          });
          if (error) {
            new Notice("Publish failed - check it manually.", 8000);
            return;
          }
          new Notice(this.summarize(stdout), 6000);
        }
      );
    } catch (e) {
      log(this.app, "SYNCHRONOUS ERROR", { message: e.message, stack: e.stack });
      new Notice("Publish failed immediately - see debug.log");
    }
  }

  summarize(stdout) {
    if (/Nothing to commit or push\./.test(stdout)) return "Nothing to publish.";
    const resized = (stdout.match(/resized /g) || []).length;
    const renamed = (stdout.match(/renamed /g) || []).length;
    if (resized || renamed) {
      return `Published - ${renamed} image(s) renamed, ${resized} resized.`;
    }
    return "Published.";
  }
};
