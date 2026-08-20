"""CLI: endeavour-gpupdate — Windows-ähnliches gpupdate /force für Samba."""

from __future__ import annotations

import argparse
import glob
import os
import pwd
import shutil
import subprocess
import sys
from pathlib import Path


def _default_krb5cc(uid: int) -> str | None:
    env = os.environ.get("KRB5CCNAME")
    if env:
        return env
    candidates = [
        f"/tmp/krb5cc_{uid}",
        f"/run/user/{uid}/krb5cc",
    ]
    for path in candidates:
        if os.path.exists(path):
            return path
    # KEYRING is opaque; leave unset and let krb5 decide.
    for path in glob.glob(f"/tmp/krb5cc_{uid}_*"):
        return path
    return None


def _samba_gpupdate() -> str:
    path = shutil.which("samba-gpupdate")
    if not path:
        raise SystemExit("samba-gpupdate nicht gefunden (Samba-Paket installieren).")
    return path


def _run(cmd: list[str], *, env: dict[str, str] | None = None) -> int:
    print("+", " ".join(cmd), flush=True)
    proc = subprocess.run(cmd, env=env)
    return proc.returncode


def _user_update(
    *,
    username: str,
    uid: int,
    force: bool,
    rsop: bool,
    unapply: bool,
    extra: list[str],
) -> int:
    gp = _samba_gpupdate()
    cmd = [gp, "--target=User", "-U", username, "--use-kerberos=required"]
    if force:
        cmd.append("--force")
    if rsop:
        cmd.append("--rsop")
    if unapply:
        cmd.append("--unapply")
    cmd.extend(extra)

    env = os.environ.copy()
    ccache = _default_krb5cc(uid)
    if ccache:
        env["KRB5CCNAME"] = ccache
    elif "KRB5CCNAME" not in env:
        env["KRB5CCNAME"] = f"/tmp/krb5cc_{uid}"

    if os.geteuid() == 0:
        return _run(cmd, env=env)

    # Non-root: escalate with sudo, preserve ccache.
    sudo = shutil.which("sudo") or "sudo"
    return _run([sudo, "-E", f"KRB5CCNAME={env['KRB5CCNAME']}", *cmd], env=env)


def _computer_update(*, force: bool, rsop: bool, unapply: bool, extra: list[str]) -> int:
    gp = _samba_gpupdate()
    cmd = [gp, "--target=Computer"]
    if force:
        cmd.append("--force")
    if rsop:
        cmd.append("--rsop")
    if unapply:
        cmd.append("--unapply")
    cmd.extend(extra)
    if os.geteuid() != 0:
        sudo = shutil.which("sudo") or "sudo"
        cmd = [sudo, *cmd]
    return _run(cmd)


def _active_gui_sessions() -> list[tuple[str, int]]:
    """Return (username, uid) for sessions with a usable runtime dir."""
    found: dict[str, int] = {}
    try:
        proc = subprocess.run(
            ["loginctl", "list-sessions", "--no-legend"],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        proc = None
    if proc and proc.returncode == 0:
        for line in proc.stdout.splitlines():
            parts = line.split()
            if len(parts) < 3:
                continue
            session_id, user = parts[0], parts[2]
            show = subprocess.run(
                ["loginctl", "show-session", session_id, "-p", "Name", "-p", "UID", "-p", "Active"],
                capture_output=True,
                text=True,
                check=False,
            )
            if show.returncode != 0:
                continue
            props = dict(
                p.split("=", 1) for p in show.stdout.splitlines() if "=" in p
            )
            if props.get("Active", "no") != "yes" and props.get("State") not in (
                "active",
                "online",
            ):
                # still accept if runtime dir exists
                pass
            name = props.get("Name") or user
            try:
                uid = int(props.get("UID", ""))
            except ValueError:
                continue
            if Path(f"/run/user/{uid}").is_dir():
                found[name] = uid
    if not found and os.geteuid() != 0:
        pw = pwd.getpwuid(os.getuid())
        found[pw.pw_name] = pw.pw_uid
    return sorted(found.items(), key=lambda x: x[1])


def _invoking_user() -> tuple[str, int]:
    """Resolve the interactive user when started via sudo/pkexec."""
    for key in ("SUDO_USER", "PKEXEC_UID"):
        if key == "SUDO_USER":
            name = os.environ.get("SUDO_USER")
            if name and name != "root":
                try:
                    pw = pwd.getpwnam(name)
                    return pw.pw_name, pw.pw_uid
                except KeyError:
                    pass
        elif key == "PKEXEC_UID":
            raw = os.environ.get("PKEXEC_UID")
            if raw and raw.isdigit():
                try:
                    pw = pwd.getpwuid(int(raw))
                    if pw.pw_name != "root":
                        return pw.pw_name, pw.pw_uid
                except KeyError:
                    pass
    pw = pwd.getpwuid(os.getuid())
    return pw.pw_name, pw.pw_uid


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="endeavour-gpupdate",
        description="Wendet AD-Gruppenrichtlinien an (Samba), analog zu Windows gpupdate /force.",
    )
    parser.add_argument(
        "--force",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Entspricht gpupdate /force (Standard: an)",
    )
    parser.add_argument("--rsop", action="store_true", help="Resultant Set of Policy ausgeben")
    parser.add_argument("--unapply", action="store_true", help="Richtlinien zurücknehmen")
    parser.add_argument(
        "--computer",
        action="store_true",
        help="Nur Computer-Richtlinien",
    )
    parser.add_argument(
        "--user",
        action="store_true",
        help="Nur User-Richtlinien (Standard, wenn weder --computer noch --all-sessions)",
    )
    parser.add_argument(
        "--all-sessions",
        action="store_true",
        help="Computer + User-Update für alle aktiven Sitzungen (Timer/Remote)",
    )
    parser.add_argument(
        "-U",
        "--username",
        default=None,
        help="AD-/lokaler Benutzername (Standard: aktueller User)",
    )
    parser.add_argument(
        "extra",
        nargs=argparse.REMAINDER,
        help="Zusätzliche Argumente für samba-gpupdate (nach --)",
    )
    args = parser.parse_args(argv)
    extra = list(args.extra)
    if extra and extra[0] == "--":
        extra = extra[1:]

    rc = 0
    do_computer = args.computer or args.all_sessions
    do_user = args.user or args.all_sessions or (not args.computer)

    if do_computer:
        rc = _computer_update(
            force=args.force, rsop=args.rsop, unapply=args.unapply, extra=extra
        )
        if rc != 0 and not args.rsop:
            return rc

    if do_user:
        if args.all_sessions:
            sessions = _active_gui_sessions()
            if not sessions:
                print("Keine aktiven User-Sitzungen gefunden.", file=sys.stderr)
            for name, uid in sessions:
                code = _user_update(
                    username=name,
                    uid=uid,
                    force=args.force,
                    rsop=args.rsop,
                    unapply=args.unapply,
                    extra=extra,
                )
                if code != 0:
                    rc = code
        else:
            if args.username:
                name = args.username.split("\\")[-1]
                try:
                    uid = pwd.getpwnam(name).pw_uid
                except KeyError:
                    print(f"Benutzer nicht gefunden: {name}", file=sys.stderr)
                    return 1
            else:
                name, uid = _invoking_user()
                if name == "root":
                    print(
                        "Als root ohne SUDO_USER: bitte -U <benutzer> oder --all-sessions nutzen.",
                        file=sys.stderr,
                    )
                    return 1
            rc = _user_update(
                username=name,
                uid=uid,
                force=args.force,
                rsop=args.rsop,
                unapply=args.unapply,
                extra=extra,
            )
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
