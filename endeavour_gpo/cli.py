"""Command-line helpers: register CSEs and install refresh hooks."""

from __future__ import annotations

import os
import sys
from configparser import ConfigParser

from endeavour_gpo.cse.gp_drive_maps_ext import EXT_GUID as DRIVE_GUID
from endeavour_gpo.cse.gp_drive_maps_ext import gp_drive_maps_ext
from endeavour_gpo.cse.gp_printers_ext import EXT_GUID as PRINTER_GUID
from endeavour_gpo.cse.gp_printers_ext import gp_printers_ext
from endeavour_gpo.install_hooks import ensure_samba_apply_gpo, install_systemd_units


def _move_section_to_end(parser: ConfigParser, section: str) -> None:
    if section not in parser:
        return
    values = dict(parser.items(section))
    parser.remove_section(section)
    parser.add_section(section)
    for key, value in values.items():
        parser.set(section, key, value)


def register_cse() -> int:
    try:
        from samba.gp.gpclass import atomic_write_conf, parse_gpext_conf, register_gp_extension
    except ImportError:
        print("Samba Python bindings not found. Install python-samba.", file=sys.stderr)
        return 1

    if os.geteuid() != 0:
        print("endeavour-gpo-register requires root (sudo).", file=sys.stderr)
        return 1

    drive_path = os.path.realpath(
        os.path.join(os.path.dirname(__file__), "cse", "gp_drive_maps_ext.py")
    )
    printer_path = os.path.realpath(
        os.path.join(os.path.dirname(__file__), "cse", "gp_printers_ext.py")
    )

    register_gp_extension(
        DRIVE_GUID,
        gp_drive_maps_ext.__name__,
        drive_path,
        machine=False,
        user=True,
    )
    register_gp_extension(
        PRINTER_GUID,
        gp_printers_ext.__name__,
        printer_path,
        machine=False,
        user=True,
    )

    lp, parser = parse_gpext_conf(None)
    _move_section_to_end(parser, DRIVE_GUID)
    _move_section_to_end(parser, PRINTER_GUID)
    atomic_write_conf(lp, parser)

    print("Registered CSE %s -> %s" % (DRIVE_GUID, drive_path))
    print("Registered CSE %s -> %s" % (PRINTER_GUID, printer_path))

    ensure_samba_apply_gpo()
    install_systemd_units()

    print(
        "Coexistence: Samba built-in drive CSE may stay enabled; "
        "Endeavour CSEs run last in gpext.conf."
    )
    print("Local refresh:  sudo endeavour-gpupdate --force")
    print("All sessions:   sudo endeavour-gpupdate --force --all-sessions")
    print("Remote (SSH):   endeavour-gpupdate-remote <host>   # from admin PC")
    print("Remote socket:  localhost:46327 (starts gpupdate for active sessions)")
    return 0


if __name__ == "__main__":
    raise SystemExit(register_cse())
