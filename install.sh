#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
py="${1:-$(command -v python3)}"
mapping="${2:-regular}"
slow="${3:-2}"
[[ "$py" = /* && -x "$py" && "$py" != *' '* ]] || { echo 'Pass an absolute Python 3 path.'; exit 1; }
[[ "$mapping" =~ ^(regular|adafruit-hat|adafruit-hat-pwm)$ && "$slow" =~ ^[0-9]+$ ]] || exit 2
# No changes to system Python, Pillow, GPIO wiring or the installed LED binding.
"$py" - <<'PY'
import sys
if sys.version_info < (3, 7):
    sys.exit('Python 3.7 or newer is needed; found ' + sys.version.split()[0])
from PIL import Image, ImageDraw
im = Image.new('RGB', (64, 32))
ImageDraw.Draw(im).rectangle((0, 0, 1, 1), fill='white')
im.tobytes()
print('Python and Pillow ready')
PY
sudo -v
if ! timeout 30 sudo systemctl show --property=Version >/dev/null; then
  echo 'System service manager is not responding. Reboot the Pi, then run this installer again.'
  exit 1
fi
legacy=''
if ! "$py" -c 'from rgbmatrix import RGBMatrix, RGBMatrixOptions' 2>/dev/null; then
  legacy="$(command -v python2 || true)"
  [[ -n "$legacy" ]] && sudo "$legacy" -c 'from rgbmatrix import RGBMatrix, RGBMatrixOptions; from PIL import Image; Image.frombytes("RGB", (1,1), b"\0\0\0")' || {
    echo 'Could not find your working LED driver in Python 3 or Python 2. No services have been changed.'; exit 1;
  }
  echo "Using your existing legacy LED driver: $legacy"
fi
# Private, pure-Python timezone dependency for Buster; never upgrade system packages.
deps="$PWD/.install-deps"
mkdir -p "$deps"
export PYTHONPATH="$deps${PYTHONPATH:+:$PYTHONPATH}"
if ! "$py" -c 'import zoneinfo' 2>/dev/null && ! "$py" -c 'from dateutil.tz import gettz; assert gettz("Australia/Melbourne")' 2>/dev/null; then
  "$py" - <<'PY'
import hashlib, io, json, os, zipfile
from urllib.request import urlopen
# Install pure Python wheels without requiring pip or changing OS packages.
for name, version in [('six', '1.17.0'), ('python-dateutil', '2.9.0.post0')]:
    with urlopen('https://pypi.org/pypi/%s/%s/json' % (name, version), timeout=30) as response:
        metadata = json.load(response)
    item = next(x for x in metadata['urls'] if x['filename'].endswith('py2.py3-none-any.whl'))
    with urlopen(item['url'], timeout=60) as response:
        data = response.read()
    assert hashlib.sha256(data).hexdigest() == item['digests']['sha256'], 'Dependency checksum failed'
    with zipfile.ZipFile(io.BytesIO(data)) as wheel:
        for member in wheel.namelist():
            if member.startswith('/') or '..' in member.split('/'):
                raise ValueError('Invalid dependency path')
        wheel.extractall('.install-deps')
PY
fi
"$py" -c 'import board; import sys; sys.path.insert(0,"afl"); from afl_scoreboard import ZoneInfo; print("Scoreboard imports ready:", ZoneInfo("Australia/Melbourne"))'
# Check every channel before stopping the existing display.
"$py" selfcheck.py
sudo -u daemon "$py" -c 'from PIL import Image' || { echo 'Python/Pillow must be accessible to the daemon user.'; exit 1; }
if [[ ! -f /etc/default/afl-led-scoreboard ]]; then
  read -r -p 'Contact email for the Squiggle AFL feed: ' email
  [[ "$email" =~ ^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$ ]] || { echo 'Please enter an email address.'; exit 2; }
  printf 'SQUIGGLE_CONTACT_EMAIL=%s\n' "$email" | sudo tee /etc/default/afl-led-scoreboard >/dev/null
  sudo chmod 600 /etc/default/afl-led-scoreboard
fi
backup="/var/backups/ultimate-scoreboard/$(date +%Y%m%d-%H%M%S)"
sudo mkdir -p "$backup"
[[ ! -d /opt/ultimate-scoreboard ]] || sudo cp -a /opt/ultimate-scoreboard "$backup/app"
[[ ! -f /etc/systemd/system/ultimate-scoreboard.service ]] || sudo cp -a /etc/systemd/system/ultimate-scoreboard.service "$backup/service"
[[ ! -d /var/lib/ultimate-scoreboard ]] || sudo cp -a /var/lib/ultimate-scoreboard "$backup/data"
active=()
enabled=()
for old in ultimate-scoreboard afl-led-scoreboard ufc-led-scoreboard ufc-scoreboard; do
  if systemctl is-enabled --quiet "$old" 2>/dev/null; then enabled+=("$old"); fi
  if systemctl is-active --quiet "$old"; then active+=("$old"); fi
done
rollback() {
  trap - ERR
  set +e
  echo "Install did not complete. Restoring the previous service. Backup: $backup"
  sudo journalctl -u ultimate-scoreboard -n 35 --no-pager
  sudo systemctl disable --now ultimate-scoreboard
  if [[ -d "$backup/app" ]]; then sudo cp -a "$backup/app/." /opt/ultimate-scoreboard/; fi
  if [[ -f "$backup/service" ]]; then
    sudo cp -a "$backup/service" /etc/systemd/system/ultimate-scoreboard.service
  else
    sudo rm -f /etc/systemd/system/ultimate-scoreboard.service
  fi
  sudo systemctl daemon-reload
  for old in "${enabled[@]}"; do sudo systemctl enable "$old"; done
  for old in "${active[@]}"; do sudo systemctl start "$old"; done
  exit 1
}
trap rollback ERR
for old in "${active[@]}"; do sudo systemctl stop "$old"; done
sudo install -d /opt/ultimate-scoreboard/dependencies
sudo cp -r gameguide.py ledlayout.py badges badgeart.py afl ufc-led-scoreboard board.py matrix_driver.py matrix_bridge.py sports.py phone.html /opt/ultimate-scoreboard/
sudo cp -r "$deps/." /opt/ultimate-scoreboard/dependencies/
sudo chmod -R a+rX /opt/ultimate-scoreboard
sudo install -d -o daemon -g daemon -m 0750 /var/lib/ultimate-scoreboard
sudo chown -R daemon:daemon /var/lib/ultimate-scoreboard
sudo tee /etc/systemd/system/ultimate-scoreboard.service >/dev/null <<EOF
[Unit]
Description=Multi-sport LED scoreboard and Wi-Fi remote
After=network.target
[Service]
EnvironmentFile=/etc/default/afl-led-scoreboard
Environment=PYTHONPATH=/opt/ultimate-scoreboard/dependencies
Environment=BOARD_LEGACY_PYTHON=$legacy
Environment=PYTHONUNBUFFERED=1
WorkingDirectory=/opt/ultimate-scoreboard
ExecStart=$py /opt/ultimate-scoreboard/board.py --matrix --data /var/lib/ultimate-scoreboard --mapping $mapping --gpio-slowdown $slow
Restart=on-failure
RestartSec=5
TimeoutStopSec=15
[Install]
WantedBy=multi-user.target
EOF
sudo systemctl daemon-reload
sudo systemctl start ultimate-scoreboard
"$py" - <<'PY'
import json, time
from urllib.request import urlopen
for attempt in range(180):
    try:
        with urlopen('http://127.0.0.1:8765/api', timeout=1) as response:
            result = json.load(response)
        if result.get('ready'):
            with urlopen('http://127.0.0.1:8765/panel.png', timeout=1) as frame:
                assert frame.read(8) == b'\x89PNG\r\n\x1a\n'
            print('Phone remote and display loop are responding.')
            break
    except (OSError, ValueError, AssertionError):
        pass
    time.sleep(1)
else:
    raise SystemExit('Scoreboard did not become ready within 180 seconds (including TV delay).')
PY
sudo systemctl is-active --quiet ultimate-scoreboard
sudo systemctl enable ultimate-scoreboard
for old in "${enabled[@]}"; do
  [[ "$old" == ultimate-scoreboard ]] || sudo systemctl disable "$old"
done
trap - ERR
echo "Installed. Automatic startup is enabled. Previous setup saved at $backup"
echo "iPhone (same Wi-Fi): http://$(hostname).local:8765"
for ip in $(hostname -I); do echo "Alternative: http://$ip:8765"; done
