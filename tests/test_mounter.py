from __future__ import annotations

from pathlib import Path

import pytest

from endeavour_gpo.credentials import encrypt_cpassword
from endeavour_gpo.drives.mounter import CifsMounter, MountError
from endeavour_gpo.drives.parser import DriveMap


def _drive(**overrides) -> DriveMap:
    base = dict(
        uid="{test}",
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
    base.update(overrides)
    return DriveMap(**base)


def _mounter(tmp_path: Path) -> CifsMounter:
    return CifsMounter(
        "EXAMPLE\\testuser",
        runtime_root=tmp_path / "drives",
        uid=1000,
        gid=1000,
        home=tmp_path / "home",
    )


def test_build_spec_krb5(tmp_path):
    mounter = _mounter(tmp_path)
    spec = mounter.build_spec(_drive())
    assert spec.source == "//server/share"
    assert spec.target == tmp_path / "drives" / "S_Share"
    assert "sec=krb5" in spec.options
    assert spec.systemd_unit_name is None


def test_build_spec_persistent_unit(tmp_path):
    mounter = _mounter(tmp_path)
    spec = mounter.build_spec(_drive(persistent=True))
    assert spec.systemd_unit_name == "gpo-drive-s_share.mount"
    assert "_netdev" in spec.options


def test_credentials_file_is_reused_and_removed_on_unmount(tmp_path):
    mounter = _mounter(tmp_path)
    drive = _drive(username="EXAMPLE\\svc", password_enc=encrypt_cpassword("secret"))
    cred_dir = tmp_path / "home" / ".cache" / "endeavour-gpo" / "credentials"

    first = mounter.build_spec(drive).credentials_file
    second = mounter.build_spec(drive).credentials_file

    assert first == second
    assert list(cred_dir.iterdir()) == [first]
    assert "password=secret" in first.read_text(encoding="utf-8")
    assert first.stat().st_mode & 0o777 == 0o600

    mounter.unmount(drive)
    assert not first.exists()


def test_build_spec_without_writing_credentials(tmp_path):
    mounter = _mounter(tmp_path)
    drive = _drive(username="EXAMPLE\\svc", password_enc=encrypt_cpassword("secret"))

    spec = mounter.build_spec(drive, write_credentials=False)

    assert "credentials=%s" % spec.credentials_file in spec.options
    assert not spec.credentials_file.exists()


def test_mount_calls_mount_cifs(tmp_path):
    mounter = _mounter(tmp_path)

    with pytest.MonkeyPatch.context() as mp:
        import endeavour_gpo.drives.mounter as mounter_mod

        def fake_run(cmd, **kwargs):
            class Result:
                returncode = 0
                stderr = ""
                stdout = ""

            return Result()

        mp.setattr(mounter_mod.subprocess, "run", fake_run)
        mp.setattr(mounter, "_is_mounted", lambda path: False)
        spec = mounter.mount(_drive())

    assert spec.target.exists()


def test_persistent_mount_does_not_install_user_unit(tmp_path):
    mounter = _mounter(tmp_path)
    drive = _drive(persistent=True)
    unit_dir = tmp_path / "home" / ".config" / "systemd" / "user"
    leftover = unit_dir / "gpo-drive-s_share.mount"
    leftover.parent.mkdir(parents=True, exist_ok=True)
    leftover.write_text("stale\n", encoding="utf-8")

    with pytest.MonkeyPatch.context() as mp:
        import endeavour_gpo.drives.mounter as mounter_mod

        def fake_run(cmd, **kwargs):
            class Result:
                returncode = 0
                stderr = ""
                stdout = ""

            return Result()

        mp.setattr(mounter_mod.subprocess, "run", fake_run)
        mp.setattr(mounter, "_is_mounted", lambda path: False)
        spec = mounter.mount(drive)

    assert spec.systemd_unit_name == "gpo-drive-s_share.mount"
    assert not leftover.exists()
    assert not unit_dir.exists() or list(unit_dir.iterdir()) == []


def test_mount_failure(tmp_path):
    mounter = _mounter(tmp_path)

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
        with pytest.raises(MountError, match="permission denied"):
            mounter.mount(_drive())
