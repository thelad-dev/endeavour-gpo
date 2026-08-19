"""The CSE must survive drive-map errors: samba.gp's log takes (message, data) only."""

from __future__ import annotations

import importlib
import json
import sys
import types
from pathlib import Path

import pytest

from endeavour_gpo.drives.mounter import MountError
from endeavour_gpo.drives.parser import DriveMap

WARNINGS: list[str] = []


class _FakeSambaLog:
    """Mirrors samba.gp.util.logging.log: a message plus one optional data argument."""

    @staticmethod
    def warning(message, data=None):
        WARNINGS.append(str(message))

    @staticmethod
    def warn(message, data=None):
        _FakeSambaLog.warning(message, data)

    @staticmethod
    def debug(message, data=None):
        pass


class _FakeXmlExt:
    """Minimal stand-in for samba.gp.gpclass.gp_xml_ext."""

    def parse(self, path):  # pragma: no cover - unused by these tests
        return None


class _FakeMiscApplier:
    """Minimal stand-in for samba.gp.gpclass.gp_misc_applier."""

    def __init__(self):
        self.cache: dict[tuple[str, str], str] = {}

    def generate_value(self, **kwargs) -> str:
        return json.dumps(kwargs)

    def parse_value(self, val: str) -> dict:
        return json.loads(val)

    def cache_get_attribute_value(self, guid, key):
        return self.cache.get((guid, key))

    def cache_add_attribute(self, guid, key, val):
        self.cache[(guid, key)] = val

    def cache_remove_attribute(self, guid, key):
        self.cache.pop((guid, key), None)


def _expand_pref_variables(uri, gptpath, lp, username=None):
    raise NameError("unknown variable %LogonServer%")


@pytest.fixture
def cse(monkeypatch):
    WARNINGS.clear()
    samba = types.ModuleType("samba")
    gp = types.ModuleType("samba.gp")
    util = types.ModuleType("samba.gp.util")
    util_logging = types.ModuleType("samba.gp.util.logging")
    gpclass = types.ModuleType("samba.gp.gpclass")

    util_logging.log = _FakeSambaLog
    gpclass.drop_privileges = lambda user, func, *args: func(*args)
    gpclass.expand_pref_variables = _expand_pref_variables
    gpclass.gp_misc_applier = _FakeMiscApplier
    gpclass.gp_xml_ext = _FakeXmlExt
    samba.gp = gp
    gp.util = util
    gp.gpclass = gpclass
    util.logging = util_logging

    for name, module in [
        ("samba", samba),
        ("samba.gp", gp),
        ("samba.gp.util", util),
        ("samba.gp.util.logging", util_logging),
        ("samba.gp.gpclass", gpclass),
    ]:
        monkeypatch.setitem(sys.modules, name, module)
    monkeypatch.delitem(sys.modules, "endeavour_gpo.cse.gp_drive_maps_ext", raising=False)

    module = importlib.import_module("endeavour_gpo.cse.gp_drive_maps_ext")
    yield module
    sys.modules.pop("endeavour_gpo.cse.gp_drive_maps_ext", None)


class _FailingMounter:
    def mount(self, drive):
        raise MountError("mount error(112): Host is down")

    def unmount(self, drive):
        raise MountError("umount: target is busy")


def _drive(**overrides) -> DriveMap:
    base = dict(
        uid="{drive-1}",
        name="S:",
        action="U",
        path=r"\\down.example.com\shared",
        label="Shared",
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


def _ext(cse):
    ext = cse.gp_drive_maps_ext()
    ext.username = "EXAMPLE\\testuser"
    ext.lp = object()
    ext._mounter = lambda: _FailingMounter()
    return ext


def test_bypass_errors_warns_and_continues(cse):
    ext = _ext(cse)

    ext.apply("{GPO}", "{drive-1}", _drive(bypass_errors=True))

    assert ext.cache_get_attribute_value("{GPO}", "{drive-1}") is not None
    assert any("bypassErrors" in msg and "Host is down" in msg for msg in WARNINGS)


def test_without_bypass_errors_mount_failure_still_raises(cse):
    ext = _ext(cse)

    with pytest.raises(MountError):
        ext.apply("{GPO}", "{drive-1}", _drive(bypass_errors=False))


def test_unapply_unmount_failure_warns(cse):
    ext = _ext(cse)
    drive = json.dumps({"uid": "{drive-1}", "letter": "S"})
    val = ext.generate_value(drive=drive, run_once="false")

    ext.unapply("{GPO}", "{drive-1}", val)

    assert any("Unapply unmount failed" in msg and "target is busy" in msg for msg in WARNINGS)


def test_expand_uri_name_error_warns(cse):
    ext = _ext(cse)
    gpo = types.SimpleNamespace(file_sys_path=str(Path("/sysvol/example/Policies/{GPO}")))

    assert ext._expand_uri(_drive(), gpo) is None
    assert any("Failed to expand drive map variables" in msg for msg in WARNINGS)
