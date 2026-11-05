# AFL LED Scoreboard 🏉

An original Australian-rules scoreboard for a **64×32 HUB75 RGB LED matrix** on a Raspberry Pi, inspired by [mikemountain/nfl-led-scoreboard](https://github.com/mikemountain/nfl-led-scoreboard). Displays club colours, optional existing team BMP logos, goals.behinds (**total points**), quarter/time from Squiggle, and pre-game / final states. Uses the free [Squiggle AFL API](https://api.squiggle.com.au/).

## Features

- 64×32 LED output using [`rpi-rgb-led-matrix`](https://github.com/hzeller/rpi-rgb-led-matrix), plus a **640×320 PNG preview** that works without a Pi.
- All 18 AFL clubs, optional team filter (`--favorite FRE`), Australian Eastern kickoff times, score in `12.8  80` format.
- One-shot fixture lookup via Squiggle REST, **cached 30 minutes**, and a long-lived SSE stream for live updates (no aggressive REST polling).
- Automatic SSE recovery, stale-cache fallback for network trouble, `--demo` mode, and offline unit tests.
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
```

**Season timing:** When no games are scheduled, the preview shows the latest result for the requested season (if one exists). Squiggle provides scores, fixture and approximate match progress; it does not guarantee a second-perfect game clock.

## Raspberry Pi LED matrix

Hardware: Raspberry Pi (Pi Zero 2 W, 3, or 4 recommended), one 64×32 HUB75 panel, suitable 5 V supply, and compatible HAT/Bonnet or wiring. Follow the wiring and install instructions for [hzeller/rpi-rgb-led-matrix](https://github.com/hzeller/rpi-rgb-led-matrix); that driver is **not** installed automatically by `pip` on your computer.

```bash
sudo -E .venv/bin/python afl_scoreboard.py --driver matrix --year 2026 --mapping adafruit-hat --brightness 55 --gpio-slowdown 2
```

Use `--mapping regular` if wired directly; board-specific electrical settings matter. Avoid running as root unnecessarily except when your matrix binding requires it. Set `SQUIGGLE_CONTACT_EMAIL` before launching. Change `--year` for future seasons; the default is the current Australian year.

## Tests

```bash
python -m unittest discover -s tests -v
```

## Data-provider responsibility

Squiggle is free, but it asks users to identify their bot via an email-bearing User-Agent, cache REST data, avoid parallel requests, and use the [event API](https://sse.squiggle.com.au/) for live updates. This program is designed around those rules. It is not affiliated with the AFL, Squiggle, or the NFL scoreboard author.

## Credits & licensing

Inspired by the LED scoreboard concept of [mikemountain/nfl-led-scoreboard](https://github.com/mikemountain/nfl-led-scoreboard) (GPL-3.0); rewritten for AFL rather than copying the NFL application. Existing `logos/*.bmp` were carried forward from this project's earlier repository state. Their rights may differ; verify before redistribution.
