"""GPP item-level targeting (Filters) parsing and evaluation."""

from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

log = logging.getLogger(__name__)

# Filters with a dedicated evaluator in this module.
SUPPORTED_FILTER_TYPES = frozenset(
    {
        "FilterGroup",
        "FilterUser",
        "FilterCollection",
        "FilterRunOnce",
    }
)


@dataclass
class GppFilter:
    filter_type: str
    bool_op: str
    not_: bool
    attributes: dict[str, str] = field(default_factory=dict)
    children: list[GppFilter] = field(default_factory=list)


@dataclass
class FilterContext:
    """Runtime context for ILT evaluation during gpupdate."""

    username: str
    security_token: Any = None
    computer_name: Optional[str] = None
    group_resolver: Optional[Callable[[GppFilter], bool]] = None

    def user_sam(self) -> str:
        return self.username.split("\\")[-1]

    def user_domain(self) -> str:
        if "\\" in self.username:
            return self.username.split("\\", 1)[0]
        return ""


def parse_filters_element(filters_el: ET.Element) -> list[GppFilter]:
    return [_parse_filter_node(child) for child in filters_el]


def _parse_filter_node(el: ET.Element) -> GppFilter:
    node = GppFilter(
        filter_type=el.tag,
        bool_op=el.get("bool", "AND"),
        not_=el.get("not", "0") == "1",
        attributes=dict(el.attrib),
    )
    if el.tag == "FilterCollection":
        node.children = [_parse_filter_node(child) for child in el]
    return node


def evaluate_filters(filters: list[GppFilter], ctx: FilterContext) -> bool:
    """Return True when all top-level filters pass (MS-GPPREF chaining)."""
    if not filters:
        return True

    result: Optional[bool] = None
    for filt in filters:
        if filt.filter_type == "FilterRunOnce":
            continue
        match = _evaluate_filter(filt, ctx)
        if filt.not_:
            match = not match

        if result is None:
            result = match
            continue

        if filt.bool_op.upper() == "OR":
            result = result or match
        else:
            result = result and match

    return True if result is None else result


def _evaluate_filter(filt: GppFilter, ctx: FilterContext) -> bool:
    if filt.filter_type == "FilterCollection":
        return _evaluate_collection(filt, ctx)
    if filt.filter_type == "FilterGroup":
        return _evaluate_group(filt, ctx)
    if filt.filter_type == "FilterUser":
        return _evaluate_user(filt, ctx)
    if filt.filter_type == "FilterRunOnce":
        return True

    log.warning("Unsupported GPP filter type %s — treating as non-match", filt.filter_type)
    return False


def _evaluate_collection(collection: GppFilter, ctx: FilterContext) -> bool:
    result: Optional[bool] = None
    for child in collection.children:
        match = _evaluate_filter(child, ctx)
        if child.not_:
            match = not match

        if result is None:
            result = match
            continue

        if child.bool_op.upper() == "OR":
            result = result or match
        else:
            result = result and match

    return False if result is None else result


def _evaluate_group(filt: GppFilter, ctx: FilterContext) -> bool:
    if ctx.group_resolver is not None:
        return ctx.group_resolver(filt)

    sid = filt.attributes.get("sid", "").strip()
    if ctx.security_token is not None and sid:
        return _token_has_sid(ctx.security_token, sid)

    name = filt.attributes.get("name", "").strip()
    if name and ctx.security_token is not None:
        return _token_has_group_name(ctx.security_token, name)

    log.warning("FilterGroup without resolvable SID/name/token: %s", filt.attributes)
    return False


def _evaluate_user(filt: GppFilter, ctx: FilterContext) -> bool:
    expected = filt.attributes.get("name", "").strip()
    if not expected:
        return False
    expected_sam = expected.split("\\")[-1].lower()
    actual = ctx.user_sam().lower()
    return expected_sam == actual or expected.lower() == ctx.username.lower()


def _token_has_sid(token: Any, sid: str) -> bool:
    target = sid.upper()
    for token_sid in token.sids:
        if str(token_sid).upper() == target:
            return True
    return False


def _token_has_group_name(token: Any, group_name: str) -> bool:
    """Best-effort name match against token SID strings (SID preferred in GPO XML)."""
    short = group_name.split("\\")[-1].lower()
    for token_sid in token.sids:
        sid_str = str(token_sid)
        if short in sid_str.lower():
            return True
    return False
