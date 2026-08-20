"""Samba gp_ext Client-Side Extension for EndeavourOS GPP SharedPrinters."""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Optional

from endeavour_gpo.drives.filters import FilterContext, evaluate_filters
from endeavour_gpo.printers.applier import CupsPrinterApplier, PrinterApplyError
from endeavour_gpo.printers.parser import SharedPrinterMap, parse_printers_element

log = logging.getLogger(__name__)

try:
    from samba.gp.gpclass import drop_privileges, expand_pref_variables, gp_misc_applier, gp_xml_ext
    from samba.gp.util.logging import log as samba_log
except ImportError as exc:  # pragma: no cover
    raise ImportError(
        "endeavour_gpo.cse requires Samba Python bindings (python-samba)."
    ) from exc

EXT_GUID = "{F3C8A901-2B4E-4D7A-9C15-8E6F0A1B2C3D}"
CSE_NAME = "Endeavour/Preferences/Printers"


def _fetch_security_token(username: str, lp: Any, creds: Any) -> Any:
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


class gp_printers_ext(gp_xml_ext, gp_misc_applier):
    """User-side CSE: Printers.xml SharedPrinter → CUPS smb queues."""

    def __str__(self) -> str:
        return CSE_NAME

    def parse_value(self, val: str) -> dict:
        vals = super().parse_value(val)
        if "printer" in vals:
            vals["printer"] = json.loads(vals["printer"])
        if "run_once" in vals:
            vals["run_once"] = json.loads(vals["run_once"])
        return vals

    def _applier(self) -> CupsPrinterApplier:
        return CupsPrinterApplier(self.username)

    def _filter_context(self) -> FilterContext:
        token = None
        try:
            token = _fetch_security_token(self.username, self.lp, self.creds)
        except Exception as exc:
            samba_log.warn("Could not fetch security token for ILT: %s" % exc)
        return FilterContext(username=self.username, security_token=token)

    def _expand_path(self, printer: SharedPrinterMap, gpo: Any) -> Optional[str]:
        if not printer.path:
            return None
        uri = "smb:" + printer.path.replace("\\", "/")
        gptpath = os.path.join(gpo.file_sys_path, "USER")
        try:
            expanded = expand_pref_variables(uri, gptpath, self.lp, username=self.username)
        except NameError as exc:
            samba_log.warn(
                "Failed to expand printer path variables: %s (%s)" % (exc, printer.path)
            )
            return None
        if expanded is None:
            return None
        return expanded.replace("smb:", "").replace("/", "\\")

    def unapply(self, guid: str, key: str, val: str) -> None:
        vals = self.parse_value(val)
        data = vals.get("printer", {})
        printer = SharedPrinterMap(
            uid=data.get("uid", ""),
            name=data.get("name", ""),
            action="D",
            path=data.get("path", ""),
            default=False,
            skip_local=False,
            delete_all=False,
            location=data.get("location", ""),
            comment=data.get("comment", ""),
            username=data.get("username"),
            cpassword=data.get("cpassword"),
            bypass_errors=True,
            persistent=data.get("persistent", False),
            changed=data.get("changed"),
            run_once=vals.get("run_once", False),
        )
        try:
            self._applier().delete(printer)
        except PrinterApplyError as exc:
            samba_log.warn("Unapply printer delete failed for %s: %s" % (key, exc))
        self.cache_remove_attribute(guid, key)

    def apply(self, guid: str, key: str, printer: SharedPrinterMap) -> None:
        old_val = self.cache_get_attribute_value(guid, key)
        val = self.generate_value(
            printer=json.dumps(
                {
                    "uid": printer.uid,
                    "name": printer.name,
                    "action": printer.action,
                    "path": printer.path,
                    "default": printer.default,
                    "skip_local": printer.skip_local,
                    "delete_all": printer.delete_all,
                    "location": printer.location,
                    "comment": printer.comment,
                    "username": printer.username,
                    "cpassword": printer.cpassword,
                    "bypass_errors": printer.bypass_errors,
                    "persistent": printer.persistent,
                    "changed": printer.changed,
                    "queue": printer.queue_name(),
                }
            ),
            run_once=json.dumps(printer.run_once),
        )

        if old_val:
            self.unapply(guid, key, old_val)

        applier = self._applier()
        try:
            applier.apply(printer)
        except PrinterApplyError as exc:
            if printer.bypass_errors:
                samba_log.warn("Printer bypassErrors: %s (%s)" % (key, exc))
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

            rel_path = "USER/Preferences/Printers/Printers.xml"
            full_path = os.path.join(gpo.file_sys_path, rel_path)
            xml_conf = drop_privileges("root", self.parse, full_path)
            if xml_conf is None:
                continue

            printers = parse_printers_element(xml_conf)
            kept: list[str] = []

            for printer in printers:
                if printer.filters and not evaluate_filters(printer.filters, ctx):
                    samba_log.debug("Printer %s filtered out by ILT" % printer.uid)
                    continue

                path = self._expand_path(printer, gpo)
                if path is None and printer.should_apply:
                    continue

                if path is not None:
                    printer = SharedPrinterMap(
                        uid=printer.uid,
                        name=printer.name,
                        action=printer.action,
                        path=path,
                        default=printer.default,
                        skip_local=printer.skip_local,
                        delete_all=printer.delete_all,
                        location=printer.location,
                        comment=printer.comment,
                        username=printer.username,
                        cpassword=printer.cpassword,
                        bypass_errors=printer.bypass_errors,
                        persistent=printer.persistent,
                        changed=printer.changed,
                        run_once=printer.run_once,
                        filters=printer.filters,
                    )

                key = printer.uid or printer.smb_uri() or printer.queue_name()
                kept.append(key)
                self.apply(gpo.name, key, printer)

            self.clean(gpo.name, keep=kept)

    def rsop(self, gpo) -> dict:
        output: dict[str, str] = {}
        if not gpo.file_sys_path:
            return output

        path = os.path.join(gpo.file_sys_path, "USER/Preferences/Printers/Printers.xml")
        xml_conf = self.parse(path)
        if xml_conf is None:
            return output

        ctx = self._filter_context()
        applier = CupsPrinterApplier(self.username)
        for printer in parse_printers_element(xml_conf):
            if printer.filters and not evaluate_filters(printer.filters, ctx):
                continue
            label = printer.name or printer.queue_name() or printer.uid
            output[label] = applier.rsop_line(printer)
        return output


if __name__ == "__main__":
    from samba.gp.gpclass import register_gp_extension

    register_gp_extension(
        EXT_GUID,
        "gp_printers_ext",
        os.path.realpath(__file__),
        machine=False,
        user=True,
    )
