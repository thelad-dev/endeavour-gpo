"""Samba gp_ext Client-Side Extension for EndeavourOS drive maps."""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Optional

from endeavour_gpo.drives.filters import FilterContext, evaluate_filters
from endeavour_gpo.drives.mounter import CifsMounter, MountError
from endeavour_gpo.drives.parser import DriveMap, parse_drives_element

log = logging.getLogger(__name__)

try:
    from samba.gp.gpclass import drop_privileges, expand_pref_variables, gp_misc_applier, gp_xml_ext
    from samba.gp.util.logging import log as samba_log
except ImportError as exc:  # pragma: no cover - exercised only on domain clients
    raise ImportError(
        "endeavour_gpo.cse requires Samba Python bindings (python-samba)."
    ) from exc

# Unique extension GUID — do not reuse Samba built-in CSE IDs.
EXT_GUID = "{E7A4B2C1-9F3D-4E8A-B6C5-1D2E3F4A5B6C}"
CSE_NAME = "Endeavour/Preferences/Drives"


def _fetch_security_token(username: str, lp: Any, creds: Any) -> Any:
    """Build the user's security token for ILT group checks."""
    from samba.auth import (
        AUTH_SESSION_INFO_AUTHENTICATED,
        AUTH_SESSION_INFO_DEFAULT_GROUPS,
        AUTH_SESSION_INFO_SIMPLE_PRIVILEGES,
        system_session,
        user_session,
    )
    from samba.dsdb import UF_SERVER_TRUST_ACCOUNT, UF_WORKSTATION_TRUST_ACCOUNT
    from samba.gp.gpclass import find_samaccount, get_dc_hostname, merge_with_system_token
    from samba.samdb import SamDB

    dc_hostname = get_dc_hostname(creds, lp)
    url = "ldap://" + dc_hostname
    samdb = SamDB(url=url, session_info=system_session(), credentials=creds, lp=lp)
    uac, dn = find_samaccount(samdb, username.split("\\")[-1])
    flags = AUTH_SESSION_INFO_DEFAULT_GROUPS | AUTH_SESSION_INFO_AUTHENTICATED
    flags |= AUTH_SESSION_INFO_SIMPLE_PRIVILEGES
    session = user_session(samdb, lp_ctx=lp, dn=dn, session_info_flags=flags)
    if uac & UF_WORKSTATION_TRUST_ACCOUNT or uac & UF_SERVER_TRUST_ACCOUNT:
        return merge_with_system_token(session.security_token)
    return session.security_token


