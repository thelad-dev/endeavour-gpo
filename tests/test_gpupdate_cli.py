from __future__ import annotations

import os

from endeavour_gpo.gpupdate import _invoking_user, main


def test_main_help():
    try:
        main(["--help"])
    except SystemExit as exc:
        assert exc.code == 0


def test_invoking_user_respects_sudo_user(monkeypatch):
    monkeypatch.setenv("SUDO_USER", "ladwein")
    monkeypatch.setattr(os, "getuid", lambda: 0)

    class FakePw:
        pw_name = "ladwein"
        pw_uid = 22622

    import pwd

    def fake_getpwnam(name: str):
        if name == "ladwein":
            return FakePw()
        raise KeyError(name)

    monkeypatch.setattr(pwd, "getpwnam", fake_getpwnam)
    name, uid = _invoking_user()
    assert name == "ladwein"
    assert uid == 22622
