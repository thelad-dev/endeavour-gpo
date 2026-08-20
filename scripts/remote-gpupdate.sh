#!/bin/bash
# Trigger endeavour-gpupdate on a domain client (from DC / admin workstation).
# Usage: endeavour-gpupdate-remote [user@]host
# Example: endeavour-gpupdate-remote nb64
#          endeavour-gpupdate-remote ladwein@nb64.dentaldimension.local
set -euo pipefail
HOST="${1:?Usage: $0 [user@]host}"
shift || true
ssh -o BatchMode=yes "$HOST" "sudo systemctl start endeavour-gpupdate.service && echo OK"
