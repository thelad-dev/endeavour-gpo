from __future__ import annotations

from pathlib import Path

from endeavour_gpo.drives.filters import FilterContext, GppFilter, evaluate_filters
from endeavour_gpo.drives.parser import parse_drives_xml

FIXTURES = Path(__file__).parent / "fixtures"


class FakeToken:
    def __init__(self, sids: list[str]):
        self.sids = sids


def test_parse_drives_xml():
    drives = parse_drives_xml(FIXTURES / "drives.xml")
    assert len(drives) == 2

    shared = drives[0]
    assert shared.letter == "S"
    assert shared.path == r"\\fileserver.example.com\shared"
    assert shared.persistent is True
    assert shared.action == "U"
    assert len(shared.filters) == 1
    assert shared.filters[0].filter_type == "FilterGroup"

    deleted = drives[1]
    assert deleted.action == "D"
    assert deleted.mount_letter == "P"


def test_cifs_source():
    drives = parse_drives_xml(FIXTURES / "drives.xml")
    assert drives[0].cifs_source() == "//fileserver.example.com/shared"


def test_filter_group_sid_match():
    filt = GppFilter(
        filter_type="FilterGroup",
        bool_op="AND",
        not_=False,
        attributes={"sid": "S-1-5-21-1234567890-1234567890-1234567890-1001"},
    )
    ctx = FilterContext(
        username="EXAMPLE\\alice",
        security_token=FakeToken(["S-1-5-21-1234567890-1234567890-1234567890-1001"]),
    )
    assert evaluate_filters([filt], ctx) is True


def test_filter_group_sid_no_match():
    filt = GppFilter(
        filter_type="FilterGroup",
        bool_op="AND",
        not_=False,
        attributes={"sid": "S-1-5-21-9999999999-9999999999-9999999999-9999"},
    )
    ctx = FilterContext(
        username="EXAMPLE\\alice",
        security_token=FakeToken(["S-1-5-21-1234567890-1234567890-1234567890-1001"]),
    )
    assert evaluate_filters([filt], ctx) is False


def test_filter_user():
    filt = GppFilter(
        filter_type="FilterUser",
        bool_op="AND",
        not_=False,
        attributes={"name": "EXAMPLE\\alice"},
    )
    ctx = FilterContext(username="EXAMPLE\\alice")
    assert evaluate_filters([filt], ctx) is True


def test_filter_collection_and():
    collection = GppFilter(
        filter_type="FilterCollection",
        bool_op="AND",
        not_=False,
        attributes={},
        children=[
            GppFilter(
                filter_type="FilterUser",
                bool_op="AND",
                not_=False,
                attributes={"name": "EXAMPLE\\alice"},
            ),
            GppFilter(
                filter_type="FilterGroup",
                bool_op="AND",
                not_=False,
                attributes={"sid": "S-1-5-21-1234567890-1234567890-1234567890-1001"},
            ),
        ],
    )
    ctx = FilterContext(
        username="EXAMPLE\\alice",
        security_token=FakeToken(["S-1-5-21-1234567890-1234567890-1234567890-1001"]),
    )
    assert evaluate_filters([collection], ctx) is True


def test_no_filters_passes():
    assert evaluate_filters([], FilterContext(username="EXAMPLE\\alice")) is True
