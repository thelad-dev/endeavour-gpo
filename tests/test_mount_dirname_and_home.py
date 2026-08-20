from __future__ import annotations

from endeavour_gpo.drives.home import home_drive_from_attrs
from endeavour_gpo.drives.parser import DriveMap, parse_drives_xml


def _drive(**overrides) -> DriveMap:
    base = dict(
        uid="{test}",
        name="Q:",
        action="U",
        path=r"\\dfs\IT",
        label="IT",
        letter="Q",
        persistent=False,
        use_letter=True,
        this_drive="NOCHANGE",
        all_drives="NOCHANGE",
        username=None,
        password_enc=None,
        bypass_errors=False,
        changed=None,
    )
    base.update(overrides)
    return DriveMap(**base)


def test_mount_dirname_letter_and_label() -> None:
    assert _drive(letter="Q", label="IT").mount_dirname == "Q_IT"
    assert (
        _drive(letter="Z", label=r"PUBLIC (\\dfs\public)").mount_dirname == "Z_PUBLIC"
    )


def test_mount_dirname_from_path_when_label_empty() -> None:
    assert _drive(letter="H", label="", path=r"\\dfs\homes\ladwein").mount_dirname == (
        "H_ladwein"
    )


def test_mount_dirname_sanitizes_unsafe_chars() -> None:
    assert _drive(letter="P", label="Foo/Bar:Baz").mount_dirname == "P_Foo_Bar_Baz"


def test_fixture_drive_mount_dirname() -> None:
    drives = {
        d.mount_letter: d for d in parse_drives_xml("tests/fixtures/drives.xml") if d.mount_letter
    }
    assert drives["S"].mount_dirname == "S_Shared"
    assert drives["P"].mount_dirname == "P_Projects"


def test_home_drive_from_attrs() -> None:
    drive = home_drive_from_attrs(r"\\dfs\homes\ladwein", "H:", sam="DOMAIN\\ladwein")
    assert drive is not None
    assert drive.uid == "{AD-HomeDirectory}"
    assert drive.mount_letter == "H"
    assert drive.label == "ladwein"
    assert drive.mount_dirname == "H_ladwein"
    assert drive.path == r"\\dfs\homes\ladwein"
    assert drive.persistent is True
    assert drive.username is None


def test_home_drive_from_attrs_empty() -> None:
    assert home_drive_from_attrs("", "H:") is None
    assert home_drive_from_attrs(r"\\dfs\homes\x", "") is None
