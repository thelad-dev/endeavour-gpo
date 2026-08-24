#!/usr/bin/env bash
# Am Netzteil: kein Idle-/Deckel-Sleep. Power-Taste = Suspend (bewusst).
# Aufruf: ac-sleep-guard.sh on|off|sync|status
set -euo pipefail

PIDFILE=/run/endeavour-gpo-ac-sleep-guard.pid
WHY="endeavour-gpo: kein Idle-/Deckel-Sleep am Netzteil (Power-Taste = Suspend)"
LOGIND_DROPIN=/etc/systemd/logind.conf.d/90-endeavour-gpo-ac-nosleep.conf
SLEEP_DROPIN=/etc/systemd/sleep.conf.d/90-endeavour-gpo-ac-nosleep.conf
POWERDEVIL_XDG=/etc/xdg/powerdevilrc
# PowerButtonAction=1 → Sleep/Suspend (Plasma 6); AutoSuspend/Lid=0 → NoAction
POWERDEVIL_RC_BODY='[AC][SuspendAndShutdown]
AutoSuspendAction=0
AutoSuspendIdleTimeoutSec=0
LidAction=0
PowerButtonAction=1
PowerDownAction=0
InhibitLidActionWhenExternalMonitorPresent=true
SleepMode=0

[AC][Display]
DimDisplayWhenIdle=false
TurnOffDisplayWhenIdle=false
TurnOffDisplayIdleTimeoutSec=0
LockBeforeTurnOffDisplay=false
'

# Nur Hibernate blockieren — Suspend muss für Power-Taste bleiben
SLEEP_TARGETS=(
  hibernate.target
  hybrid-sleep.target
  suspend-then-hibernate.target
)

is_ac_online() {
  local dir type online status
  for dir in /sys/class/power_supply/*; do
    [[ -d "$dir" ]] || continue
    type="$(cat "$dir/type" 2>/dev/null || true)"
    online="$(cat "$dir/online" 2>/dev/null || true)"
    status="$(cat "$dir/status" 2>/dev/null || true)"
    if [[ "$type" == "Mains" && "$online" == "1" ]]; then
      return 0
    fi
    if [[ "$type" == "USB" && "$online" == "1" ]]; then
      return 0
    fi
    case "$(basename "$dir")" in
      AC|ACAD|ADP*|adp*|USB*)
        [[ "$online" == "1" ]] && return 0
        ;;
    esac
    if [[ "$type" != "Battery" && ( "$status" == "Charging" || "$status" == "Full" ) ]]; then
      return 0
    fi
  done
  return 1
}

write_powerdevil_file() {
  local dest="$1"
  mkdir -p "$(dirname "$dest")"
  printf '%s\n' "$POWERDEVIL_RC_BODY" >"$dest"
}

ensure_configs() {
  mkdir -p "$(dirname "$LOGIND_DROPIN")" "$(dirname "$SLEEP_DROPIN")" "$(dirname "$POWERDEVIL_XDG")"
  cat >"$LOGIND_DROPIN" <<'EOF'
# endeavour-gpo: Idle/Deckel aus; Power-Taste = Suspend; Shutdown nur über Menü
[Login]
IdleAction=ignore
HandleSuspendKey=suspend
HandleHibernateKey=ignore
HandleLidSwitch=ignore
HandleLidSwitchExternalPower=ignore
HandleLidSwitchDocked=ignore
HandlePowerKey=suspend
EOF
  write_powerdevil_file "$POWERDEVIL_XDG"
  local home cfg
  for home in /home/* /home/*/*; do
    [[ -d "$home" ]] || continue
    cfg="$home/.config/powerdevilrc"
    mkdir -p "$home/.config" 2>/dev/null || continue
    write_powerdevil_file "$cfg" 2>/dev/null || true
    chown --reference="$home" "$cfg" 2>/dev/null || true
  done
}

