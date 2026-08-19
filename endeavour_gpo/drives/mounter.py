"""mount.cifs integration for EndeavourOS / Linux domain members."""

from __future__ import annotations

import logging
import os
import pwd
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from endeavour_gpo.credentials import decrypt_cpassword
from endeavour_gpo.drives.parser import DriveMap

log = logging.getLogger(__name__)


class MountError(RuntimeError):
    pass


@dataclass
class MountSpec:
    source: str
    target: Path
    options: list[str]
    credentials_file: Optional[Path] = None
    systemd_unit_name: Optional[str] = None


class CifsMounter:
    """Apply drive maps using mount.cifs and optional systemd user units."""

    def __init__(
        self,
        username: str,
        runtime_root: Optional[Path] = None,
        *,
        uid: Optional[int] = None,
        gid: Optional[int] = None,
        home: Optional[Path] = None,
    ):
        self.username = username
        self.user_sam = username.split("\\")[-1]
        if uid is not None and gid is not None and home is not None:
            self.uid = uid
            self.gid = gid
            self.home = home
        else:
            self.pw = pwd.getpwnam(self.user_sam)
            self.uid = self.pw.pw_uid
            self.gid = self.pw.pw_gid
            self.home = Path(self.pw.pw_dir)
        if runtime_root is not None:
            self.runtime_root = runtime_root
        else:
            self.runtime_root = Path(f"/run/user/{self.uid}/endeavour-gpo/drives")

    def build_spec(self, drive: DriveMap, *, write_credentials: bool = True) -> MountSpec:
        letter = drive.mount_letter or "X"
        source = drive.cifs_source()
        if not source and drive.should_mount:
            raise MountError(f"Drive map {drive.uid} has no UNC path")

        target = self.runtime_root / letter
        options = [
            "uid=%d" % self.uid,
            "gid=%d" % self.gid,
            "file_mode=0644",
            "dir_mode=0755",
            "nosuid",
            "nodev",
        ]

        creds_file: Optional[Path] = None
        if drive.username:
            creds_file = self._credentials_path(letter)
            if write_credentials:
                password = ""
                if drive.password_enc:
                    password = decrypt_cpassword(drive.password_enc)
                self._write_credentials(creds_file, drive.username, password)
            options.append("credentials=%s" % creds_file)
        else:
            options.append("sec=krb5")

        if drive.persistent:
            options.append("_netdev")

        unit_name = None
        if drive.persistent and not drive.run_once:
            unit_name = "gpo-drive-%s.mount" % letter.lower()

        return MountSpec(
            source=source,
            target=target,
            options=options,
            credentials_file=creds_file,
            systemd_unit_name=unit_name,
        )

    def mount(self, drive: DriveMap) -> MountSpec:
        spec = self.build_spec(drive)
        spec.target.parent.mkdir(parents=True, exist_ok=True)
        spec.target.mkdir(parents=True, exist_ok=True)

        if self._is_mounted(spec.target):
            log.debug("Already mounted: %s", spec.target)
        else:
            cmd = [
                "mount.cifs",
                spec.source,
                str(spec.target),
                "-o",
                ",".join(spec.options),
            ]
            log.info("Mounting %s -> %s", spec.source, spec.target)
            proc = subprocess.run(cmd, capture_output=True, text=True)
            if proc.returncode != 0:
                raise MountError(proc.stderr.strip() or proc.stdout.strip() or "mount.cifs failed")

        if spec.systemd_unit_name:
            self._install_systemd_unit(spec)
        return spec

    def unmount(self, drive: DriveMap) -> None:
        letter = drive.mount_letter or "X"
        target = self.runtime_root / letter
        self._remove_systemd_unit(letter)
        self._credentials_path(letter).unlink(missing_ok=True)

        if target.exists() and self._is_mounted(target):
            proc = subprocess.run(["umount", str(target)], capture_output=True, text=True)
            if proc.returncode != 0:
                raise MountError(proc.stderr.strip() or "umount failed")
        if target.exists():
            try:
                target.rmdir()
            except OSError:
                pass

    def _credentials_path(self, letter: str) -> Path:
        cred_dir = self.home / ".cache" / "endeavour-gpo" / "credentials"
        return cred_dir / ("drive-%s.cred" % letter.lower())

    def _write_credentials(self, cred_path: Path, username: str, password: str) -> Path:
        cred_path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(cred_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as creds:
            creds.write("username=%s\npassword=%s\n" % (username, password))
        os.chmod(cred_path, 0o600)
        return cred_path

    def _systemd_unit_path(self, unit_name: str) -> Path:
        return self.home / ".config" / "systemd" / "user" / unit_name

    def _install_systemd_unit(self, spec: MountSpec) -> None:
        assert spec.systemd_unit_name is not None
        unit_path = self._systemd_unit_path(spec.systemd_unit_name)
        unit_path.parent.mkdir(parents=True, exist_ok=True)

        opts = list(spec.options)
        if spec.credentials_file is not None:
            opts = [o for o in opts if not o.startswith("credentials=")]
            opts.append("credentials=%s" % spec.credentials_file)

        content = """[Unit]
Description=GPO drive map %s
After=network-online.target
Wants=network-online.target

[Mount]
What=%s
Where=%s
Type=cifs
Options=%s

[Install]
WantedBy=default.target
""" % (
            spec.target.name,
            spec.source,
            spec.target,
            ",".join(opts),
        )
        unit_path.write_text(content, encoding="utf-8")
        subprocess.run(
            ["systemctl", "--user", "daemon-reload"],
            check=False,
            capture_output=True,
        )
        subprocess.run(
            ["systemctl", "--user", "enable", spec.systemd_unit_name],
            check=False,
            capture_output=True,
        )

    def _remove_systemd_unit(self, letter: str) -> None:
        unit_name = "gpo-drive-%s.mount" % letter.lower()
        unit_path = self._systemd_unit_path(unit_name)
        if unit_path.exists():
            subprocess.run(
                ["systemctl", "--user", "disable", unit_name],
                check=False,
                capture_output=True,
            )
            unit_path.unlink(missing_ok=True)

    @staticmethod
    def _is_mounted(path: Path) -> bool:
        try:
            with open("/proc/mounts", encoding="utf-8") as mounts:
                target = str(path.resolve())
                for line in mounts:
                    parts = line.split()
                    if len(parts) >= 2 and parts[1] == target:
                        return True
        except OSError:
            pass
        return False


def which_mount_cifs() -> Optional[str]:
    return shutil.which("mount.cifs")
