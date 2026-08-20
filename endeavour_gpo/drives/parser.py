"""Parse GPO Preferences Drives.xml into structured drive map items."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from endeavour_gpo.drives.filters import GppFilter, parse_filters_element

_UNSAFE_DIR_CHARS = re.compile(r"[^\w\-]+", re.UNICODE)

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

DRIVES_CLSID = "{8FDDCC1A-0C3C-43cd-A6B4-71A6DF20DA8C}"
DRIVE_CLSID = "{935D1B74-9CB8-4e3c-9914-7DD559B7A417}"


@dataclass
class DriveMap:
    uid: str
    name: str
    action: str
    path: str
    label: str
    letter: str
    persistent: bool
    use_letter: bool
    this_drive: str
    all_drives: str
    username: Optional[str]
    password_enc: Optional[str]
    bypass_errors: bool
    changed: Optional[str]
    run_once: bool = False
    filters: list[GppFilter] = field(default_factory=list)

    @property
    def action_label(self) -> str:
        return ACTION_LABELS.get(self.action, self.action)

    @property
    def mount_letter(self) -> str:
        letter = (self.letter or "").rstrip(":").upper()
        return letter

    @property
    def folder_title(self) -> str:
        """Short title for ~/netzlaufwerke/<letter>_<title>/ (e.g. IT, PUBLIC)."""
        raw = (self.label or "").strip()
        if not raw:
            source = self.cifs_source()
            raw = source.rstrip("/").split("/")[-1] if source else ""
        if not raw:
            return ""
        # "PUBLIC (\\dfs\\public)" → "PUBLIC"
        raw = re.split(r"[(\[]", raw, maxsplit=1)[0].strip()
        cleaned = _UNSAFE_DIR_CHARS.sub("_", raw).strip("_")
        return cleaned

    @property
    def mount_dirname(self) -> str:
        """Directory under netzlaufwerke: ``Q_IT``, ``Z_PUBLIC``, ``H_ladwein``."""
        letter = self.mount_letter or "X"
        title = self.folder_title
        if title:
            return "%s_%s" % (letter, title)
        return letter

    @property
    def is_hidden(self) -> bool:
        return self.this_drive == "HIDE"

    @property
    def should_mount(self) -> bool:
        return self.action in (ACTION_CREATE, ACTION_UPDATE, ACTION_REPLACE)

    @property
    def should_unmount(self) -> bool:
        return self.action == ACTION_DELETE

    def cifs_source(self) -> str:
        """Convert UNC path to mount.cifs source (//server/share)."""
        path = (self.path or "").strip()
        if not path:
            return ""
        normalized = path.replace("\\", "/")
        if normalized.startswith("//"):
            return normalized
        if normalized.startswith("/"):
            return "/" + normalized.lstrip("/")
        return "//" + normalized.lstrip("/")


def parse_drives_xml(path: str | Path) -> list[DriveMap]:
    tree = ET.parse(path)
    return parse_drives_element(tree.getroot())


def parse_drives_element(root: ET.Element) -> list[DriveMap]:
    if root.tag != "Drives":
        raise ValueError(f"Expected <Drives> root element, got <{root.tag}>")

    if root.get("disabled") == "1":
        return []

    results: list[DriveMap] = []
    for drive_el in root.findall("Drive"):
        drive = _parse_drive_element(drive_el)
        if drive is not None:
            results.append(drive)
    return results


def _parse_drive_element(drive_el: ET.Element) -> Optional[DriveMap]:
    if drive_el.get("disabled") == "1":
        return None

    props = drive_el.find("Properties")
    if props is None:
        return None
    if props.get("disabled") == "1":
        return None

    filters_el = drive_el.find("Filters")
    filters = parse_filters_element(filters_el) if filters_el is not None else []
    run_once = _has_run_once_filter(filters_el)

    return DriveMap(
        uid=drive_el.get("uid", ""),
        name=drive_el.get("name", ""),
        action=props.get("action", ACTION_UPDATE),
        path=props.get("path", ""),
        label=props.get("label", ""),
        letter=props.get("letter", ""),
        persistent=props.get("persistent", "0") == "1",
        use_letter=props.get("useLetter", "1") == "1",
        this_drive=props.get("thisDrive", "NOCHANGE"),
        all_drives=props.get("allDrives", "NOCHANGE"),
        username=(props.get("userName") or None),
        password_enc=(props.get("cpassword") or None),
        bypass_errors=drive_el.get("bypassErrors", "0") == "1",
        changed=drive_el.get("changed"),
        run_once=run_once,
        filters=filters,
    )


def _has_run_once_filter(filters_el: Optional[ET.Element]) -> bool:
    if filters_el is None:
        return False
    return filters_el.find("FilterRunOnce") is not None
