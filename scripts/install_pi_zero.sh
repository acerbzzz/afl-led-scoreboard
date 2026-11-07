#!/bin/sh
# Run from /home/pi/afl-led-scoreboard; supports Raspbian Buster without apt.
set -eu
REPO="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
if [ ! -d "$REPO/logos" ]; then
  echo 'ERROR: Required club logos not found; clone the complete repository.' >&2
  exit 1
fi
if [ -e /usr/local/bin/afl ]; then
  echo 'ERROR: /usr/local/bin/afl already exists; refusing to overwrite it.' >&2
  exit 1
fi
printf 'Your email for Squiggle identification: '
IFS= read -r CONTACT
case "$CONTACT" in
  *'@'*.*) ;;
  *) echo 'Please enter a real contact email.' >&2; exit 1 ;;
esac
# Store the identifying email locally, not in the Git repository.
printf '%s\n' "$CONTACT" | sudo sh -c 'umask 077; cat > /etc/afl-led-scoreboard-contact'
# A tiny command with an optional argument to run demo or different mux settings.
sudo tee /usr/local/bin/afl >/dev/null <<EOF
#!/bin/sh
cd "$REPO"
exec sudo /usr/bin/python "$REPO/scripts/pi_zero_legacy.py" "\$@"
EOF
sudo chmod 755 /usr/local/bin/afl
printf '\nInstalled the local AFL launcher. Start with: afl --demo\n'
printf 'For real scores: afl --favorite FRE\n'
