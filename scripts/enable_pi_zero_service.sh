#!/bin/sh
# OPTIONAL, only after the physical LED demo is legible.
set -eu
ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
if [ ! -f /etc/afl-led-scoreboard-contact ]; then
  echo 'ERROR: Run install_pi_zero.sh first; Squiggle contact email missing.' >&2
  exit 1
fi
if [ ! -f "$ROOT/scripts/pi_zero_legacy.py" ]; then
  echo 'ERROR: Pi Zero scoreboard launcher missing.' >&2
  exit 1
fi
if [ -f /etc/systemd/system/afl-led-scoreboard.service ]; then
  echo 'ERROR: Service already exists; not overwriting it.' >&2
  exit 1
fi
printf '%s\n' '[Unit]' 'Description=AFL LED scoreboard (Pi Zero W legacy)' 'Wants=network-online.target' 'After=network-online.target' '' '[Service]' 'Type=simple' 'User=root' "WorkingDirectory=$ROOT" "ExecStart=/usr/bin/python $ROOT/scripts/pi_zero_legacy.py" 'Restart=on-failure' 'RestartSec=30' '' '[Install]' 'WantedBy=multi-user.target' | sudo tee /etc/systemd/system/afl-led-scoreboard.service >/dev/null
sudo systemctl daemon-reload
sudo systemctl enable afl-led-scoreboard.service
printf 'Service enabled, not yet started. Start with: sudo systemctl start afl-led-scoreboard\n'
