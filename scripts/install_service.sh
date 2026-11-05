#!/usr/bin/env bash
# Install a boot-start service ON THE RASPBERRY PI, not inside Codespaces.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
if [[ "$(uname -s)" != "Linux" ]] || ! command -v systemctl >/dev/null; then
  echo "Requires a Raspberry Pi running a systemd-based Linux OS." >&2; exit 1
fi
if [[ "$ROOT" == *[[:space:]]* ]]; then
  echo "Move this project to a path without spaces before installing the service." >&2; exit 1
fi
if [[ ! -x "$ROOT/.venv/bin/python" ]]; then
  echo "Create a Python venv and install dependencies at $ROOT/.venv first." >&2; exit 1
fi
if ! "$ROOT/.venv/bin/python" -c 'import rgbmatrix, PIL' 2>/dev/null; then
  echo "Install both Pillow and rpi-rgb-led-matrix in .venv on the Pi first." >&2; exit 1
fi
read -r -p "Squiggle contact email: " email
SQUIGGLE_CONTACT_EMAIL="$email" "$ROOT/.venv/bin/python" -c 'from afl_scoreboard import contact_headers; import os; contact_headers(os.environ["SQUIGGLE_CONTACT_EMAIL"])'
read -r -p "GPIO mapping [regular / adafruit-hat / adafruit-hat-pwm] (regular): " mapping
mapping="${mapping:-regular}"
case "$mapping" in regular|adafruit-hat|adafruit-hat-pwm) ;; *) echo "Invalid GPIO mapping" >&2; exit 1;; esac
service="$(mktemp)"
trap 'rm -f "$service"' EXIT
cat > "$service" <<EOF
[Unit]
Description=AFL Squiggle HUB75 LED scoreboard
Wants=network-online.target
After=network-online.target

[Service]
Type=simple
User=root
WorkingDirectory=$ROOT
EnvironmentFile=/etc/afl-led-scoreboard.env
Environment=AFL_SCOREBOARD_CACHE_DIR=/var/cache/afl-led-scoreboard
ExecStart=$ROOT/.venv/bin/python $ROOT/afl_scoreboard.py --driver matrix --mapping $mapping --rotate-seconds 15 --rotate-limit 6
Restart=on-failure
RestartSec=15

[Install]
WantedBy=multi-user.target
EOF
# The matrix driver needs root access for timing during initialisation. It drops
# privileges afterwards; keep the cache directory writable by the daemon user.
sudo install -d -o daemon -g daemon -m 0750 /var/cache/afl-led-scoreboard
printf 'SQUIGGLE_CONTACT_EMAIL=%s\n' "$email" | sudo tee /etc/afl-led-scoreboard.env >/dev/null
sudo chmod 0600 /etc/afl-led-scoreboard.env
sudo install -m 0644 "$service" /etc/systemd/system/afl-led-scoreboard.service
sudo systemctl daemon-reload
sudo systemctl enable --now afl-led-scoreboard.service
sudo systemctl --no-pager --full status afl-led-scoreboard.service || true
echo 'Service installed. View logs: sudo journalctl -u afl-led-scoreboard -f'
