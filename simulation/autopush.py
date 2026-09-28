"""Auto-publish — after a day is played, commit the generated artifacts
(charts, animation, the daily post, the fetched wire, the checkpoint) and
push them to the configured git remote.

Only the four artifact paths are staged, never the whole worktree, so
source edits made while the daemon is resident are never swept into an
automated commit.

Everything here fails soft and is time-boxed: a missing remote, an
unreachable network, a rejected push or a passphrase-protected key logs a
line and the daemon carries on. A push is never forced and history is
never rewritten — if the remote has diverged, the commit simply stays
local and goes out with the next successful push.

Disable with --no-push, or SIM_AUTOPUSH=0.
"""

from __future__ import annotations

import os
import subprocess

# staged explicitly; missing paths are skipped
ARTIFACTS = ("media", "posts", "real_events")
TIMEOUT = 120
# never block on a passphrase / host-key prompt in an unattended loop
GIT_ENV = {
    "GIT_SSH_COMMAND": "ssh -o BatchMode=yes -o StrictHostKeyChecking=accept-new",
    "GIT_TERMINAL_PROMPT": "0",
    "GIT_ASKPASS": "true",
    "SSH_ASKPASS": "true",
}


def enabled() -> bool:
    return os.environ.get("SIM_AUTOPUSH", "1") not in ("0", "false", "no")


def _reason(out: str, code: int) -> str:
    """The most informative line of a failed git invocation."""
    lines = [l.strip() for l in out.splitlines() if l.strip()]
    for line in lines:
        low = line.lower()
        if any(k in low for k in ("rejected", "error:", "fatal:", "denied",
                                  "timed out", "could not read")):
            return line
    return lines[-1] if lines else f"exit {code}"


def _git(*args: str, root: str) -> tuple[int, str]:
    """Run a git command, returning (returncode, merged output)."""
    env = {**os.environ, **GIT_ENV}
    try:
        r = subprocess.run(("git", *args), cwd=root, env=env,
                           capture_output=True, text=True, timeout=TIMEOUT)
    except (subprocess.TimeoutExpired, OSError) as exc:
        return 1, f"{type(exc).__name__}: {exc}"
    return r.returncode, (r.stdout + r.stderr).strip()


def publish(day_no: int, dump_path: str, root: str | None = None,
            log=print) -> bool:
    """Commit + push the day's artifacts. Returns True only if the push
    reached the remote. Never raises."""
    root = root or os.getcwd()
    if not enabled():
        return False

    code, _ = _git("rev-parse", "--git-dir", root=root)
    if code:
        log("  [PUSH] not a git repository — skipping")
        return False
    code, remote = _git("remote", root=root)
    if code or not remote:
        log("  [PUSH] no git remote configured — skipping")
        return False

    paths = [p for p in (*ARTIFACTS, dump_path)
             if os.path.exists(os.path.join(root, p))]
    if not paths:
        log("  [PUSH] nothing generated to publish")
        return False

    code, out = _git("add", "--", *paths, root=root)
    if code:
        log(f"  [PUSH] git add failed: {_reason(out, code)}")
        return False

    # anything actually staged? (charts can be byte-identical on a rerun)
    if _git("diff", "--cached", "--quiet", root=root)[0] == 0:
        log("  [PUSH] artifacts unchanged — nothing to commit")
        return False

    msg = (f"sim day {day_no}: predictions, charts, daily post\n\n"
           f"Automated commit by the simulation daemon.")
    code, out = _git("commit", "-m", msg, root=root)
    if code:
        log(f"  [PUSH] commit failed: {_reason(out, code)}")
        return False
    log(f"  [PUSH] committed day {day_no} artifacts")

    branch = _git("rev-parse", "--abbrev-ref", "HEAD", root=root)[1] or "HEAD"
    code, out = _git("push", "origin", branch, root=root)
    if code:
        log(f"  [PUSH] push failed: {_reason(out, code)} — commit kept "
            f"locally, will go out with the next successful run")
        return False
    log(f"  [PUSH] pushed day {day_no} to origin/{branch}")
    return True