class gp_drive_maps_ext(gp_xml_ext, gp_misc_applier):
    """User-side CSE: Drives.xml → mount.cifs with item-level targeting."""

    def __str__(self) -> str:
        return CSE_NAME

    def parse_value(self, val: str) -> dict:
        vals = super().parse_value(val)
        if "drive" in vals:
            vals["drive"] = json.loads(vals["drive"])
        if "run_once" in vals:
            vals["run_once"] = json.loads(vals["run_once"])
        return vals

    def _mounter(self) -> CifsMounter:
        return CifsMounter(self.username)

    def _filter_context(self) -> FilterContext:
        token = None
        try:
            token = _fetch_security_token(self.username, self.lp, self.creds)
        except Exception as exc:
            samba_log.warn("Could not fetch security token for ILT: %s", exc)
        return FilterContext(username=self.username, security_token=token)

    def _expand_uri(self, drive: DriveMap, gpo: Any) -> Optional[str]:
        if not drive.path:
            return None
        uri = "smb:" + drive.path.replace("\\", "/")
        gptpath = os.path.join(gpo.file_sys_path, "USER")
        try:
            return expand_pref_variables(uri, gptpath, self.lp, username=self.username)
        except NameError as exc:
            samba_log.warn("Failed to expand drive map variables: %s (%s)", exc, drive.path)
            return None

    def unapply(self, guid: str, key: str, val: str) -> None:
        vals = self.parse_value(val)
        drive_data = vals.get("drive", {})
        drive = DriveMap(
            uid=drive_data.get("uid", ""),
            name=drive_data.get("name", ""),
            action=drive_data.get("action", "U"),
            path=drive_data.get("path", ""),
            label=drive_data.get("label", ""),
            letter=drive_data.get("letter", ""),
            persistent=drive_data.get("persistent", False),
            use_letter=drive_data.get("use_letter", True),
            this_drive=drive_data.get("this_drive", "NOCHANGE"),
            all_drives=drive_data.get("all_drives", "NOCHANGE"),
            username=drive_data.get("username"),
            password_enc=drive_data.get("password_enc"),
            bypass_errors=drive_data.get("bypass_errors", False),
            changed=drive_data.get("changed"),
            run_once=vals.get("run_once", False),
        )
        if drive.should_mount or drive.should_unmount:
            try:
                self._mounter().unmount(drive)
            except MountError as exc:
                samba_log.warn("Unapply unmount failed for %s: %s", key, exc)
        self.cache_remove_attribute(guid, key)

    def apply(self, guid: str, key: str, drive: DriveMap) -> None:
        old_val = self.cache_get_attribute_value(guid, key)
        val = self.generate_value(
            drive=json.dumps(
                {
                    "uid": drive.uid,
                    "name": drive.name,
                    "action": drive.action,
                    "path": drive.path,
                    "label": drive.label,
                    "letter": drive.letter,
                    "persistent": drive.persistent,
                    "use_letter": drive.use_letter,
                    "this_drive": drive.this_drive,
                    "all_drives": drive.all_drives,
                    "username": drive.username,
                    "password_enc": drive.password_enc,
                    "bypass_errors": drive.bypass_errors,
                    "changed": drive.changed,
                }
            ),
            run_once=json.dumps(drive.run_once),
        )

        if old_val:
            self.unapply(guid, key, old_val)

        mounter = self._mounter()
        try:
            if drive.should_mount:
                mounter.mount(drive)
            elif drive.should_unmount:
                mounter.unmount(drive)
        except MountError as exc:
            if drive.bypass_errors:
                samba_log.warn("Drive map bypassErrors: %s (%s)", key, exc)
            else:
                raise

        self.cache_add_attribute(guid, key, val)

    def process_group_policy(self, deleted_gpo_list, changed_gpo_list) -> None:
        for guid, settings in deleted_gpo_list:
            if str(self) in settings:
                for key, val in settings[str(self)].items():
                    self.unapply(guid, key, val)

        ctx = self._filter_context()
        for gpo in changed_gpo_list:
            if not gpo.file_sys_path:
                continue

            rel_path = "USER/Preferences/Drives/Drives.xml"
            full_path = os.path.join(gpo.file_sys_path, rel_path)
            xml_conf = drop_privileges("root", self.parse, full_path)
            if xml_conf is None:
                continue

            drives = parse_drives_element(xml_conf)
            kept: list[str] = []

            for drive in drives:
                if drive.is_hidden:
                    samba_log.debug("Skipping hidden drive %s", drive.uid)
                    continue

                if drive.filters and not evaluate_filters(drive.filters, ctx):
                    samba_log.debug("Drive %s filtered out by ILT", drive.uid)
                    continue

                uri = self._expand_uri(drive, gpo)
                if uri is None and drive.should_mount:
                    continue

                if uri:
                    drive = DriveMap(
                        uid=drive.uid,
                        name=drive.name,
                        action=drive.action,
                        path=uri.replace("smb:", "").replace("/", "\\"),
                        label=drive.label,
                        letter=drive.letter,
                        persistent=drive.persistent,
                        use_letter=drive.use_letter,
                        this_drive=drive.this_drive,
                        all_drives=drive.all_drives,
                        username=drive.username,
                        password_enc=drive.password_enc,
                        bypass_errors=drive.bypass_errors,
                        changed=drive.changed,
                        run_once=drive.run_once,
                        filters=drive.filters,
                    )

                key = drive.uid or drive.cifs_source()
                kept.append(key)
                self.apply(gpo.name, key, drive)

            self.clean(gpo.name, keep=kept)

    def rsop(self, gpo) -> dict:
        output: dict[str, str] = {}
        if not gpo.file_sys_path:
            return output

        path = os.path.join(gpo.file_sys_path, "USER/Preferences/Drives/Drives.xml")
        xml_conf = self.parse(path)
        if xml_conf is None:
            return output

        ctx = self._filter_context()
        for drive in parse_drives_element(xml_conf):
            if drive.is_hidden:
                continue
            if drive.filters and not evaluate_filters(drive.filters, ctx):
                continue
            label = drive.label or drive.mount_letter or drive.uid
            if drive.should_mount:
                spec = CifsMounter(self.username).build_spec(drive)
                output[label] = "mount.cifs %s %s -o %s" % (
                    spec.source,
                    spec.target,
                    ",".join(spec.options),
                )
            elif drive.should_unmount:
                output[label] = "umount %s" % (
                    CifsMounter(self.username).runtime_root / drive.mount_letter
                )
        return output


if __name__ == "__main__":
    from samba.gp.gpclass import register_gp_extension

    register_gp_extension(
        EXT_GUID,
        "gp_drive_maps_ext",
        os.path.realpath(__file__),
        machine=False,
        user=True,
    )
