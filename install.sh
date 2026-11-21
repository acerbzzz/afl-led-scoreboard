#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
py="${1:-$(command -v python3)}"
[[ "$py" = /* && -x "$py" ]] || { echo 'Pass the absolute Python path from your working scoreboard.'; exit 1; }
"$py" -c 'import sys; assert sys.version_info >= (3,10); from PIL import Image; from rgbmatrix import RGBMatrix'
mapping="${2:-regular}"
slow="${3:-2}"
[[ "$mapping" =~ ^(regular|adafruit-hat|adafruit-hat-pwm)$ && "$slow" =~ ^[0-9]+$ && "$py" != *" "* ]] || exit 2
if [[ ! -f /etc/default/afl-led-scoreboard ]]; then
  read -r -p "Contact email for the Squiggle AFL feed: " email
  [[ "$email" =~ ^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$ ]] || { echo 'Please enter an email address.'; exit 2; }
  printf 'SQUIGGLE_CONTACT_EMAIL=%s\n' "$email" | sudo tee /etc/default/afl-led-scoreboard >/dev/null
  sudo chmod 600 /etc/default/afl-led-scoreboard
fi
sudo install -d /opt/ultimate-scoreboard
sudo cp -r gameguide.py badges badgeart.py afl ufc-led-scoreboard board.py sports.py phone.html /opt/ultimate-scoreboard/
sudo chmod -R a+rX /opt/ultimate-scoreboard
sudo install -d -o daemon -g daemon -m 0750 /var/lib/ultimate-scoreboard
# The matrix binding may drop privileges before the channel workers start.
sudo -u daemon "$py" -c 'from PIL import Image' || { echo 'Use a Python interpreter accessible to daemon, e.g. /usr/bin/python3 with Pillow and rgbmatrix installed.'; exit 1; }
sudo tee /etc/systemd/system/ultimate-scoreboard.service >/dev/null <<EOF
[Unit]
Description=Multi-sport LED scoreboard and Wi-Fi remote
After=network.target
[Service]
EnvironmentFile=/etc/default/afl-led-scoreboard
WorkingDirectory=/opt/ultimate-scoreboard
ExecStart=$py /opt/ultimate-scoreboard/board.py --matrix --data /var/lib/ultimate-scoreboard --mapping $mapping --gpio-slowdown $slow
Restart=on-failure
RestartSec=5
[Install]
WantedBy=multi-user.target
EOF
for old in afl-led-scoreboard ufc-led-scoreboard ufc-scoreboard; do
  if systemctl is-active --quiet "$old" || systemctl is-enabled --quiet "$old" 2>/dev/null; then
    sudo systemctl disable --now "$old"
  fi
done
sudo systemctl daemon-reload
sudo systemctl enable ultimate-scoreboard
sudo systemctl restart ultimate-scoreboard
sleep 2
sudo systemctl is-active --quiet ultimate-scoreboard || { sudo journalctl -u ultimate-scoreboard -n 25 --no-pager; exit 1; }
echo "On the same Wi-Fi, open http://$(hostname).local:8765 on your phone."
hostname -I
