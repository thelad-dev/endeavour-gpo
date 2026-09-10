from __future__ import annotations

import os

from endeavour_gpo.gpupdate import _invoking_user, _is_local_user, main


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


def test_is_local_user_passwd_and_system_uid(monkeypatch):
    data = "ladwein_local:x:1000:1000::/home/ladwein_local:/bin/bash\n"

    class FakeFile:
        def __init__(self, text: str):
            self._lines = text.splitlines(True)

        def __iter__(self):
            return iter(self._lines)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    def fake_open(path, *args, **kwargs):
        if str(path) == "/etc/passwd":
            return FakeFile(data)
        raise AssertionError(path)

    monkeypatch.setattr("builtins.open", fake_open)
    assert _is_local_user("root", 0) is True
    assert _is_local_user("ladwein_local", 1000) is True
    assert _is_local_user("ladwein", 22622) is False
