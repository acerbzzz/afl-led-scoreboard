# Original Raspberry Pi Zero W (Rev 1.1) — AFL scoreboard

**Fremantle crest adjustment:** On the 16×16 physical display, the purple shield fill can overpower its white anchor. The legacy Pi renderer now reduces only the interior purple and keeps the outer outline/white anchor visible. This is a targeted colour treatment of the original crest; no club logo files or HD previews are replaced.

**Compact LED logo experiment:** Pi Zero icons now use the main emblem from each bundled 32×32 logo, discarding the tiny printed wordmark before resizing to 16×16. Pale outside pixels are removed and white highlights reduced. Original files are unchanged. Use `afl --demo --brightness 10` to compare on the physical panel. This cannot add detail beyond 16×16 pixels.

**Logo backdrop fix:** The bundled club images contain opaque pale backgrounds. The legacy Pi renderer now strips only light-coloured pixels connected to each image edge, retaining internal white crest artwork and displaying the surrounding area black. Use a low brightness such as `afl --demo --brightness 10` when evaluating the change.

This is an **optional legacy adapter** for the original Pi Zero W running Raspbian Buster (Python 2.7 and Python 3.7). The normal `afl_scoreboard.py` desktop application requires Python 3.10+ and **will not run** on this older Pi. No OS upgrade or `apt-get` is necessary for this adapter if you already have the older NFL scoreboard's Python 2 `rgbmatrix` bindings and Pillow working.

## Hardware first: get a clean image

The visible AFL demo with duplicated rows and a block of lit pixels on the right is **not correctly calibrated**. That is not a Squiggle problem. Verify a separate correctly polarised 5V supply, a shared Pi/panel ground, the panel INPUT and the driver's `regular` GPIO wiring. Shut down/disconnect both devices before moving a jumper wire. Direct 3.3V GPIO signals can be unreliable on some 5V HUB75 panels; a suitable level-shifter/adapter may be required.

Some 64×32 panels use **1:8 multiplexing**, rather than the standard direct scan. With the previously installed C++ demo you can compare, without changing any wires:

```sh
sudo ~/nfl-led-scoreboard/matrix/examples-api-use/demo -D 3 --led-rows=32 --led-cols=64 --led-gpio-mapping=regular --led-multiplexing=1 --led-brightness=20 --led-slowdown-gpio=2
```

Press Ctrl+C to stop. Compare with the same command using `--led-multiplexing=0`. If `1` shows a properly arranged square and `0` repeats rows, the panel needs the stripe-multiplexing setting. If neither is correct, **do not guess at wire swaps**; inspect HUB75 labeling and test power, shared grounds, A/B/C/D address lines, CLK, LAT and OE. Consult [hzeller's wiring instructions](https://github.com/hzeller/rpi-rgb-led-matrix/blob/master/wiring.md) and [matrix parameters](https://github.com/hzeller/rpi-rgb-led-matrix#changing-parameters-via-command-line-flags). Do not assume `--led-multiplexing=1` is correct for every panel.

## Install legacy AFL application on Pi only

```sh
cd ~
git clone --depth 1 https://github.com/acerbzzz/afl-led-scoreboard.git
sh ~/afl-led-scoreboard/scripts/install_pi_zero.sh
```

The installer asks for a real Squiggle contact email. It stores it locally in `/etc/afl-led-scoreboard-contact` (root-only permissions), never commits it to Git, and creates `/usr/local/bin/afl`. It refuses to replace an existing `afl` command. This does not overwrite the old NFL scoreboard folder.

First, run a short, **offline demo**, clearly labelled DEMO and lasting 20 seconds. The native 64×32 layout now gives each team an entire 16-pixel-high row: **a mandatory 16×16 crest**, its abbreviation, goals.behinds and a larger 5×7 total score. This trades the old full-width match header for bigger, more recognisable crests:

```sh
afl --demo --brightness 10
```

If your C++ demo proved that multiplexing 1 works, test the analogous Python parameter:

```sh
afl --demo --multiplexing 1
```

The old Python bindings may not support all C++ matrix parameters; the script reports that explicitly. Keep brightness low initially (default 25%) and ensure correct panel power and wiring.

Once the panel image is readable, display a single actual Squiggle fixture/result for Fremantle:

```sh
afl --once --favorite FRE
```

Rotate all clubs every 15 seconds:

```sh
afl
```

Limit rotation to Fremantle games:

```sh
afl --favorite FRE
```

Control+C stops the continuous scoreboard. The application fetches and caches fixtures approximately every 30 minutes, and listens to Squiggle's server-sent event endpoint when games are in progress. No invented scores; stale cached fixtures are clearly warned about on the terminal when the network fails. It doesn't depend on the HD PNG assets: the included actual legacy logos are mandatory for all clubs.

## Optional startup once hardware works

Only when the screen is stable, run `sh ~/afl-led-scoreboard/scripts/enable_pi_zero_service.sh`. The installer creates and enables a systemd service, but **does not immediately start it**, avoiding a display conflict with your test process. To start it: `sudo systemctl start afl-led-scoreboard`. Check `sudo journalctl -u afl-led-scoreboard -n 30`. Stop and disable with `sudo systemctl disable --now afl-led-scoreboard`.

## Limitations

This adapter is designed for Python 2.7, but its automated tests run on current Python with fake GPIO bindings. The real Pi Zero Python 2 runtime and Squiggle HTTPS connections **need verification on the actual device**. Buster is unsupported and has security limitations. We avoid a risky in-place OS upgrade on the user's only microSD card.
