# Ultimate Pi Scoreboard

One 64×32 HUB75 panel, one Pi and an iPhone remote. The controller starts in AFL Demo so you can check the LEDs immediately. In Safari choose a channel, then Feed for provider scores. Add the remote to your Home Screen from the Share menu. The Pi remembers the last channel, source, manual card and brightness after reboot.

## Install on the Pi

On the Pi, clone the multi-sport branch into your home directory.

```bash
git clone --depth 1 --single-branch --branch ultimate-scoreboard https://github.com/acerbzzz/afl-led-scoreboard.git ~/ultimate-scoreboard
cd ~/ultimate-scoreboard
```

1. Use Raspberry Pi OS with Python 3.7+, Pillow 5.4+ and your existing hzeller rgbmatrix bindings. Raspbian Buster is supported; keep the existing OS and wiring.
2. Run `bash install.sh`. It automatically uses the installed Python 2 LED binding when Python 3 has no binding. If you already have a working Python 3 environment, pass that Python instead, e.g. `bash install.sh /opt/scoreboard-venv/bin/python regular 2`. The interpreter must be executable by the daemon user. Use your working mapping and slowdown values. Direct GPIO defaults to regular and 2, matching the original setup. New settings start at 20% brightness.
3. The installer reuses the AFL email configuration or prompts for the contact address used with Squiggle. It switches off detected standalone AFL/UFC services so one process drives the panel, then enables the combined service at boot after checking the phone API and rendered frame. It backs up the installed app, service and settings under `/var/backups/ultimate-scoreboard/` and restores the previous service on startup failure. Stop any manually launched board or differently named display service before starting.
4. On the same trusted Wi-Fi, open the address printed by the installer. If the hostname fails, use the printed Pi LAN address and port 8765. Anyone on that LAN can control the panel. Keep it local.

For subsequent updates, run this from the Pi. Settings and favourites live outside the checkout. If you made local troubleshooting edits, preserve them with `git stash push -u -m "Before scoreboard repair"` before pulling.

```bash
cd ~/ultimate-scoreboard && git pull --ff-only && bash install.sh
```

## Watching

AFL uses the existing Squiggle rotation and club logos. UFC uses the existing fight feed, introduction portraits and finish animations. Live fight names now occupy the full panel width. The final card shows the winner and method together. UFC Results cycles completed bouts from the latest completed card found in the past 28 days, including when the main feed has switched to the next event. METHOD PENDING means the provider has yet to supply the method. Decision types use DEC UD, DEC SD and DEC MD. The clock reflects provider updates.

Cricket follows Australian national sides and selected domestic competitions when listed in ESPN's cricket header. NRL uses the NRL draw. NFL, MLB, NBA and Australian NBL use ESPN scoreboards. Two-team feeds rotate matches every twenty seconds and refresh about once a minute. Provider coverage varies. OFFLINE marks a failed refresh and NO MATCH means the source returned no matching fixtures. Demo uses labelled sample scores. Manual accepts names, scores and status details from the phone, including overs or a bout result.

## Preview and troubleshoot

Run `python3 board.py` with Pillow installed (also python-dateutil on Python 3.7/3.8) to preview without GPIO, then open http://localhost:8765. For service diagnostics use `sudo journalctl -u ultimate-scoreboard -n 40 --no-pager`. If the panel is already occupied, check `systemctl list-units --type=service | grep -Ei 'score|matrix'`. To return to a previous setup run `sudo systemctl disable --now ultimate-scoreboard` then enable the standalone service you previously used, e.g. `sudo systemctl enable --now afl-led-scoreboard`.

## Team artwork

NFL, MLB, NBA, NBL, cricket and NRL show an emblem beside each side. AFL uses updated club crests. UFC displays its promotion mark on introductions, live fights, celebrations and results. Bundled images work offline. Cricket uses country flags and can also load additional team artwork supplied by its ESPN feed. A team without artwork gets an initialled badge. Sources: ESPN team and league artwork, FootyLogos NRL club marks.

## Watching one game

In Games, select a channel and source, then choose **Watch this game** to pin a fixture or fight. Use the stars to prioritise your teams on that channel. Now showing mirrors the physical panel, including TV delay. Unpin to resume rotation. Pins, favourites, night hours and delay survive a reboot. Once a pinned frame has appeared it is saved for recovery, including the final result. Selecting a different channel or source releases the pin.

