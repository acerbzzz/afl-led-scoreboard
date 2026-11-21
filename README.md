# Ultimate Pi Scoreboard

One 64×32 HUB75 panel, one Pi and an iPhone remote. The controller starts in AFL Demo so you can check the LEDs immediately. In Safari choose a channel, then Feed for provider scores. Add the remote to your Home Screen from the Share menu. The Pi remembers the last channel, source, manual card and brightness after reboot.

## Install on the Pi

On the Pi, clone the multi-sport branch into your home directory.

```bash
git clone --depth 1 --single-branch --branch ultimate-scoreboard https://github.com/acerbzzz/afl-led-scoreboard.git ~/ultimate-scoreboard
cd ~/ultimate-scoreboard
```

1. Use Raspberry Pi OS with Python 3.9+, Pillow 8.2+ and your existing hzeller rgbmatrix Python bindings.
2. Run `bash install.sh`. If the binding lives in your previous scoreboard environment, pass that Python instead, e.g. `bash install.sh /opt/scoreboard-venv/bin/python regular 2`. The interpreter must be executable by the daemon user. Use your working mapping and slowdown values. Direct GPIO defaults to regular and 2.
3. The installer reuses the AFL email configuration or prompts for the contact address used with Squiggle. It switches off detected standalone AFL/UFC services so one process drives the panel, then enables the combined service at boot. Stop any manually launched board or differently named display service before starting.
4. On the same trusted Wi-Fi, open the address printed by the installer. If the hostname fails, use the printed Pi LAN address and port 8765. Anyone on that LAN can control the panel. Keep it local.

For subsequent updates, run this from the Pi. Settings and favourites live outside the checkout.

```bash
cd ~/ultimate-scoreboard && git pull --ff-only && bash install.sh
```

## Watching

AFL uses the existing Squiggle rotation and club logos. UFC uses the existing fight feed, introduction portraits and finish animations. Live fight names now occupy the full panel width. The final card shows the winner and method together. UFC Results cycles completed bouts from the latest completed card found in the past 28 days, including when the main feed has switched to the next event. METHOD PENDING means the provider has yet to supply the method. Decision types use DEC UD, DEC SD and DEC MD. The clock reflects provider updates.

Cricket follows Australian national sides and selected domestic competitions when listed in ESPN's cricket header. NRL uses the NRL draw. NFL, MLB, NBA and Australian NBL use ESPN scoreboards. Two-team feeds rotate matches every ten seconds and refresh about once a minute. Provider coverage varies. OFFLINE marks a failed refresh and NO MATCH means the source returned no matching fixtures. Demo uses labelled sample scores. Manual accepts names, scores and status details from the phone, including overs or a bout result.

## Preview and troubleshoot

Run `python3 board.py` with Pillow installed to preview without GPIO, then open http://localhost:8765. For service diagnostics use `sudo journalctl -u ultimate-scoreboard -n 40 --no-pager`. If the panel is already occupied, check `systemctl list-units --type=service | grep -Ei 'score|matrix'`. To return to a previous setup run `sudo systemctl disable --now ultimate-scoreboard` then enable the standalone service you previously used, e.g. `sudo systemctl enable --now afl-led-scoreboard`.

## Team artwork

NFL, MLB, NBA, NBL, cricket and NRL show an emblem beside each side. AFL uses updated club crests. UFC displays its promotion mark on introductions, live fights, celebrations and results. Bundled images work offline. Cricket uses country flags and can also load additional team artwork supplied by its ESPN feed. A team without artwork gets an initialled badge. Sources: ESPN team and league artwork, FootyLogos NRL club marks.

## Watching one game

In Games, select a channel and source, then choose **Watch this game** to pin a fixture or fight. Use the stars to prioritise your teams on that channel. Now showing mirrors the physical panel, including TV delay. Unpin to resume rotation. Pins, favourites, night hours and delay survive a reboot. Once a pinned frame has appeared it is saved for recovery, including the final result. Selecting a different channel or source releases the pin.

Settings offers a 0–120 second TV delay and a night brightness cap using the Pi's local clock. Equal start and end hours disable the cap. After changing channel, pin or delay the buffer fills again. Connection shows the Pi link separately from the last provider update. Provider coverage and pace determine when a score, finish method, down and distance, or base occupancy becomes available. NFL and MLB alternate available situation details with the clock or inning. Only the selected channel polls its feed.

College Football follows ESPN’s NCAA Division I FBS slate, including unranked teams. Select Games → College Football → Feed to choose a matchup. The offline demo features Ohio State and Michigan. Live games use team logos from ESPN when available.
