"""Command-line helpers."""

from __future__ import annotations

import os
import sys
from configparser import ConfigParser

from endeavour_gpo.cse.gp_drive_maps_ext import EXT_GUID, gp_drive_maps_ext


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

    ext_path = os.path.realpath(
        os.path.join(os.path.dirname(__file__), "cse", "gp_drive_maps_ext.py")
    )
    register_gp_extension(
        EXT_GUID,
        gp_drive_maps_ext.__name__,
        ext_path,
        machine=False,
        user=True,
    )

    lp, parser = parse_gpext_conf(None)
    _move_section_to_end(parser, EXT_GUID)
    atomic_write_conf(lp, parser)

    print("Registered CSE %s -> %s" % (EXT_GUID, ext_path))
    print(
        "Coexistence: Samba built-in gp_drive_maps_user_ext (gio) may stay enabled; "
        "this CSE runs last in gpext.conf and takes priority via mount.cifs under ~/netzlaufwerke/."
    )
    print(
        "Run: sudo env KRB5CCNAME=/tmp/krb5cc_$(id -u) "
        "samba-gpupdate --target=User -U \"$USER\" --use-kerberos=required --force"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(register_cse())