mask_sleep_targets() {
  # Alte zu aggressive Masken (Suspend/sleep) freigeben — inkl. --runtime
  systemctl unmask --runtime sleep.target suspend.target >/dev/null 2>&1 || true
  systemctl unmask sleep.target suspend.target >/dev/null 2>&1 || true
  systemctl mask "${SLEEP_TARGETS[@]}" >/dev/null 2>&1 || true
  mkdir -p "$(dirname "$SLEEP_DROPIN")"
  cat >"$SLEEP_DROPIN" <<'EOF'
[Sleep]
AllowSuspend=yes
AllowHibernation=no
AllowHybridSleep=no
AllowSuspendThenHibernate=no
EOF
  systemctl daemon-reload >/dev/null 2>&1 || true
}

unmask_sleep_targets() {
  systemctl unmask "${SLEEP_TARGETS[@]}" sleep.target suspend.target >/dev/null 2>&1 || true
  rm -f "$SLEEP_DROPIN"
  systemctl daemon-reload >/dev/null 2>&1 || true
}

start_inhibit() {
  ensure_configs
  mask_sleep_targets
  # Alten Inhibit ersetzen (früher blockierte sleep/suspend-key die Power-Taste)
  if [[ -f "$PIDFILE" ]]; then
    kill "$(cat "$PIDFILE")" 2>/dev/null || true
    rm -f "$PIDFILE"
  fi
  pkill -f "systemd-inhibit .*--who=endeavour-gpo" 2>/dev/null || true
  systemd-inhibit --what=idle:handle-lid-switch:handle-hibernate-key \
    --who=endeavour-gpo --why="$WHY" --mode=block \
    /usr/bin/sleep infinity &
  echo $! >"$PIDFILE"
  if command -v powerprofilesctl >/dev/null 2>&1; then
    powerprofilesctl set performance 2>/dev/null || true
  fi
  for uid in $(ls -1 /run/user 2>/dev/null || true); do
    [[ "$uid" =~ ^[0-9]+$ ]] || continue
    sudo -u "#$uid" DBUS_SESSION_BUS_ADDRESS="unix:path=/run/user/$uid/bus" \
      qdbus6 org.kde.Solid.PowerManagement /org/kde/Solid/PowerManagement \
      org.kde.Solid.PowerManagement.reparseConfiguration 2>/dev/null || true
  done
}

stop_inhibit() {
  if [[ -f "$PIDFILE" ]]; then
    kill "$(cat "$PIDFILE")" 2>/dev/null || true
    rm -f "$PIDFILE"
  fi
  pkill -f "systemd-inhibit .*--who=endeavour-gpo" 2>/dev/null || true
  unmask_sleep_targets
}

show_status() {
  echo "ac_online=$(is_ac_online && echo yes || echo no)"
  echo "sleep_dropin=$([[ -f $SLEEP_DROPIN ]] && echo yes || echo no)"
  echo "inhibit_pid=$([[ -f $PIDFILE ]] && cat "$PIDFILE" || echo none)"
  systemctl is-enabled endeavour-gpo-ac-nosleep.service 2>/dev/null || true
  systemctl is-enabled endeavour-gpo-ac-nosleep.timer 2>/dev/null || true
  busctl call org.freedesktop.login1 /org/freedesktop/login1 org.freedesktop.login1.Manager CanSuspend 2>/dev/null || true
  busctl call org.freedesktop.login1 /org/freedesktop/login1 org.freedesktop.login1.Manager CanHibernate 2>/dev/null || true
  for t in sleep.target suspend.target hibernate.target hybrid-sleep.target suspend-then-hibernate.target; do
    echo -n "$t: "
    systemctl is-enabled "$t" 2>/dev/null || echo "?"
  done
  echo -n "PowerButtonAction="
  kreadconfig6 --file powerdevilrc --group AC --group SuspendAndShutdown --key PowerButtonAction 2>/dev/null || true
}

case "${1:-}" in
  on) start_inhibit ;;
  off) stop_inhibit ;;
  sync)
    if is_ac_online; then start_inhibit; else stop_inhibit; fi
    ;;
  status) show_status ;;
  *)
    echo "Usage: $0 on|off|sync|status" >&2
    exit 2
    ;;
esac
