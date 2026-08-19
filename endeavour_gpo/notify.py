"""Desktop notifications for the logged-in user (from root gpupdate context)."""

from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path

log = logging.getLogger(__name__)


def notify_user(
    uid: int,
    username: str,
    title: str,
    body: str,
    *,
    urgency: str = "critical",
) -> None:
    """Show a libnotify desktop notification in the user's session."""
    notify_send = shutil.which("notify-send")
    if notify_send is None:
        log.debug("notify-send not installed; skipping notification")
        return

    runtime = Path(f"/run/user/{uid}")
    if not runtime.is_dir():
        log.debug("No session directory for uid %d; skipping notification", uid)
        return

    bus = runtime / "bus"
    env_prefix = [
        f"XDG_RUNTIME_DIR={runtime}",
        f"DBUS_SESSION_BUS_ADDRESS=unix:path={bus}",
    ]
    cmd = ["runuser", "-u", username, "--", "env", *env_prefix, notify_send]
    if shutil.which("runuser") is None:
        cmd = ["sudo", "-u", username, "env", *env_prefix, notify_send]

    cmd.extend(["-u", urgency, "-a", "endeavour-gpo", title, body])
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        log.debug(
            "notify-send failed (uid=%d): %s",
            uid,
            proc.stderr.strip() or proc.stdout.strip(),
        )
