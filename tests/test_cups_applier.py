from __future__ import annotations

from endeavour_gpo.printers.applier import CupsPrinterApplier, PrinterApplyError
from endeavour_gpo.printers.parser import SharedPrinterMap


def _printer(**overrides) -> SharedPrinterMap:
    base = dict(
        uid="{test}",
        name="Technik",
        action="U",
        path=r"\\SOPHOS\Technik",
        default=False,
        skip_local=False,
        delete_all=False,
        location="EG",
        comment="Technikdrucker",
        username=None,
        cpassword=None,
        bypass_errors=False,
        persistent=False,
    )
    base.update(overrides)
    return SharedPrinterMap(**base)


def _applier() -> CupsPrinterApplier:
    return CupsPrinterApplier("EXAMPLE\\testuser", uid=1000)


class _Result:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def test_apply_create_uses_everywhere(monkeypatch):
    applier = _applier()
    calls: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        if cmd[:2] == ["lpstat", "-p"]:
            return _Result(1, stderr="Unknown destination")
        return _Result(0)

    monkeypatch.setattr("endeavour_gpo.printers.applier.subprocess.run", fake_run)
    queue = applier.apply(_printer())
    assert queue == "endeavour-sophos-technik"
    lpadmin = next(c for c in calls if c[:1] == ["lpadmin"] and "-x" not in c)
    assert lpadmin[lpadmin.index("-v") + 1] == "smb://SOPHOS/Technik"
    assert "auth-info-required=negotiate" in lpadmin
    assert lpadmin[lpadmin.index("-m") + 1] == "everywhere"


def test_everywhere_fallback_to_raw(monkeypatch):
    applier = _applier()
    models: list[str] = []

    def fake_run(cmd, **kwargs):
        if cmd[:2] == ["lpstat", "-p"]:
            return _Result(1)
        if cmd[:1] == ["lpadmin"] and "-m" in cmd:
            model = cmd[cmd.index("-m") + 1]
            models.append(model)
            if model == "everywhere":
                return _Result(1, stderr="No everywhere")
            return _Result(0)
        return _Result(0)

    monkeypatch.setattr("endeavour_gpo.printers.applier.subprocess.run", fake_run)
    applier.apply(_printer())
    assert models == ["everywhere", "raw"]


def test_default_set_via_lpoptions(monkeypatch):
    applier = _applier()
    calls: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        if cmd[:2] == ["lpstat", "-p"]:
            return _Result(0)
        return _Result(0)

    monkeypatch.setattr("endeavour_gpo.printers.applier.subprocess.run", fake_run)
    applier.apply(_printer(default=True))
    assert ["lpoptions", "-d", "endeavour-sophos-technik"] in calls


def test_skip_local_blocks_default(monkeypatch):
    applier = _applier()
    calls: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        if cmd[:2] == ["lpstat", "-p"]:
            return _Result(0)
        if cmd[:2] == ["lpstat", "-v"]:
            return _Result(0, stdout="device for PDF: file:///tmp/out.pdf\n")
        return _Result(0)

    monkeypatch.setattr("endeavour_gpo.printers.applier.subprocess.run", fake_run)
    applier.apply(_printer(default=True, skip_local=True))
    assert not any(c[:1] == ["lpoptions"] for c in calls)


def test_delete_queue(monkeypatch):
    applier = _applier()
    calls: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        if cmd[:2] == ["lpstat", "-p"]:
            return _Result(0)
        return _Result(0)

    monkeypatch.setattr("endeavour_gpo.printers.applier.subprocess.run", fake_run)
    applier.apply(_printer(action="D"))
    assert ["lpadmin", "-x", "endeavour-sophos-technik"] in calls


def test_apply_failure_raises(monkeypatch):
    applier = _applier()

    def fake_run(cmd, **kwargs):
        if cmd[:2] == ["lpstat", "-p"]:
            return _Result(1)
        if cmd[:1] == ["lpadmin"]:
            return _Result(1, stderr="cups denied")
        return _Result(0)

    monkeypatch.setattr("endeavour_gpo.printers.applier.subprocess.run", fake_run)
    monkeypatch.setattr("endeavour_gpo.printers.applier.notify_user", lambda *a, **k: None)
    try:
        applier.apply(_printer())
        raised = False
    except PrinterApplyError:
        raised = True
    assert raised
