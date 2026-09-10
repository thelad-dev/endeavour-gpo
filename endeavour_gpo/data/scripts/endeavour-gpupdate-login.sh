#!/bin/bash
# Computer-GPO shortly after display-manager / network.
# User drive maps: systemd --user endeavour-gpupdate-session.service
set -euo pipefail
exec /usr/bin/endeavour-gpupdate --force --computer
