# AFL LED Scoreboard 🏉

An original Australian-rules scoreboard for a **64×32 HUB75 RGB LED matrix** on a Raspberry Pi, inspired by [mikemountain/nfl-led-scoreboard](https://github.com/mikemountain/nfl-led-scoreboard). Displays club colours, optional existing team BMP logos, goals.behinds (**total points**), quarter/time from Squiggle, and pre-game / final states. Uses the free [Squiggle AFL API](https://api.squiggle.com.au/).

## Features

- 64×32 LED output using [`rpi-rgb-led-matrix`](https://github.com/hzeller/rpi-rgb-led-matrix), plus a **640×320 PNG preview** that works without a Pi.
- All 18 AFL clubs, optional team filter (`--favorite FRE`), Australian Eastern kickoff times, score in `12.8  80` format.
- One-shot fixture lookup via Squiggle REST, **cached 30 minutes**, and a long-lived SSE stream for live updates (no aggressive REST polling).
- **Automatic match rotation**: cycle through up to six relevant games every 15 seconds without extra REST requests; one SSE connection covers active matches.
- Automatic SSE recovery, stale-cache fallback for network trouble, `--demo` mode, and offline unit tests.
- Compact colour-coded `FINAL`, `LIVE`, quarter/half-time labels and Australian-local fixture times.
- Raspberry Pi RGB diagnostics (`--hardware-test`) and optional systemd boot-start installer.
- **No API key or paid service** required. Squiggle does require an identifying `User-Agent` containing your own contact email.

## Quick preview (Windows/macOS/Linux/PC)

```bash
python3 -m venv .venv
source .venv/bin/activate           # Windows: .venv\\Scripts\\activate
python -m pip install -r requirements.txt
python afl_scoreboard.py --demo
# open preview.png
```

## Real Squiggle scores

Set **your own contact email**; this is required by the free API and must not be a made-up address. Set it in the terminal environment (do not commit it):

```bash
export SQUIGGLE_CONTACT_EMAIL='you@your-domain.com'
python afl_scoreboard.py --once --year 2026 --favorite FRE
```

For a long-running scoreboard (use SSE while an AFL match is live):

```bash
python afl_scoreboard.py --year 2026 --favorite FRE
# To rotate all clubs instead, omit --favorite:
python afl_scoreboard.py --year 2026 --rotate-seconds 10 --rotate-limit 6
```

**Rotation:** The most relevant games are ranked live first, followed by upcoming fixtures and recently completed games. `--favorite FRE` limits the rotation to Fremantle matches. `--once` renders just the first selected game.  `Ctrl+C` stops rotation. The preview image is overwritten each cycle; open or reload it to view the current frame.

**Season timing:** When no games are scheduled, the preview shows the latest result for the requested season (if one exists). Squiggle provides scores, fixture and approximate match progress; it does not guarantee a second-perfect game clock.

## Raspberry Pi LED matrix

Hardware: Raspberry Pi (Pi Zero 2 W, 3, or 4 recommended), one 64×32 HUB75 panel, suitable 5 V supply, and compatible HAT/Bonnet or wiring. Follow the wiring and install instructions for [hzeller/rpi-rgb-led-matrix](https://github.com/hzeller/rpi-rgb-led-matrix); that driver is **not** installed automatically by `pip` on your computer.

```bash
sudo -E .venv/bin/python afl_scoreboard.py --driver matrix --year 2026 --mapping adafruit-hat --brightness 55 --gpio-slowdown 2
```

Use `--mapping regular` if wired directly; board-specific electrical settings matter. Avoid running as root unnecessarily except when your matrix binding requires it. Set `SQUIGGLE_CONTACT_EMAIL` before launching. Change `--year` for future seasons; the default is the current Australian year.

## Hardware check and start on boot (run on the Raspberry Pi only)

**Codespaces can render preview PNGs but cannot drive physical GPIO pins.** On a Pi with a 64×32 HUB75 panel, suitable HAT and **separate 5V panel power**:

```bash
sudo apt-get update
sudo apt-get install -y python3-dev cython3 cmake git
python3 -m venv --system-site-packages .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m pip install 'git+https://github.com/hzeller/rpi-rgb-led-matrix'
# Confirm the actual mapping for your wiring; 'regular' is only a starting point.
sudo .venv/bin/python afl_scoreboard.py --driver matrix --hardware-test --mapping regular
# Only after verifying the LEDs work:
bash scripts/install_service.sh
```

The test displays red/green/blue diagnostic frames followed by an AFL demo; the hardware wiring and electrical safety must be verified on your actual panel. A **mocked matrix** is covered by offline tests, but that is not a physical LED test. The installer asks for your contact email and mapping, writes an environment file with limited permissions under `/etc`, installs `afl-led-scoreboard.service`, and starts it at boot. It is **not** intended to run inside Codespaces. Logs: `sudo journalctl -u afl-led-scoreboard -f`. Disable: `sudo systemctl disable --now afl-led-scoreboard.service`.

The driver may need initial root privileges for precise GPIO timing and normally drops privileges afterwards. See [upstream hardware instructions](https://github.com/hzeller/rpi-rgb-led-matrix). Raspberry Pi 5 is not listed as officially supported by the upstream driver; Pi Zero 2 W, Pi 3 and Pi 4 are more predictable choices.

## Tests

```bash
python -m unittest discover -s tests -v
```

## Data-provider responsibility

Squiggle is free, but it asks users to identify their bot via an email-bearing User-Agent, cache REST data, avoid parallel requests, and use the [event API](https://sse.squiggle.com.au/) for live updates. This program is designed around those rules. It is not affiliated with the AFL, Squiggle, or the NFL scoreboard author.

## Credits & licensing

Inspired by the LED scoreboard concept of [mikemountain/nfl-led-scoreboard](https://github.com/mikemountain/nfl-led-scoreboard) (GPL-3.0); rewritten for AFL rather than copying the NFL application. Existing `logos/*.bmp` were carried forward from this project's earlier repository state. Their rights may differ; verify before redistribution.
