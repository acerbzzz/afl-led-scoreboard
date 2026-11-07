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

## Goal animation on the LED panel

During a live AFL game, the single existing Squiggle SSE connection reports
`event: score` with `type: goal` and `side: hteam` / `ateam`.
The Pi briefly shows the scoring team's real crest and a flashing GOAL!
message for about 2.2 seconds, then resumes scores and game rotation.
A new goal-count increase is required; startup snapshots, goals in already
finished games, behinds, identical SSE replays and score-only updates cannot
trigger a celebration. Works while rotating all clubs or following
`--favorite FRE` (only games matching the filter).

To test without a live match, use the **clearly simulated** offline animation:

```sh
afl --demo-goal --brightness 10
```

For a pixel-accurate preview without touching GPIO or the Internet:
`afl --demo-goal --preview` writes `pi_zero_goal_preview.png` to the repository.
Real games use `afl --brightness 10 --rotate-seconds 10` and animate on
actual live goal events; `--no-goal-animation` disables this feature.
Squiggle is a third-party score feed, not a guaranteed instantaneous
official stadium clock.

## Optional startup once hardware works

Only when the screen is stable, run `sh ~/afl-led-scoreboard/scripts/enable_pi_zero_service.sh`. The installer creates and enables a systemd service, but **does not immediately start it**, avoiding a display conflict with your test process. To start it: `sudo systemctl start afl-led-scoreboard`. Check `sudo journalctl -u afl-led-scoreboard -n 30`. Stop and disable with `sudo systemctl disable --now afl-led-scoreboard`.

## Limitations

This adapter is designed for Python 2.7, but its automated tests run on current Python with fake GPIO bindings. The real Pi Zero Python 2 runtime and Squiggle HTTPS connections **need verification on the actual device**. Buster is unsupported and has security limitations. We avoid a risky in-place OS upgrade on the user's only microSD card.


## Final siren + real AFL ladder (2026 update)

**FULL TIME:** When Squiggle's SSE `complete` event changes a previously
live game to 100% complete, the Pi flashes FULL TIME with the winning team's
mandatory crest and winning margin for ~3.2 seconds; tied games show DRAW.
It will not celebrate historical matches on startup or replayed events.
Afterwards the normal scoreboard and GOAL animation continue as before.

**Actual standings:** Squiggle `q=standings;year=YYYY` is used, not the
model-prediction `q=ladder` endpoint. Standings are cached for one hour, with
an explicit warning when stale cached data is used after network failure.
Each 64x32 page displays two clubs with their mandatory 16px logos, rank,
premiership points (P), wins (W) and percentage. Nine pages cover all 18
clubs when data is available. Missing or preseason rankings are not invented.

Try both visual upgrades without contacting Squiggle (all scores and ranks
in this test are SIMULATED, and clearly announced):

```sh
git -C ~/afl-led-scoreboard pull --ff-only && afl --demo-upgrades --brightness 10
```

Normal matches and one ladder page every three match screens:

```sh
afl --brightness 10 --rotate-seconds 10 --ladder-every 3
```

Ladder only, cycling through all 18 ranked clubs:

```sh
afl --ladder-only --brightness 10 --rotate-seconds 5
```

The ladder mode is optional; without it, existing scoreboard rotation
continues unchanged. Squiggle contact credentials and real GPIO are only
required for live operation, not the simulated `--demo-upgrades`.


## All 18 clubs on one ladder screen and upcoming matches

The 64x32 ladder now displays **all 18 AFL teams simultaneously**, as
three columns of six rows with their two-digit rank and coloured three-letter
club abbreviation. All standings come from Squiggle `q=standings`; if
the provider hasn't published a complete 18-team ladder, the screen
says LADDER WAIT rather than inventing placements. There is not enough
room for 18 full crests on the same 64x32 panel; **real club logos remain
mandatory on every final score, live match, goal animation and fixture**.

Completed final scores are kept in the automatic rotation alongside upcoming
fixtures. A final-siren celebration leaves the final scores visible briefly
before continuing. Each upcoming fixture shows both team logos, round,
home/away designations, date and local kickoff time; it never displays
made-up scores. The Pi checks the next season's Squiggle fixture when
the current season has no upcoming matches. If the provider has not
published that season, it cannot display unannounced games.

The normal AFL command now inserts a complete ladder screen after
three match or fixture screens:

```sh
afl --brightness 10 --rotate-seconds 10
```

Use `--ladder-only` for the single full ladder; `--ladder-every 0`
for match/fixture rotation without the ladder; `--fixtures-year 2027`
to specify an additional future season.

The offline visual test now displays a simulated final-siren celebration,
all 18 ladder entries, a published-style future fixture screen, and the
final score. Its standings/fixture are deliberately fictional and never
used for real games:

```sh
git -C ~/afl-led-scoreboard pull --ff-only && afl --demo-upgrades --brightness 10
```
