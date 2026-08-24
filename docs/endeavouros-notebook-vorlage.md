# Vorlage: EndeavourOS-Notebook (Dental Dimension)

> **Repo:** https://github.com/thelad-dev/endeavour-setup (privat)


Kopierbare **Installations- und Härte-Checkliste** für neue Linux-Notebooks.  
Referenzgerät: **NB64** (`NB64.dentaldimension.local`) — Stand 2026-08-24.

Platzhalter: `<NBXX>`, `<sam>`, `<user>_local`, `<Join-Admin>`.  
**Keine Passwörter/Secrets in diese Datei.**

| Feld | Wert (Vorlage) |
|------|----------------|
| Domäne | `DENTALDIMENSION.LOCAL` |
| OS | EndeavourOS (Arch rolling) + **Plasma 6** |
| AD-Stack | **Samba / Winbind** (nicht SSSD) |
| GPO-Client | [endeavour-gpo](https://github.com/thelad-dev/endeavour-gpo) |
| Zeitzone | `Europe/Berlin` |

---

## Ablauf auf einen Blick

```text
1. BIOS / Hardware
2. EndeavourOS-Basis + SSH + NTP
3. Pakete (Pflicht / optional)
4. Active Directory (krb5, Join, NSS/PAM)
5. endeavour-gpo-register + erster gpupdate
6. Energie-Policy (AC)
7. Netzwerk (Ethernet/USB, Bridge für VMs, Prelogin, DNS)
8. Software / Desktop-Feinschliff
9. Abnahme
```

---

## 1. Hardware / BIOS

- [ ] Firmware aktuell; Secure Boot / TPM nach Vorgabe (Win-VMs: TPM 2.0 + Secure Boot möglich)
- [ ] Wake-on-LAN an **Onboard-NIC** (USB-Ethernet/ASIX weckt im Soft-Off meist **nicht**)
- [ ] Netzteil: `/sys/class/power_supply/*/type` → `Mains`, `online=1`
- [ ] Speicherplatz: OS + GPO-Cache; bei KVM zusätzlich `/var/lib/libvirt/images` (ISO/Disks großzügig)

---

## 2. Basis-Installation EndeavourOS

- [ ] Installer: Plasma, Locale `de_DE.UTF-8`, Tastatur DE
- [ ] Hostname = AD-Computername: `<NBXX>` (z. B. `NB64`)
- [ ] Lokaler Break-Glass-Admin: **`<sam>_local`** (nicht der reine AD-SAM) — Beispiel NB64: AD `ladwein`, lokal `ladwein_local` ∈ `wheel`
- [ ] Falls Installer nur `<sam>` angelegt hat: Account nach `<sam>_local` umbenennen (Login-Name + Home), bevor Domain-Join den AD-User anlegt
- [ ] Nach erstem Boot:

```bash
sudo pacman -Syu
sudo pacman -S --needed chrony openssh
sudo systemctl enable --now sshd chronyd
timedatectl set-timezone Europe/Berlin
# chronyd übernimmt die Sync — timesyncd NICHT parallel (Arch-Preset: timesyncd oft enabled)
sudo systemctl disable --now systemd-timesyncd 2>/dev/null || true
# Firmen-NTP: Gateway + DCs (+ optional PTB), nicht nur Arch-Pool
# In /etc/chrony.conf z. B.:
#   server 192.168.2.2 iburst
#   server 192.168.2.12 iburst   # dc01
#   server 192.168.2.13 iburst   # dc02
chronyc tracking   # Uhr muss zum DC passen (Offset << 1s)
chronyc sources
```

---

## 3. Software-Pakete

### 3.1 Pflicht (jeder Client)

```bash
sudo pacman -S --needed \
  git zsh yay rsync chrony \
  cifs-utils gvfs gvfs-smb \
  samba smbclient krb5 \
  cups cups-filters hplip \
  firefox firefox-i18n-de \
  networkmanager-openvpn openvpn \
  bluez bluez-utils \
  pipewire pipewire-pulse wireplumber
```

### 3.2 IT-/Standard-Zusatz (wie NB64)

```bash
sudo pacman -S --needed \
  google-chrome \
  teamviewer
```

### 3.3 Optional: lokale Windows-VMs (KVM)

```bash
sudo pacman -S --needed \
  qemu-desktop libvirt virt-manager \
  edk2-ovmf swtpm virt-firmware \
  dnsmasq iptables-nft
sudo systemctl enable --now libvirtd
# nicht parallel modular virtnetworkd mit monolithischem libvirtd kämpfen lassen
sudo usermod -aG libvirt,kvm <user>_local
# AD-User später ebenfalls: usermod -aG libvirt <sam>
```

### 3.4 Software-Matrix (Soll)

| Komponente | Zweck | Pflicht? |
|------------|--------|----------|
| Firefox (+ de) | Browser | ja |
| Google Chrome | Browser | ja (IT) |
| TeamViewer | Fernhilfe | ja (IT) |
| Samba (+ winbindd) / smbclient / krb5 | AD | ja (Arch: kein Paket `winbind`) |
| CUPS + Filter/HPLIP | Drucken | ja |
| cifs-utils | Netzlaufwerke (GPO/CIFS) | ja |
| kio-extras (Plasma) | SMB in Dolphin | aus ISO; `gvfs-smb` optional/nicht nötig |
| OpenVPN (NM) | VPN | ja |
| git, yay, zsh | Admin | ja |
| chrony | Zeit sync (AD) | ja |
| qemu/libvirt/virt-manager | Win-VMs | optional |
| Plasma-Apps (Dolphin, Kate, Konsole, Spectacle, Okular, VLC) | Desktop | aus ISO |

Office / Fachsoftware: **nicht** über endeavour-gpo — separat (Flatpak/Paket/IT).

---

## 4. Active Directory

### 4.1 Kerberos — `/etc/krb5.conf`

```ini
[libdefaults]
    default_realm = DENTALDIMENSION.LOCAL
    dns_lookup_realm = true
    dns_lookup_kdc = true

[realms]
    DENTALDIMENSION.LOCAL = {
        kdc = dc01.dentaldimension.local
        kdc = dc02.dentaldimension.local
        admin_server = dc01.dentaldimension.local
    }

[domain_realm]
    .dentaldimension.local = DENTALDIMENSION.LOCAL
    dentaldimension.local = DENTALDIMENSION.LOCAL
```

### 4.2 Domain-Join (Winbind)

Voraussetzungen: DNS zu DCs, Uhr sync, Join-Konto.

```bash
# Arch: winbindd/wbinfo stecken im Paket „samba“ (kein separates winbind-Paket)
sudo pacman -S --needed samba smbclient
# Join — exakte Optionen an Firmenstandard anpassen:
sudo net ads join -U '<Join-Admin>'
sudo systemctl enable --now smb nmb winbind
# Trust NUR als root prüfen (sonst: Failed to open secrets.tdb / Access Denied):
sudo wbinfo -t
sudo net ads testjoin
```

### 4.3 NSS

`/etc/nsswitch.conf` (Auszug NB64):

```text
passwd: files systemd winbind
group:  files [SUCCESS=merge] systemd winbind
```

### 4.4 PAM

`pam_winbind.so` mit `krb5_auth` und **`cached_login`** (Offline-Login).  
Nach Join prüfen:

```bash
wbinfo -t
getent passwd <sam>
id <sam>
```

### 4.5 AD-Objekt & Gruppen

- [ ] Computer in korrekter OU
- [ ] **Ein** DNS-A-Record = aktuelle LAN/WLAN-IP (wandernde Clients: DNS pflegen, keine feste DHCP-Reservation nötig)
- [ ] Gruppe `<nbxx>_lokaleadmins` (o. Ä.) für lokale Admin-Rechte
- [ ] User in `linux-benutzer` / `linux-admins` je Policy

### 4.5.1 DNS-A-Record (verbindlich)

**Ziel:** genau **eine** A-Adresse für `<NBXX>.dentaldimension.local`, und die muss unter `hostname -I` liegen.

| Nicht tun | Warum |
|-----------|--------|
| Blind `sudo net ads dns register -P` bei laufendem libvirt-NAT | Registriert **alle** Interfaces inkl. `virbr0` → z. B. `192.168.122.1` im AD-DNS |
| Alte A-Records stehen lassen | SSH/Monitoring landet auf toter IP (NB64: `.173` vs. aktuelle `.142`) |

**Empfohlen (wandernde Notebooks — NB64):**

1. Nach Netzwechsel DNS-A auf **aktuelle** IP setzen (DHCP-Reservation **nicht** — Client wechselt Subnetz/WLAN).
2. **Nicht** blind `sudo net ads dns register -P` bei laufendem libvirt-NAT (registriert `virbr0`).
3. Am DC (PowerShell, Beispiel):

```powershell
# Stale löschen, aktuelle IP setzen (als DNS-Admin)
Remove-DnsServerResourceRecord -ZoneName 'dentaldimension.local' -Name 'NB64' -RRType A -RecordData '192.168.2.173' -Force
Add-DnsServerResourceRecordA -ZoneName 'dentaldimension.local' -Name 'NB64' -IPv4Address '192.168.2.142'
Get-DnsServerResourceRecord -ZoneName 'dentaldimension.local' -Name 'NB64' -RRType A
```

4. Prüfen: `dig @dc01.dentaldimension.local <NBXX>.dentaldimension.local A +short` — **eine** Zeile, richtige IP.

### 4.6 Home-Verzeichnis

Unter NB64 typisch: `/home/DENTALDIMENSION/<sam>`.  
`pam_mkhomedir` (oder Äquivalent) aktiv, damit das Home beim ersten Login entsteht.

### 4.7 Offline-Login

- Samba: `winbind offline logon = yes` (setzt `endeavour-gpo-register`)
- User **einmal online** anmelden, damit das Passwort gecacht wird

---

## 5. endeavour-gpo (Laufwerke, Drucker, Hooks)

Repo: https://github.com/thelad-dev/endeavour-gpo

```bash
git clone https://github.com/thelad-dev/endeavour-gpo.git
cd endeavour-gpo
sudo ./scripts/install.sh
# alternativ:
# sudo python3 -m pip install -e . --break-system-packages
# sudo endeavour-gpo-register
```

### Was Register/Install einrichtet

| Baustein | Inhalt |
|----------|--------|
| Samba | `/etc/samba/endeavour-gpo.conf` — `apply group policies = yes`, `winbind offline logon = yes` |
| CSE | Drives + Printers in `gpext.conf` (Endeavour-CSE ans Ende) |
| Timer | `endeavour-gpupdate.timer` (~90 min + Jitter) |
| Login | `endeavour-gpupdate-login.service` |
| Remote | Socket `:46327` / `endeavour-gpupdate-remote` |
| Energie | `ac-sleep-guard` + `endeavour-gpo-ac-nosleep.{service,sync.service,timer}` |
| Netz | `endeavour-gpo-nm-prelogin.service` + Plasmalogin-Drop-in |
| CUPS | SMB-Kerberos-Shim (offizielles `smbspool` **nicht** überschreiben) |

### Erster Policy-Lauf

```bash
klist   # Ticket des AD-Users
endeavour-gpupdate --force
# oder mit sudo und User-Ticket:
sudo -E env KRB5CCNAME=/tmp/krb5cc_$(id -u) endeavour-gpupdate --force
```

### Erwartete Ergebnisse (NB64)

- Laufwerke: `~/netzlaufwerke/<Buchstabe>_<Titel>/` (+ AD-Home z. B. `H_…`)
- Drucker: CUPS-Queues `endeavour-sophos-*` (Buchhaltung, Ei, Technik, …)

```bash
findmnt -t cifs
lpstat -a
lpstat -v
systemctl is-enabled endeavour-gpupdate.timer \
  endeavour-gpo-ac-nosleep.timer endeavour-gpo-nm-prelogin.service
```

---

## 6. Energie-Policy (verbindlich)

| Ereignis | Am Netzteil (AC) | Batterie |
|----------|------------------|----------|
| Idle / Auto-Suspend | **aus** | Plasma-Default |
| Deckel | **ignorieren** | Plasma-Default |
| **Power-Taste** | **Suspend** | **Suspend** |
| Hibernate | aus | aus |
| Herunterfahren | nur Startmenü / Logout | ebenso |

Technik:

- Skript: `/usr/local/lib/endeavour-gpo/ac-sleep-guard.sh`
- Units: `endeavour-gpo-ac-nosleep.service`, `-sync.service`, `.timer` (alle ~2 min)
- logind: `HandlePowerKey=suspend`, Lid/Idle ignore
- PowerDevil (verschachtelt!): `[AC][SuspendAndShutdown]` — `AutoSuspendAction=0`, `LidAction=0`, `PowerButtonAction=1`
- User-`~/.config/powerdevilrc` muss mitgezogen werden (überschreibt sonst `/etc/xdg`)

```bash
sudo /usr/local/lib/endeavour-gpo/ac-sleep-guard.sh on
sudo /usr/local/lib/endeavour-gpo/ac-sleep-guard.sh status
# CanSuspend erlaubt (z. B. challenge/yes); CanHibernate = no
# PowerButtonAction = 1
systemd-inhibit --list | grep endeavour-gpo
```

**Manuell testen:** Power-Taste → Suspend; Aufwachen; Shutdown nur über Menü.

---

## 7. Netzwerk

### 7.1 Host-Anbindung

- [ ] Ethernet oder USB-NIC als **systemweite** NM-Verbindung, Autoconnect, hohe Priorität  
  (NB64: Verbindung `USB-Ethernet` → Interface `enp0s20f0u1c2`)
- [ ] WLAN: Firmen-SSID; **802.1X „DENSION Dental“** ggf. zusätzlich systemweit
- [ ] Prelogin: `endeavour-gpo-nm-prelogin.service` + Plasmalogin nach `NetworkManager-wait-online`
- [ ] DNS: **ein** A-Record für `<NBXX>` = aktuelle Host-IP (keine Alt-IPs, kein virbr0)

### 7.2 Bridge für VMs (echte LAN-IP, nur Ethernet)

Ziel: QEMU/KVM-Gast bekommt DHCP aus dem **physischen** LAN (wie ein eigener PC).  
**Zuverlässig nur mit Kabel** — WiFi-Bridge scheitert an Consumer-APs (3-Adress-Modus).

```bash
# Beispiel USB-Ethernet → br0 (Namen anpassen)
ETH_IF=enp0s20f0u1c2
ETH_CON="USB-Ethernet"

sudo nmcli connection add type bridge ifname br0 con-name br0-lan \
  ipv4.method auto ipv6.method auto connection.autoconnect yes bridge.stp no
sudo nmcli connection modify "$ETH_CON" \
  connection.master br0 connection.slave-type bridge \
  ipv4.method disabled ipv6.method ignore connection.autoconnect yes
sudo nmcli connection up "$ETH_CON"
sudo nmcli connection up br0-lan
ip -br a   # Host-IP liegt auf br0
```

In **virt-manager**: NIC → Netzwerkquelle → **Überbrückungsgerät…** → `br0`, Modell `virtio`.

**Achtung:** Bridge-Umbau kann SSH kurz/länger unterbrechen — lokal am Gerät oder Konsole bereithalten.  
Notfall Host-Netz ohne Bridge:

```bash
sudo nmcli connection modify USB-Ethernet connection.master "" connection.slave-type "" \
  ipv4.method auto ipv6.method auto
sudo nmcli connection down br0-lan 2>/dev/null
sudo nmcli connection delete br0-lan 2>/dev/null
sudo nmcli connection up USB-Ethernet
```

### 7.3 VM-Netz umschalten (Ethernet-Bridge vs. WiFi/NAT)

| Modus | Wann | virt-manager / Skript |
|-------|------|------------------------|
| Bridge `br0` | Host am Kabel, Gast braucht LAN-IP | Überbrückungsgerät `br0` |
| Libvirt-NAT `default` | Host am WLAN / „immer online“ | Virtuelles Netzwerk `default` |

Auf dem Schreibtisch des Users (Vorlage NB64):

- `~/Schreibtisch/vm64-netz-wifi.sh` — VM → NAT (folgt Host-Uplink)
- `~/Schreibtisch/vm64-netz-ethernet-bridge.sh` — VM → `br0`

Nach Umschalten im Gast DHCP erneuern (`ipconfig /renew` unter Windows).

---

## 8. Benutzer & Rechte

- [ ] Lokal: `<user>_local` ∈ `wheel`
- [ ] AD-User einmal **online** anmelden (Kerberos + Offline-Cache)
- [ ] `sudo` für AD-User nur über Policy/`linux-admins`
- [ ] KVM: AD-User ∈ `libvirt` (und ggf. `kvm`)

---

## 9. Abnahme (neues Gerät)

Skript (Repo): `sudo ./scripts/client-abnahme.sh <sam>`

Manuell:

```bash
hostname -f
timedatectl | grep synchronized
systemctl is-enabled chronyd; systemctl is-enabled systemd-timesyncd   # timesyncd = disabled
sudo wbinfo -t && sudo net ads testjoin && id <sam>
getent passwd <sam>_local; id <sam>_local   # Break-Glass ∈ wheel
dig @dc01.dentaldimension.local "$(hostname -s).dentaldimension.local" A +short
ls ~/netzlaufwerke   # als AD-User nach Login
lpstat -a
systemctl is-enabled sshd endeavour-gpupdate.timer \
  endeavour-gpo-ac-nosleep.timer endeavour-gpo-nm-prelogin.service
sudo /usr/local/lib/endeavour-gpo/ac-sleep-guard.sh status
# Power-Taste → Suspend
# Bei KVM: Bridge nur am Ethernet; WLAN → NAT; br0-lan ohne Carrier down
```

- [ ] Ein SOPHOS-Drucker testen
- [ ] Laufwerk lesen/schreiben
- [ ] Reboot → AD-Login, Timer und AC-Policy wieder aktiv
- [ ] DNS zeigt genau die aktuelle IP
- [ ] SSH von IT-Netz erreichbar (`sshd` enabled)

---

## 10. Stolpersteine (aus NB64)

1. USB-Ethernet **WoL** unzuverlässig (ASIX) — Onboard-NIC nutzen.
2. **Doppelte / falsche DNS-A-Records** → falsche SSH-Ziele; A-Record bei Netzwechsel am DC pflegen; **nie** libvirt-`virbr0` mitregistrieren.
3. Plasma 6: PowerDevil-Keys **verschachtelt** (`[AC][SuspendAndShutdown]`), nicht flach `[AC]`.
4. CUPS: `/usr/bin/smbspool` nicht durch Wrapper ersetzen — endeavour-gpo-Shim nutzen.
5. libvirt: **libvirtd** monolithisch **oder** modular — nicht mischen (NB64: modular `virtqemud`/`virtnetworkd`).
6. Idle/Deckel aus ≠ Power-Taste aus — Power-Taste bleibt **Suspend**.
7. Bridge-Umbau kann Host-SSH killen — Notfall-NM-Befehle bereithalten.
8. WiFi: keine echte LAN-Bridge; VM dann **NAT**; `br0-lan` ohne Ethernet-Slave **down** + Autoconnect aus.
9. **chrony + systemd-timesyncd parallel** → timesyncd disable; sonst konkurrierende NTP-Quellen.
10. `wbinfo -t` / `net ads testjoin` **ohne sudo** wirken „broken“ (`secrets.tdb` root-only) — immer root.
11. Konsolen-Session oft als `<sam>_local`; AD-GPO/CIFS brauchen Login als `<sam>` (oder User-Ticket).

---

## 11. Schnellreferenz Befehle

| Aufgabe | Befehl |
|---------|--------|
| GPO erzwingen | `endeavour-gpupdate --force` |
| AC-Policy an | `sudo …/ac-sleep-guard.sh on` |
| AC-Status | `sudo …/ac-sleep-guard.sh status` |
| Ticket | `klist` / `kinit <sam>@DENTALDIMENSION.LOCAL` |
| Trust | `wbinfo -t` |
| Drucker | `lpstat -a` |
| Laufwerke | `findmnt -t cifs` |

---

## 12. Changelog

| Datum | Änderung |
|-------|----------|
| 2026-08-21 | Erstfassung NB64 + endeavour-gpo; Power-Taste = Suspend |
| 2026-08-21 | Erweitert: Phasenablauf, Bridge/NAT für VMs, Notfall-NM, DNS/SSH-Lektionen, Software-Matrix |
| 2026-08-24 | Vollanalyse NB64 (`.2.142`): timesyncd-Konflikt, DNS-Härte (kein virbr0), Join-Checks als root, `scripts/client-abnahme.sh`; vm64-Setup User-seitig |
