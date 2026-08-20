#!/bin/bash
# Refresh GPO for every active session shortly after graphical login / boot.
set -euo pipefail
sleep 15
exec /usr/bin/endeavour-gpupdate --force --all-sessions
