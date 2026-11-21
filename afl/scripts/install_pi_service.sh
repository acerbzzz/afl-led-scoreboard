#!/usr/bin/env bash
# Run this on a physical Raspberry Pi after installing the rgbmatrix Python bindings.
set -euo pipefail

if [[ "${1:-}" == "--help" ]]; then
  printf '%s\n' 'Usage: bash scripts/install_pi_service.sh [regular|adafruit-hat|adafruit-hat-pwm]' \
    'Run on Raspberry Pi with a connected 64x32 HUB75 panel.' \
    'Installs an auto-starting systemd service and a root-readable contact-email env file.'
  exit 0
fi
if [[ ! -r /proc/device-tree/model ]] || ! grep -aq 'Raspberry Pi' /proc/device-tree/model; then
  echo 'This installer runs only on a Raspberry Pi, not Codespaces or a laptop.' >&2
  exit 1
fi

mapping="${1:-adafruit-hat}"
case "$mapping" in
  regular|adafruit-hat|adafruit-hat-pwm) ;;
  *) echo 'Invalid mapping. Choose regular, adafruit-hat, or adafruit-hat-pwm.' >&2; exit 2 ;;
esac

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
if [[ "$root" =~ [[:space:]] ]]; then
  echo 'Please keep this project in a directory with no spaces for systemd.' >&2
  exit 2
fi
python="$root/.venv/bin/python"
if [[ ! -x "$python" ]]; then
  echo "Missing $python; create .venv and install Pillow and rgbmatrix first." >&2
  exit 2
fi
if ! "$python" -c 'from PIL import Image; from rgbmatrix import RGBMatrix' >/dev/null 2>&1; then
  echo 'Pillow or the Raspberry Pi rgbmatrix bindings are not installed in .venv.' >&2
  exit 2
fi

read -r -p 'Squiggle contact email (will NOT be added to GitHub): ' email
if [[ ! "$email" =~ ^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$ ]]; then
  echo 'Enter a valid contact email.' >&2
  exit 2
fi

# The rgbmatrix library normally drops root to daemon at initialization. The
# post-drop user must still be able to update the Squiggle REST cache.
sudo install -d -m 0750 -o daemon -g daemon /var/cache/afl-led-scoreboard
email_tmp="$(mktemp)"
service_tmp="$(mktemp)"
trap 'rm -f "$email_tmp" "$service_tmp"' EXIT
printf 'SQUIGGLE_CONTACT_EMAIL=%s\n' "$email" > "$email_tmp"
sudo install -m 0600 -o root -g root "$email_tmp" /etc/default/afl-led-scoreboard
cat > "$service_tmp" <<EOF
[Unit]
Description=AFL LED Scoreboard (Squiggle live AFL scores)
Wants=network-online.target
After=network-online.target

[Service]
Type=simple
User=root
WorkingDirectory=$root
EnvironmentFile=/etc/default/afl-led-scoreboard
ExecStart=$python $root/afl_scoreboard.py --driver matrix --mapping $mapping --cache-dir /var/cache/afl-led-scoreboard --rotate-seconds 15 --rotate-limit 6
Restart=on-failure
RestartSec=20
TimeoutStopSec=10

[Install]
WantedBy=multi-user.target
EOF
sudo install -m 0644 -o root -g root "$service_tmp" /etc/systemd/system/afl-led-scoreboard.service
sudo systemctl daemon-reload
sudo systemctl enable --now afl-led-scoreboard.service
printf '\nInstalled. Check with: sudo systemctl status afl-led-scoreboard --no-pager\n'
printf 'Follow logs with: sudo journalctl -u afl-led-scoreboard -f\n'