Settings offers a 0–120 second TV delay and a night brightness cap using the Pi's local clock. Equal start and end hours disable the cap. After changing channel, pin or delay the buffer fills again. Connection shows the Pi link separately from the last provider update. Provider coverage and pace determine when a score, finish method, down and distance, or base occupancy becomes available. Sport-specific details rotate every four seconds while team logos and scores stay in place. Only the selected channel polls its feed.

College Football follows ESPN’s NCAA Division I FBS slate, including unranked teams. Select Games → College Football → Feed to choose a matchup. The offline demo features Ohio State and Michigan. Live games use team logos from ESPN when available.

## Compatibility and checks

The Python 2 process only owns the original LED driver and accepts raw frames from the Python 3 app. It has no web server or feed code. A stalled driver exits so systemd can restart the board. The installer adds only private, checksum-verified timezone dependencies when needed; it does not upgrade Python, Pillow or the LED binding. Pillow before 8 uses a bitmap-font fallback for desktop HD previews; the physical 64x32 design is unchanged.

Run `python3 selfcheck.py` for offline render checks. Automated tests:

```bash
PYTHONPATH=afl python3 -m unittest discover -s afl/tests
PYTHONPATH=ufc-led-scoreboard python3 -m unittest discover -s ufc-led-scoreboard -p 'test*.py'
PYTHONPATH=afl:ufc-led-scoreboard python3 -m unittest test_channels test_runtime
```

The runtime tests exercise the legacy pipe with a mock matrix, all phone demo channels, saved selection after restart and recovery from interrupted settings. Physical GPIO, live provider availability and boot on a particular Pi still require an on-device check.

## Clear panel layout

AFL keeps its original layout. Other team sports use two separate team rows: a real crest, team abbreviation and large score, followed by one native-pixel status line. Logos are cropped using transparency and given a subdued edge for visibility on black. Scores and crests stay fixed while information pages rotate; text is never horizontally squeezed to fit. A score too long for its cell shows `--`; the phone retains its full value.

| Sport | Panel information when supplied by the feed |
| --- | --- |
| NFL / college football | Quarter, clock, possession marker, down and distance, field position, timeouts |
| MLB | Inning/half, balls-strikes count, outs, occupied-base diamonds |
| NBA / NBL | Quarter, clock, shot clock, team fouls, timeouts |
| Cricket | Runs/wickets, batting-side marker, overs, target, match summary/result |
| NRL | Score, match state, provider clock when present |
| UFC | Fighter names, round/time; final winner and method stay visible while finish time/judge cards rotate in the header |

This is a compact broadcast-style presentation, not a TV data subscription. Missing fields are omitted; the app does not invent a running clock or guess possession. ESPN often omits shot clocks, fouls or timeouts, and NRL can reject requests (HTTP 403). The phone retains longer summaries. Demo data is explicitly labelled and does not indicate a live match.

### UFC fighter portraits

Live bouts show both real fighter photos, corner-coloured names, round and clock. Completed bouts with a known winner show a larger winner portrait, winner name and finish method. SUB means submission, DQ disqualification, and NC no contest; the phone keeps the full method. Finish timing and available judge cards rotate in the header. Names paginate at native pixel size rather than being squeezed. Missing photos use a name fallback. ESPN headshots load in the background so a slow image request cannot stall the score display. Successful portraits are saved under the scoreboard data directory and reused after reboot, including offline. Failed downloads retry after five minutes; demo portraits work offline.

## Formula 1

Select **F1** in the phone remote, then Feed or Demo. The LED leaderboard shows three drivers at a time and cycles through the field. Choose **Watch driver** to hold one driver, with name, position, constructor and available timing details. The F1 logo is bundled for offline use; constructor identity is shown with its supplied name and team colour.

The channel polls ESPN's F1 scoreboard every 30 seconds, selects a live session first, otherwise the latest completed session or an upcoming session. Practice, qualifying, sprint and race sessions are supported. Only race/sprint periods are shown as lap counts. Upcoming entry-list order is never presented as grid position. Background requests fetch constructor and timing metadata for visible drivers; missing gaps, tyre data and other unavailable telemetry are not guessed. This is a public scoreboard feed, not an official real-time timing subscription. Driver metadata refreshes at most every two minutes. All demo timings are illustrative.

F1 uses the same brightness, TV delay, offline status and saved selection controls as other channels. The manual mode remains a generic manually entered score card. ESPN artwork is used for the F1 logo.
