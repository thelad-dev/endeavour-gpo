# endeavour-gpo

Custom Samba **Group Policy Client-Side Extension (CSE)** for **EndeavourOS** (and other Linux domain members) that applies Active Directory **Drive Maps** preferences from `Drives.xml` using **`mount.cifs`**.

Windows clients get mapped drives from GPO Preferences out of the box. Samba ships a built-in drive-map CSE (`gp_drive_maps_user_ext`, `gio mount`) that only partially supports item-level targeting. This project closes that gap for EndeavourOS deployments:

- Parses `User/Preferences/Drives/Drives.xml` from the GPO SYSVOL cache (via Samba's `gp_xml_ext` framework)
- Respects GPO **security filtering** (handled by Samba when building the GPO list)
- Evaluates **item-level targeting** (`FilterGroup`, `FilterCollection`, `FilterUser`, …)
- Mounts shares with **`mount.cifs`** (Kerberos/`sec=krb5` by default, optional GPP credentials)
- Tracks applied state in Samba's GPO cache for clean unapply on logoff / policy change
- **Coexistence:** runs in parallel with Samba's built-in drive CSE; registered last in `gpext.conf` so Endeavour mappings take priority (gio mounts are released before `mount.cifs`)
- **Mount failures** trigger a desktop notification (`notify-send`) for the logged-in user

## Requirements

- Domain-joined EndeavourOS / Arch Linux host with Samba (`samba`, `python-samba`)
- `cifs-utils` (`mount.cifs`)
- Kerberos ticket or domain credentials for the logging-in user
- Root privileges for `samba-gpupdate` (standard Samba GPO apply path)

## Installation

```bash
git clone https://github.com/thelad-dev/endeavour-gpo.git
cd endeavour-gpo
pip install -e ".[dev]"
sudo endeavour-gpo-register
```

Registration writes an entry to `/var/lib/samba/gpext.conf` and loads the CSE on the next `samba-gpupdate`.

## Usage

After registration, drive maps apply with the Samba gpupdate flow for the **logged-in user**
(Samba 4.24+: `--target=User`; without `-U` the machine account is used and mounts land in the wrong home):

```bash
sudo env KRB5CCNAME=/tmp/krb5cc_$(id -u) \
  samba-gpupdate --target=User -U "$USER" --use-kerberos=required --force
sudo env KRB5CCNAME=/tmp/krb5cc_$(id -u) \
  samba-gpupdate --target=User -U "$USER" --use-kerberos=required --rsop
```

Mounts appear under:

```text
~/netzlaufwerke/<letter>_<title>/
```

Examples: `Q_IT`, `Z_PUBLIC`, `H_ladwein` (title from GPO label, or the share name).

**AD home drive:** `homeDirectory` / `homeDrive` on the user object (e.g. `H:` → `\\dfs\homes\<user>`)
are mapped automatically in addition to Preferences `Drives.xml`.

Persistent (`reconnect`) mappings also install a systemd user mount unit under `~/.config/systemd/user/`.

## Architecture

```text
samba-gpupdate
  └── gp_ext_loader → endeavour_gpo.cse.gp_drive_maps_ext
        ├── endeavour_gpo.drives.parser   (Drives.xml → datamodel)
        ├── endeavour_gpo.drives.filters  (ILT evaluation)
        └── endeavour_gpo.drives.mounter (mount.cifs / systemd)
```

The CSE subclasses Samba's `gp_xml_ext` and `gp_misc_applier` — the same pattern as upstream `gp_drive_maps_ext.py`, but with Endeavour-specific mounting and fuller ILT support.

## Item-level targeting

| Filter | Support |
|--------|---------|
| `FilterGroup` | Yes (SID / name via security token) |
| `FilterCollection` | Yes (nested AND/OR) |
| `FilterUser` | Yes |
| `FilterRunOnce` | Yes (no persistent systemd unit) |
| `FilterOrgUnit`, `FilterSite`, WMI, LDAP, … | Logged as unsupported → item skipped |

## Security note

Legacy GPP **`cpassword`** fields can be decrypted (MS-GPPREF static AES key). Prefer Kerberos/`sec=krb5` and empty `userName`/`cpassword` in new GPO items.

Drive items that do carry `userName` need a `mount.cifs` credentials file. It is written per drive letter (lowercase) to:

```text
~/.cache/endeavour-gpo/credentials/drive-<letter>.cred
```

with mode `0600`, rewritten on each apply, and deleted again when the drive is unmapped. `--rsop` only prints the resulting `mount.cifs` command and never writes credentials to disk.

## Development

```bash
pip install -e ".[dev]"
pytest
ruff check .
```

## License

GPL-3.0-or-later — compatible with Samba's gp_ext framework.
