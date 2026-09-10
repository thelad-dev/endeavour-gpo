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
    "endeavour-gpo-ac-nosleep.service",
    "endeavour-gpo-ac-nosleep-sync.service",
    "endeavour-gpo-ac-nosleep.timer",
    "endeavour-gpo-nm-prelogin.service",
)

USER_UNIT_FILES = ("endeavour-gpupdate-session.service",)

SUDOERS_SESSION = """# Managed by endeavour-gpo-register.
# Session-Hook darf User-GPO (Laufwerke) ohne Passwort als root anwenden.
Defaults!/usr/local/lib/endeavour-gpo/endeavour-gpupdate-session.sh !requiretty
ALL ALL=(root) NOPASSWD: /usr/local/lib/endeavour-gpo/endeavour-gpupdate-session.sh
"""

EXTRA_DRIVES_EXAMPLE = """# Zusätzliche CIFS-Laufwerke neben GPP Drives / AD-Home.
# Eine Zeile: //server/share  Ordnername
# Ordnername ist relativ zu ~/netzlaufwerke/
#
# Beispiel:
# //dfs/Marketing  M_Marketing
"""

LOGIND_NOSLEEP = """# endeavour-gpo: Idle/Deckel aus; Power-Taste = Suspend
[Login]
IdleAction=ignore
HandleSuspendKey=suspend
HandleHibernateKey=ignore
HandleLidSwitch=ignore
HandleLidSwitchExternalPower=ignore
HandleLidSwitchDocked=ignore
HandlePowerKey=suspend
"""

SMB_INCLUDE = """# Managed by endeavour-gpo-register — do not edit by hand unless needed.
[global]
    apply group policies = yes
    # Offline-Login für AD-Konten (pam_winbind cached_login)
    winbind offline logon = yes
"""

