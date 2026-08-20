"""Parse GPO Preferences Printers.xml into SharedPrinter items."""

from __future__ import annotations

import logging
import re
import unicodedata
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
from urllib.parse import quote

from endeavour_gpo.drives.filters import GppFilter, parse_filters_element

log = logging.getLogger(__name__)

ACTION_CREATE = "C"
ACTION_UPDATE = "U"
ACTION_REPLACE = "R"
ACTION_DELETE = "D"

ACTION_LABELS = {
    ACTION_CREATE: "Create",
    ACTION_UPDATE: "Update",
    ACTION_REPLACE: "Replace",
    ACTION_DELETE: "Delete",
}

_UNSUPPORTED_TAGS = frozenset({"PortPrinter", "LocalPrinter"})
_QUEUE_UNSAFE = re.compile(r"[^a-z0-9]+")


@dataclass
class SharedPrinterMap:
    uid: str
    name: str
    action: str
    path: str
    default: bool
    skip_local: bool
    delete_all: bool
    location: str
    comment: str
    username: Optional[str]
    cpassword: Optional[str]
    bypass_errors: bool
    persistent: bool
    changed: Optional[str] = None
    run_once: bool = False
    filters: list[GppFilter] = field(default_factory=list)

    @property
    def action_label(self) -> str:
        return ACTION_LABELS.get(self.action, self.action)

    @property
    def should_apply(self) -> bool:
        return self.action in (ACTION_CREATE, ACTION_UPDATE, ACTION_REPLACE)

    @property
    def should_delete(self) -> bool:
        return self.action == ACTION_DELETE

    def smb_uri(self) -> str:
        """UNC → CUPS smb:// URI (path segments percent-encoded for Umlaute)."""
        path = (self.path or "").strip()
        if not path:
            return ""
        normalized = path.replace("\\", "/").lstrip("/")
        if not normalized:
            return ""
        parts = [p for p in normalized.split("/") if p]
        encoded = "/".join(quote(p, safe="") for p in parts)
        return "smb://" + encoded

    def queue_name(self) -> str:
        unc = (self.path or "").replace("\\", "/").strip("/")
        if not unc:
            raw = self.name or self.uid or "printer"
            return "endeavour-" + _sanitize_queue_part(raw)
        parts = [p for p in unc.split("/") if p]
        if len(parts) >= 2:
            body = "-".join(_sanitize_queue_part(p) for p in parts[:2])
        else:
            body = _sanitize_queue_part(parts[0] if parts else "printer")
        return "endeavour-" + body


def _sanitize_queue_part(value: str) -> str:
    folded = unicodedata.normalize("NFKD", value)
    ascii_only = folded.encode("ascii", "ignore").decode("ascii")
    cleaned = _QUEUE_UNSAFE.sub("-", ascii_only.lower()).strip("-")
    return cleaned or "printer"


def parse_printers_xml(path: str | Path) -> list[SharedPrinterMap]:
    tree = ET.parse(path)
    return parse_printers_element(tree.getroot())


def parse_printers_element(root: ET.Element) -> list[SharedPrinterMap]:
    if root.tag != "Printers":
        raise ValueError(f"Expected <Printers> root element, got <{root.tag}>")
    if root.get("disabled") == "1":
        return []

    results: list[SharedPrinterMap] = []
    for child in root:
        if child.tag in _UNSUPPORTED_TAGS:
            log.warning("Skipping unsupported printer preference <%s>", child.tag)
            continue
        if child.tag != "SharedPrinter":
            log.warning("Skipping unknown Printers child <%s>", child.tag)
            continue
        printer = _parse_shared_printer(child)
        if printer is not None:
            results.append(printer)
    return results


def _parse_shared_printer(el: ET.Element) -> Optional[SharedPrinterMap]:
    if el.get("disabled") == "1":
        return None
    props = el.find("Properties")
    if props is None or props.get("disabled") == "1":
        return None

    filters_el = el.find("Filters")
    filters = parse_filters_element(filters_el) if filters_el is not None else []
    run_once = filters_el is not None and filters_el.find("FilterRunOnce") is not None

    username = props.get("userName") or props.get("username") or None
    if username == "":
        username = None
    cpassword = props.get("cpassword") or None
    if cpassword == "":
        cpassword = None

    return SharedPrinterMap(
        uid=el.get("uid", ""),
        name=el.get("name", ""),
        action=props.get("action", ACTION_UPDATE),
        path=props.get("path", ""),
        default=props.get("default", "0") == "1",
        skip_local=props.get("skipLocal", "0") == "1",
        delete_all=props.get("deleteAll", "0") == "1",
        location=props.get("location", "") or "",
        comment=props.get("comment", "") or "",
        username=username,
        cpassword=cpassword,
        bypass_errors=el.get("bypassErrors", "0") == "1",
        persistent=props.get("persistent", "0") == "1",
        changed=el.get("changed"),
        run_once=run_once,
        filters=filters,
    )
