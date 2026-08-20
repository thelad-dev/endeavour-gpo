from __future__ import annotations

from endeavour_gpo.gpupdate import main


def test_main_help():
    try:
        main(["--help"])
    except SystemExit as exc:
        assert exc.code == 0