NM_CONF = """# endeavour-gpo: Netz vor dem Login (systemweite Verbindungen)
[main]
no-auto-default=*

[device]
# Alle Geräte von NM verwalten lassen
wifi.scan-rand-mac-address=no
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

    session_src = scripts_dir / "endeavour-gpupdate-session.sh"
    if session_src.is_file():
        session_dest = Path("/usr/local/lib/endeavour-gpo/endeavour-gpupdate-session.sh")
        session_dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(session_src, session_dest)
        os.chmod(session_dest, 0o755)
        print(f"Installiert {session_dest}")

    _install_user_units(src_dir)
    _install_sudoers_session()
    _install_extra_drives_example()

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
        logind = Path("/etc/systemd/logind.conf.d/90-endeavour-gpo-ac-nosleep.conf")
        logind.parent.mkdir(parents=True, exist_ok=True)
        logind.write_text(LOGIND_NOSLEEP, encoding="utf-8")
        # ältere Drop-in-Namen entfernen
        Path("/etc/systemd/logind.conf.d/90-no-sleep-on-ac.conf").unlink(missing_ok=True)
        print(f"Installiert {logind}")
        xdg = Path("/etc/xdg/powerdevilrc")
        xdg.parent.mkdir(parents=True, exist_ok=True)
        xdg.write_text(
            "[AC][SuspendAndShutdown]\n"
            "AutoSuspendAction=0\n"
            "AutoSuspendIdleTimeoutSec=0\n"
            "LidAction=0\n"
            "PowerButtonAction=1\n"
            "PowerDownAction=0\n"
            "InhibitLidActionWhenExternalMonitorPresent=true\n"
            "SleepMode=0\n"
            "\n"
            "[AC][Display]\n"
            "DimDisplayWhenIdle=false\n"
            "TurnOffDisplayWhenIdle=false\n"
            "TurnOffDisplayIdleTimeoutSec=0\n"
            "LockBeforeTurnOffDisplay=false\n",
            encoding="utf-8",
        )
        print(f"Installiert {xdg}")
        subprocess.run(["udevadm", "control", "--reload"], check=False)
        subprocess.run([str(guard_dest), "sync"], check=False)

    _install_prelogin_network(scripts_dir, src_dir)
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
    subprocess.run(
        ["systemctl", "--global", "enable", "endeavour-gpupdate-session.service"],
        check=False,
    )
    subprocess.run(
        ["systemctl", "enable", "--now", "endeavour-gpo-ac-nosleep.service"],
        check=False,
    )
    subprocess.run(
        ["systemctl", "enable", "--now", "endeavour-gpo-ac-nosleep.timer"],
        check=False,
    )
    subprocess.run(
        ["systemctl", "enable", "--now", "endeavour-gpo-nm-prelogin.service"],
        check=False,
    )


def _install_user_units(src_dir: Path) -> None:
    """systemd --user unit: GPO drive maps after graphical-session.target."""
    user_dest = Path("/etc/systemd/user")
    user_dest.mkdir(parents=True, exist_ok=True)
    user_src_dir = src_dir / "user"
    for name in USER_UNIT_FILES:
        src = user_src_dir / name
        if not src.is_file():
            src = src_dir / name
        if not src.is_file():
            print(f"Warnung: User-Unit fehlt: {name}", file=sys.stderr)
            continue
        target = user_dest / name
        shutil.copy2(src, target)
        print(f"Installiert {target}")


def _install_sudoers_session() -> None:
    dest = Path("/etc/sudoers.d/endeavour-gpupdate")
    tmp = dest.with_suffix(".tmp")
    tmp.write_text(SUDOERS_SESSION, encoding="utf-8")
    os.chmod(tmp, 0o440)
    check = subprocess.run(
        ["visudo", "-c", "-f", str(tmp)],
        capture_output=True,
        text=True,
        check=False,
    )
    if check.returncode != 0:
        tmp.unlink(missing_ok=True)
        print(
            "Warnung: sudoers für Session-Hook ungültig, nicht installiert: "
            + (check.stderr or check.stdout).strip(),
            file=sys.stderr,
        )
        return
    tmp.replace(dest)
    os.chmod(dest, 0o440)
    print(f"Installiert {dest}")


def _install_extra_drives_example() -> None:
    dest = Path("/etc/endeavour-gpo/extra-drives.conf")
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        return
    dest.write_text(EXTRA_DRIVES_EXAMPLE, encoding="utf-8")
    os.chmod(dest, 0o644)
    print(f"Installiert {dest}")


def _install_prelogin_network(scripts_dir: Path, systemd_dir: Path) -> None:
    """Systemweite NM-Verbindungen vor dem Display-Manager aktivieren."""
    nm_src = scripts_dir / "nm-prelogin-up.sh"
    if nm_src.is_file():
        nm_dest = Path("/usr/local/lib/endeavour-gpo/nm-prelogin-up.sh")
        nm_dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(nm_src, nm_dest)
        os.chmod(nm_dest, 0o755)
        print(f"Installiert {nm_dest}")

    dropin_src = systemd_dir / "plasmalogin.service.d-network.conf"
    if dropin_src.is_file():
        dropin_dir = Path("/etc/systemd/system/plasmalogin.service.d")
        dropin_dir.mkdir(parents=True, exist_ok=True)
        dropin_dest = dropin_dir / "20-endeavour-gpo-network.conf"
        shutil.copy2(dropin_src, dropin_dest)
        print(f"Installiert {dropin_dest}")

    nm_conf_dir = Path("/etc/NetworkManager/conf.d")
    nm_conf_dir.mkdir(parents=True, exist_ok=True)
    nm_conf = nm_conf_dir / "20-endeavour-gpo-prelogin.conf"
    nm_conf.write_text(NM_CONF, encoding="utf-8")
    print(f"Installiert {nm_conf}")

    # Vorhandene System-Connections: systemweit + Autoconnect
    try:
        listed = subprocess.run(
            ["nmcli", "-t", "-f", "UUID,FILENAME", "connection", "show"],
            check=False,
            capture_output=True,
            text=True,
        )
        for line in listed.stdout.splitlines():
            if ":" not in line:
                continue
            uuid, _, filename = line.partition(":")
            if "/etc/NetworkManager/system-connections/" not in filename:
                continue
            subprocess.run(
                [
                    "nmcli",
                    "connection",
                    "modify",
                    "uuid",
                    uuid,
                    "connection.permissions",
                    "",
                    "connection.autoconnect",
                    "yes",
                ],
                check=False,
                capture_output=True,
            )
            print(f"NM-Verbindung {uuid}: systemweit, autoconnect=yes")
    except FileNotFoundError:
        print("Warnung: nmcli fehlt — NM-Verbindungen nicht angepasst.", file=sys.stderr)

    subprocess.run(["systemctl", "try-reload-or-restart", "NetworkManager"], check=False)


def _install_cups_smb_krb5_backend(scripts_dir: Path) -> None:
    """Install root-only CUPS smb backend that forwards AUTH_UID to Samba's wrapper.

    Never writes to /usr/bin/smbspool — a past symlink-follow bug overwrote the
    real binary and caused an infinite wrapper loop.
    """
    src = scripts_dir / "cups-smb-krb5-backend.sh"
    if not src.is_file():
        print(f"Warnung: CUPS-Backend-Skript fehlt: {src}", file=sys.stderr)
        return

    real_smbspool = Path("/usr/bin/smbspool")
    if real_smbspool.is_file():
        with real_smbspool.open("rb") as fh:
            magic = fh.read(4)
        if magic != b"\x7fELF":
            print(
                "FEHLER: /usr/bin/smbspool ist kein ELF-Binary "
                "(vermutlich überschrieben). Bitte: pacman -S smbclient",
                file=sys.stderr,
            )
            return

    backend = Path("/usr/lib/cups/backend/smb")
    backup = Path("/usr/lib/cups/backend/smb.endeavour-gpo-orig")
    if backend.is_symlink():
        target = os.readlink(backend)
        if not backup.exists():
            backup.write_text(target + "\n", encoding="utf-8")
        backend.unlink()
    elif backend.is_file() and not backup.exists():
        # Only back up non-script leftovers; do not follow links.
        backend.unlink()
    if backend.exists() or backend.is_symlink():
        backend.unlink()
    shutil.copy2(src, backend)
    os.chmod(backend, 0o700)
    os.chown(backend, 0, 0)
    print(f"Installiert CUPS-Backend {backend} (Kerberos-Shim → smbspool_krb5_wrapper)")
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
