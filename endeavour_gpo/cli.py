"""Command-line helpers."""

from __future__ import annotations

import os
import sys

from endeavour_gpo.cse.gp_drive_maps_ext import EXT_GUID, gp_drive_maps_ext


def register_cse() -> int:
    try:
        from samba.gp.gpclass import register_gp_extension
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
    print("Registered CSE %s -> %s" % (EXT_GUID, ext_path))
    print("Run: sudo samba-gpupdate --target=user --force")
    return 0


if __name__ == "__main__":
    raise SystemExit(register_cse())
