from __future__ import annotations

import logging
from pathlib import Path

from endeavour_gpo.printers.parser import SharedPrinterMap, parse_printers_xml

FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_shared_printers_only(caplog):
    with caplog.at_level(logging.WARNING):
        printers = parse_printers_xml(FIXTURES / "printers.xml")

    assert len(printers) == 2
    assert any("PortPrinter" in r.message for r in caplog.records)

    technik = printers[0]
    assert technik.name == "Technik"
    assert technik.path == r"\\SOPHOS\Technik"
    assert technik.action == "U"
    assert technik.default is True
    assert technik.smb_uri() == "smb://SOPHOS/Technik"
    assert technik.queue_name() == "endeavour-sophos-technik"
    assert len(technik.filters) == 1
    assert technik.filters[0].filter_type == "FilterGroup"

    deleted = printers[1]
    assert deleted.action == "D"
    assert deleted.should_delete is True


def test_queue_name_umlaut_folding():
    p = SharedPrinterMap(
        uid="{x}",
        name="GL",
        action="U",
        path=r"\\SOPHOS\Geschäftsleitung-Assistenz",
        default=False,
        skip_local=False,
        delete_all=False,
        location="",
        comment="",
        username=None,
        cpassword=None,
        bypass_errors=False,
        persistent=False,
    )
    assert p.queue_name() == "endeavour-sophos-geschaftsleitung-assistenz"
    assert p.smb_uri() == "smb://SOPHOS/Gesch%C3%A4ftsleitung-Assistenz"
