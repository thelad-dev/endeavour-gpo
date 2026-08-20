# endeavour-gpo

Custom Samba **Group Policy Client-Side Extensions (CSE)** for **EndeavourOS** (and other Linux domain members):

- **Drive Maps** from `Drives.xml` via **`mount.cifs`** (plus AD `homeDirectory`/`homeDrive`)
- **Shared Printers** from `Printers.xml` via **CUPS** (`lpadmin` + `smb://` + Kerberos)
- **`endeavour-gpupdate`** — Windows-like `gpupdate /force`
- Automatic refresh (~90+0–30 min) and remote trigger (SSH + localhost socket)

## Requirements

- Domain-joined EndeavourOS / Arch with Samba (`samba`, `python-samba`), `cifs-utils`, `cups`
- Kerberos ticket for the logged-in user
- Root for registration / `samba-gpupdate`

## Installation

```bash
git clone https://github.com/thelad-dev/endeavour-gpo.git
cd endeavour-gpo
sudo python3 -m pip install -e ".[dev]" --break-system-packages
sudo endeavour-gpo-register
```

Registration:

- Writes drive + printer CSEs into `/var/lib/samba/gpext.conf` (last = priority)
- Enables `apply group policies = yes` via `/etc/samba/endeavour-gpo.conf`
- Installs systemd timer, login hook, and remote socket (`127.0.0.1:46327`)

## Usage

```bash
# wie Windows: gpupdate /force
sudo endeavour-gpupdate --force

# alle aktiven Sitzungen (Timer / Remote)
sudo endeavour-gpupdate --force --all-sessions

# RSOP
sudo endeavour-gpupdate --rsop
```

### Remote (vom Richtlinienserver / Admin-PC)

Windows `Invoke-GPUpdate` nutzt Task Scheduler — unter Linux:

```bash
# empfohlen: SSH
endeavour-gpupdate-remote nb64
# entspricht: ssh nb64 'sudo systemctl start endeavour-gpupdate.service'

# lokal auf dem Client (Socket, nur localhost)
printf '' | nc 127.0.0.1 46327
```

### Mounts

```text
~/netzlaufwerke/<letter>_<title>/   # z. B. Q_IT, Z_PUBLIC, H_ladwein
```

AD-Home (`homeDirectory`/`homeDrive`) wird zusätzlich zu Preferences gemappt.

### Printers

CUPS-Queues `endeavour-<server>-<share>` (z. B. `endeavour-sophos-technik`) mit
`auth-info-required=negotiate`. PortPrinter/LocalPrinter: noch nicht (skip + Warnung).

## Architecture

```text
endeavour-gpupdate / samba-gpupdate / winbind timer
  └── CSEs
        ├── Endeavour/Preferences/Drives   → mount.cifs + AD home
        └── Endeavour/Preferences/Printers → CUPS SharedPrinter
```

## Item-level targeting

| Filter | Support |
|--------|---------|
| `FilterGroup` | Yes |
| `FilterCollection` | Yes |
| `FilterUser` | Yes |
| `FilterRunOnce` | Yes |
| andere | skip + warn |

## Security note

Legacy GPP **`cpassword`** can be decrypted (MS-GPPREF). Prefer Kerberos. Credential files for drive maps (if any): `~/.cache/endeavour-gpo/credentials/drive-<letter>.cred` mode `0600`.

Remote socket binds **localhost only**; cross-host refresh uses **SSH**.

## Development

```bash
pip install -e ".[dev]"
pytest
ruff check .
```

## License

GPL-3.0-or-later — compatible with Samba's gp_ext framework.
