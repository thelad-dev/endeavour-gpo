from __future__ import annotations

from pathlib import Path

import pytest

from endeavour_gpo import notify
from endeavour_gpo.drives.mounter import CifsMounter, MountError, drive_gio_uri
from endeavour_gpo.drives.parser import DriveMap


def test_default_mount_root_uses_netzlaufwerke(tmp_path: Path) -> None:
    mounter = CifsMounter(
        "EXAMPLE\\testuser",
        uid=1000,
        gid=1000,
        home=tmp_path / "home",
    )
    assert mounter.runtime_root == tmp_path / "home" / "netzlaufwerke"


def test_drive_gio_uri() -> None:
    drive = DriveMap(
        uid="{x}",
        name="S:",
        action="U",
        path=r"\\fileserver\share",
        label="",
        letter="S",
        persistent=False,
        use_letter=True,
        this_drive="NOCHANGE",
        all_drives="NOCHANGE",
        username=None,
        password_enc=None,
        bypass_errors=False,
        changed=None,
    )
    assert drive_gio_uri(drive) == "smb://fileserver/share"


def test_notify_user_skips_without_session(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_which(name: str) -> str | None:
        return "/usr/bin/notify-send" if name == "notify-send" else None

    monkeypatch.setattr(notify.shutil, "which", fake_which)
    calls: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)

        class Result:
            returncode = 0
            stderr = ""
            stdout = ""

        return Result()

    monkeypatch.setattr(notify.subprocess, "run", fake_run)
    notify.notify_user(99999, "nobody", "title", "body")
    assert calls == []


def test_notify_user_invokes_notify_send(monkeypatch: pytest.MonkeyPatch) -> None:
    class _RuntimeDir:
        def __init__(self, path: str) -> None:
            self.path = Path(path)

        def is_dir(self) -> bool:
            return True

        def __truediv__(self, other: str) -> Path:
            return self.path / other

    def fake_path(value: str) -> _RuntimeDir | Path:
        if value == "/run/user/1000":
            return _RuntimeDir(value)
        return Path(value)

    def fake_which(name: str) -> str | None:
        if name == "notify-send":
            return "/usr/bin/notify-send"
        if name == "runuser":
            return "/usr/bin/runuser"
        return None

    monkeypatch.setattr(notify, "Path", fake_path)
    monkeypatch.setattr(notify.shutil, "which", fake_which)

    captured: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        captured.append(cmd)

        class Result:
            returncode = 0
            stderr = ""
            stdout = ""

        return Result()

    monkeypatch.setattr(notify.subprocess, "run", fake_run)
    notify.notify_user(1000, "ladwein", "Netzlaufwerk", "Fehler")

    assert len(captured) == 1
    assert captured[0][0] == "runuser"
    assert "/usr/bin/notify-send" in captured[0]
    assert "Netzlaufwerk" in captured[0]


def test_mount_failure_sends_notification(tmp_path: Path) -> None:
    mounter = CifsMounter(
        "EXAMPLE\\testuser",
        runtime_root=tmp_path / "drives",
        uid=1000,
        gid=1000,
        home=tmp_path / "home",
    )
    drive = DriveMap(
        uid="{x}",
        name="S:",
        action="U",
        path=r"\\server\share",
        label="Share",
        letter="S",
        persistent=False,
        use_letter=True,
        this_drive="NOCHANGE",
        all_drives="NOCHANGE",
        username=None,
        password_enc=None,
        bypass_errors=False,
        changed=None,
    )
    notified: list[str] = []
    mounter.notify_mount_failure = lambda d, err: notified.append(err)  # type: ignore[method-assign]

    with pytest.MonkeyPatch.context() as mp:
        import endeavour_gpo.drives.mounter as mounter_mod

        def fail_run(cmd, **kwargs):
            class Result:
                returncode = 1
                stderr = "permission denied"
                stdout = ""

            return Result()

        mp.setattr(mounter_mod.subprocess, "run", fail_run)
        mp.setattr(mounter, "_is_mounted", lambda path: False)
        mp.setattr(mounter, "_release_conflicting_gio_mount", lambda drive: None)
        with pytest.raises(MountError, match="permission denied"):
            mounter.mount(drive)

    assert notified == ["permission denied"]
