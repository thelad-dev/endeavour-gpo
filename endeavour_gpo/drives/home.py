"""AD homeDirectory / homeDrive → DriveMap (Kerberos mount)."""

from __future__ import annotations

import logging
from typing import Any, Optional

from endeavour_gpo.drives.parser import ACTION_UPDATE, DriveMap

log = logging.getLogger(__name__)

AD_HOME_UID = "{AD-HomeDirectory}"
AD_HOME_GUID = "AD-HomeDrive"


def home_drive_from_attrs(
    home_directory: str,
    home_drive: str,
    *,
    sam: str = "",
) -> Optional[DriveMap]:
    """Build a DriveMap from AD attribute values (no Samba required).

    Label is the last UNC path component (e.g. ``\\\\dfs\\homes\\ladwein`` →
    ``ladwein``) so the mounter can form folders like ``H_ladwein``.
    """
    path = (home_directory or "").strip()
    letter = (home_drive or "").strip()
    if not path or not letter:
        return None

    label = _last_path_component(path)
    if not label and sam:
        label = sam.split("\\")[-1]

    name = letter if letter.endswith(":") else "%s:" % letter.rstrip(":")

    return DriveMap(
        uid=AD_HOME_UID,
        name=name,
        action=ACTION_UPDATE,
        path=path,
        label=label,
        letter=letter,
        persistent=True,
        use_letter=True,
        this_drive="NOCHANGE",
        all_drives="NOCHANGE",
        username=None,
        password_enc=None,
        bypass_errors=True,
        changed=None,
        run_once=False,
    )


def fetch_home_drive(username: str, lp: Any, creds: Any) -> Optional[DriveMap]:
    """Fetch AD homeDirectory/homeDrive via SamDB and return an Update DriveMap."""
    try:
        import ldb
        from samba.auth import system_session
        from samba.gp.gpclass import find_samaccount, get_dc_hostname
        from samba.samdb import SamDB
    except ImportError:
        log.warning("Samba Python bindings unavailable; skipping AD home drive")
        return None

    sam = (username or "").split("\\")[-1]
    if not sam:
        log.warning("Empty username; skipping AD home drive")
        return None

    try:
        dc_hostname = get_dc_hostname(creds, lp)
        url = "ldap://" + dc_hostname
        samdb = SamDB(
            url=url,
            session_info=system_session(),
            credentials=creds,
            lp=lp,
        )
        _uac, dn = find_samaccount(samdb, sam)
        res = samdb.search(
            dn,
            scope=ldb.SCOPE_BASE,
            expression="(objectClass=*)",
            attrs=["homeDirectory", "homeDrive"],
        )
        if len(res) != 1:
            log.warning("Unexpected SamDB result count for %s home attrs: %s", sam, len(res))
            return None

        msg = res[0]
        home_directory = _ldb_attr(msg, "homeDirectory")
        home_drive = _ldb_attr(msg, "homeDrive")
    except Exception as exc:
        log.warning("Could not fetch AD home drive for %s: %s", sam, exc)
        return None

    if not home_directory.strip() or not home_drive.strip():
        log.debug("User %s has no homeDirectory/homeDrive; skipping", sam)
        return None

    return home_drive_from_attrs(home_directory, home_drive, sam=sam)


def _ldb_attr(msg: Any, name: str) -> str:
    if name not in msg:
        return ""
    val = msg[name][0]
    if isinstance(val, bytes):
        return val.decode("utf-8", errors="replace")
    return str(val)


def _last_path_component(path: str) -> str:
    normalized = path.replace("\\", "/").rstrip("/")
    if not normalized:
        return ""
    return normalized.rsplit("/", 1)[-1]
