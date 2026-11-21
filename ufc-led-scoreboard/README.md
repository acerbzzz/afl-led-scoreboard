# UFC LED Scoreboard

A fight-card display for one 64×32 HUB75 panel, designed for the same Raspberry Pi Zero W and direct GPIO wiring as the AFL LED scoreboard. Each frame shows the event, two fighters, and the bout status. The two row colors distinguish opponents. Green text and a W identify the reported winner.

## Try the offline demo on your Pi

From this folder, use the Python interpreter that already runs your AFL scoreboard. Stop the AFL display before either app drives the same panel. If your working interpreter is in a virtual environment, substitute its full path for python3 in both commands.

```bash
python3 -m unittest -v && sudo python3 scoreboard.py --demo --driver matrix
```

Press Ctrl+C to clear the panel. Start the live UFC feed with:

```bash
sudo python3 scoreboard.py --driver matrix
```

The defaults are direct GPIO mapping (regular), brightness 50, and GPIO slowdown 1. Match your AFL command with --mapping, --brightness and --gpio-slowdown if you customized those settings.

## Desktop preview

Requires Python 3.8+ and Pillow 9.1+. Install Pillow in your Python environment with `python3 -m pip install -r requirements.txt`. Run `python3 scoreboard.py --demo --once` to write a 640×320 pixel-scaled preview.png. Leave off --once to cycle through fictional scheduled, live and final examples. Only the matrix mode requires the Raspberry Pi rgbmatrix Python binding from https://github.com/hzeller/rpi-rgb-led-matrix.

## Fight data

The app polls ESPN's public UFC scoreboard roughly every 30 seconds. While a bout is live it takes priority. Between live bouts, the panel rotates through the returned card every eight seconds. The clock displays the last provider update. Finals without an explicit winner have no winner marker. When a request fails, the last in-memory card stays visible with FEED OFFLINE until a later poll succeeds. With an empty feed it shows NO CARD.

Data endpoint: https://site.api.espn.com/apis/site/v2/sports/mma/ufc/scoreboard

## Fighter introductions
Scheduled bouts rotate through two introduction frames, one per fighter, with a 30×30 face crop beside their surname. Live bouts immediately take priority at the next feed refresh. If a photo is unavailable the regular two-name frame appears. The app reuses up to 128 headshots in memory. The offline demo includes miniature ESPN portraits of André Muniz and Arnold Allen in an illustrative pairing. Photos are credited to ESPN and their respective rights holders.

## Live fight and result display
Both corners stay on screen during the fight and its finish. The middle column shows the provider's round and clock. When ESPN supplies judges' cards, the bottom row cycles through each judge's score in left-to-right fighter order. SCORE PENDING means no cards have been reported. On a final bout, the result also cycles through the winner and the reported method. A missing portrait uses the fighter's initial.

The board plays one short finish animation per bout it followed during this run. KO/TKO uses a burst, submissions use a closing frame, decisions use three judge marks, and other reported outcomes use a sweep with their method name. Starting the board after a fight has ended shows the final without replaying old celebrations. Result details are retrieved in the background from ESPN's MMA competition status endpoint. The offline demo is a fictional example with a submission finish.
