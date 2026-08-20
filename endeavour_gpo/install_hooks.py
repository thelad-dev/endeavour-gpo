"""Install systemd units, Samba include, and login hooks."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

UNIT_FILES = (
    "endeavour-gpupdate.service",
    "endeavour-gpupdate.timer",
    "endeavour-gpupdate-remote@.service",
    "endeavour-gpupdate-remote.socket",
    "endeavour-gpupdate-login.service",
)

SMB_INCLUDE = """# Managed by endeavour-gpo-register — do not edit by hand unless needed.
[global]
    apply group policies = yes
"""


def _data_root() -> Path:
    """Bundled data next to this module (works for editable and wheel installs)."""
    bundled = Path(__file__).resolve().parent / "data"
    if (bundled / "systemd").is_dir():
        return bundled
    # Fallback: repo checkout layout
    repo = Path(__file__).resolve().parent.parent
    if (repo / "packaging" / "systemd").is_dir():
        return repo / "packaging"
    raise FileNotFoundError(
        "Packaging-Daten nicht gefunden (endeavour_gpo/data oder packaging/)."
    )


def install_systemd_units() -> None:
    data = _data_root()
    src_dir = data / "systemd" if (data / "systemd").is_dir() else data
    dest = Path("/etc/systemd/system")
    for name in UNIT_FILES:
        src = src_dir / name
        if not src.is_file():
            print(f"Warnung: Unit fehlt: {src}", file=sys.stderr)
            continue
        target = dest / name
        shutil.copy2(src, target)
        print(f"Installiert {target}")

    scripts_dir = data / "scripts"
    if not scripts_dir.is_dir():
        scripts_dir = Path(__file__).resolve().parent.parent / "scripts"

    login_src = scripts_dir / "endeavour-gpupdate-login.sh"
    if login_src.is_file():
        login_dest = Path("/usr/local/lib/endeavour-gpo/endeavour-gpupdate-login.sh")
        login_dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(login_src, login_dest)
        os.chmod(login_dest, 0o755)
        print(f"Installiert {login_dest}")

    remote_src = scripts_dir / "remote-gpupdate.sh"
    if remote_src.is_file():
        remote_dest = Path("/usr/local/bin/endeavour-gpupdate-remote")
        shutil.copy2(remote_src, remote_dest)
        os.chmod(remote_dest, 0o755)
        print(f"Installiert {remote_dest}")

    guard_src = scripts_dir / "ac-sleep-guard.sh"
    if guard_src.is_file():
        guard_dest = Path("/usr/local/lib/endeavour-gpo/ac-sleep-guard.sh")
        guard_dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(guard_src, guard_dest)
        os.chmod(guard_dest, 0o755)
        print(f"Installiert {guard_dest}")
        udev = Path("/etc/udev/rules.d/99-endeavour-gpo-ac-nosleep.rules")
        udev.write_text(
            "# endeavour-gpo: kein System-Sleep solange Netzteil steckt\n"
            'SUBSYSTEM=="power_supply", ENV{POWER_SUPPLY_TYPE}=="Mains", '
            'ENV{POWER_SUPPLY_ONLINE}=="1", '
            'RUN+="/usr/local/lib/endeavour-gpo/ac-sleep-guard.sh on"\n'
            'SUBSYSTEM=="power_supply", ENV{POWER_SUPPLY_TYPE}=="Mains", '
            'ENV{POWER_SUPPLY_ONLINE}=="0", '
            'RUN+="/usr/local/lib/endeavour-gpo/ac-sleep-guard.sh off"\n',
            encoding="utf-8",
        )
        print(f"Installiert {udev}")
        subprocess.run(["udevadm", "control", "--reload"], check=False)
        subprocess.run([str(guard_dest), "sync"], check=False)

    _install_cups_smb_krb5_backend(scripts_dir)

    subprocess.run(["systemctl", "daemon-reload"], check=False)
    subprocess.run(["systemctl", "enable", "--now", "endeavour-gpupdate.timer"], check=False)
    subprocess.run(
        ["systemctl", "enable", "--now", "endeavour-gpupdate-remote.socket"],
        check=False,
    )
    subprocess.run(
        ["systemctl", "enable", "endeavour-gpupdate-login.service"],
        check=False,
    )


def _install_cups_smb_krb5_backend(scripts_dir: Path) -> None:
    """Replace world-readable smb symlink with root-only Kerberos wrapper."""
    src = scripts_dir / "cups-smb-krb5-backend.sh"
    if not src.is_file():
        return
    backend = Path("/usr/lib/cups/backend/smb")
    backup = Path("/usr/lib/cups/backend/smb.endeavour-gpo-orig")
    if backend.is_symlink() or (backend.is_file() and not backup.exists()):
        if not backup.exists():
            # Keep a pointer to the real smbspool
            if backend.is_symlink():
                target = os.readlink(backend)
                backup.write_text(target + "\n", encoding="utf-8")
            else:
                shutil.copy2(backend, backup)
    # Install wrapper as mode 0700 so cupsd runs it as root (can read user tickets).
    shutil.copy2(src, backend)
    os.chmod(backend, 0o700)
    os.chown(backend, 0, 0)
    print(f"Installiert CUPS-Backend {backend} (Kerberos-Wrapper, mode 0700)")
    subprocess.run(["systemctl", "try-reload-or-restart", "cups"], check=False)


def ensure_samba_apply_gpo() -> None:
    conf = Path("/etc/samba/endeavour-gpo.conf")
    conf.write_text(SMB_INCLUDE, encoding="utf-8")
    print(f"Geschrieben {conf}")

    smb = Path("/etc/samba/smb.conf")
    if not smb.is_file():
        print("Warnung: /etc/samba/smb.conf fehlt — include manuell setzen.", file=sys.stderr)
        return
    text = smb.read_text(encoding="utf-8")
    marker = "include = /etc/samba/endeavour-gpo.conf"
    if marker in text:
        return
    lines = text.splitlines(keepends=True)
    out: list[str] = []
    inserted = False
    for line in lines:
        out.append(line)
        if not inserted and line.strip().lower() == "[global]":
            out.append(marker + "\n")
            inserted = True
    if not inserted:
        out.insert(0, marker + "\n")
    smb.write_text("".join(out), encoding="utf-8")
    print(f"Include in {smb} ergänzt")
    subprocess.run(["systemctl", "try-reload-or-restart", "winbind"], check=False)
