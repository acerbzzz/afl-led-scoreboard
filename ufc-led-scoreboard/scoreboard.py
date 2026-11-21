"""64x32 UFC fight board for direct-GPIO Raspberry Pi matrices."""
import os
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import gameguide as guide
from functools import lru_cache
import argparse
import json
import logging
import time
import unicodedata
from dataclasses import dataclass
from urllib.request import Request, urlopen

from PIL import Image, ImageDraw
from portraits import photo
from finishes import ResultFeed, method_label

URL = "https://site.api.espn.com/apis/site/v2/sports/mma/ufc/scoreboard"
# Four native LED rows per glyph. Each octal digit encodes a three-pixel row.
FONT = dict(zip("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 :-./'",
                ("2575 6567 3443 6556 7467 7464 3473 5755 7227 1116 5655 4447 "
                 "5775 5675 2552 6574 2553 6565 3616 7222 5557 5552 5575 5225 "
                 "5522 7127 7557 2627 7127 7317 5571 7616 4677 7122 7677 7571 "
                 "0000 0202 0070 0002 1124 2200").split()))


@dataclass
class Bout:
    card: str
    names: tuple
    state: str
    detail: str
    winner: tuple = (False, False)
    athlete_ids: tuple = ("", "")
    key: tuple = ()
    method: str = ""
    cards: tuple = ()
    timing: str = ""


def bouts(payload):
    if not isinstance(payload, dict) or not isinstance(payload.get("events"), list):
        raise ValueError("Missing events list")
    result = []
    for event in payload["events"]:
        for fight in event.get("competitions", []):
            pair = fight.get("competitors", [])
            if len(pair) != 2:
                continue
            names = []
            for competitor in pair:
                athlete = competitor.get("athlete", {})
                name = athlete.get("lastName") or athlete.get("shortName") or athlete.get("displayName") or "TBA"
                names.append(name.split(". ", 1)[-1])
            status = fight.get("status", {})
            kind = status.get("type", {})
            state = kind.get("state", "")
            detail = kind.get("description") or "PENDING"
            if state == "in":
                clock = status.get("displayClock")
                detail = "R{}".format(status["period"]) if status.get("period") else "LIVE"
                if clock and clock != "-":
                    detail += " " + clock
            elif state == "pre" and kind.get("name") == "STATUS_SCHEDULED":
                detail = "UPCOMING"
            judge_scores = []
            for competitor in pair:
                lines = competitor.get("linescores") or []
                judges = lines[0].get("linescores", []) if lines else []
                judge_scores.append([str(j.get("displayValue", "")) for j in judges])
            cards = tuple(a + "-" + b for a, b in zip(*judge_scores)
                          if a.isdigit() and b.isdigit() and int(a) and int(b))
            timing = "R{}".format(status["period"]) if status.get("period") else ""
            if timing and status.get("displayClock") not in (None, "", "-"):
                timing += " " + status["displayClock"]
            result.append(Bout(event.get("shortName") or "UFC", tuple(names), state, detail,
                               tuple(c.get("winner") is True for c in pair),
                               tuple(str(c.get("id") or c.get("athlete", {}).get("id") or "") for c in pair),
                               (str(event.get("id", "")), str(fight.get("id", ""))),
                               method_label(status.get("result")) or method_label(fight.get("result")) or method_label(fight.get("method")), cards, timing))
    return result


def pixels(draw, x, y, label, color, width):
    label = unicodedata.normalize("NFKD", label.upper()).encode("ascii", "ignore").decode()
    for letter in label:
        if x + 3 > width:
            break
        for row, mask in enumerate(FONT.get(letter, "7120")):
            for col in range(3):
                if int(mask) & (4 >> col):
                    draw.point((x + col, y + row), color)
        x += 4


def short_method(label):
    upper = label.upper()
    for fragment, short in (("UNANIMOUS","UD"), ("SPLIT","SD"), ("MAJORITY","MD")):
        if fragment in upper and "DRAW" not in upper:
            return "DEC " + short
    if "TECHNICAL KNOCKOUT" in upper or "TKO" in upper:
        return "KO/TKO" if "KO/TKO" in upper else "TKO"
    if "KNOCKOUT" in upper:
        return "KO"
    if "SUBMISSION" in upper:
        return "SUBMISSION"
    return upper


def big_line(image, label, y, color):
    label = label[:26]
    width = max(1, len(label) * 4 - 1)
    strip = Image.new("RGB", (width, 4))
    pixels(ImageDraw.Draw(strip), 0, 0, label, color, width)
    strip = strip.resize((min(64, width * 2), 9), Image.Resampling.NEAREST)
    image.paste(strip, ((64 - strip.width) // 2, y))


@lru_cache(maxsize=1)
def promotion_mark():
    path = Path(__file__).resolve().parent.parent / "badges/ufc/ufc.png"
    with Image.open(path) as source:
        mark = source.convert("RGBA")
    mark.thumbnail((18,7),Image.Resampling.LANCZOS)
    red = Image.new("RGBA",mark.size,"#ff3744")
    red.putalpha(mark.getchannel("A"))
    return red


def put_mark(frame,x=0):
    mark = promotion_mark()
    frame.paste(mark,(x,0),mark)


def fight_frame(bout, tick, offline):
    image = Image.new("RGB", (64, 32))
    draw = ImageDraw.Draw(image)
    if bout.state == "post":
        winner = next((n for n, won in zip(bout.names, bout.winner) if won), "")
        pixels(draw, 20, 1, "WINNER" if winner else "FINAL", "#ffb944", 64)
        big_line(image, winner or "RESULT PENDING", 8, "#63ff84")
        big_line(image, short_method(bout.method) or "METHOD PENDING", 21, "#ffffff")
    else:
        pixels(draw, 20, 1, ("OFF " if offline else "") + (bout.timing or bout.detail), "#ffb944", 64)
        big_line(image, bout.names[0], 9, "#ff7777")
        big_line(image, bout.names[1], 21, "#8abaff")
    put_mark(image)
    if offline and bout.state == "post":
        draw.point((63,0), fill="orange")
    return image


def celebration(bout):
    label = bout.method.upper()
    image = fight_frame(bout, 0, False)
    for step in range(14):
        frame = image.copy()
        draw = ImageDraw.Draw(frame)
        draw.rectangle((0, 24, 63, 31), fill="black")
        progress = min(step, 8)
        if "KO" in label or "KNOCKOUT" in label:
            for x in (31-progress*3, 32+progress*3):
                draw.line((31, 24, x, 31), fill="#ff6030")
        elif "SUB" in label:
            draw.rectangle((progress*3, 24, 63-progress*3, 31), outline="#ac71ff")
        elif "DEC" in label or label in ("UD", "SD", "MD"):
            for x in range(0, min(3, 1+step//3)*22, 22):
                draw.line((x, 31, x+17, 31), fill="#ffcb55")
        else:
            draw.line((0, 31, min(63, step*6), 31), fill="#62ffa3")
        offset = min(max(0, len(label)-16), max(0, step-4)*2)
        pixels(draw, 0, 25, label[offset:], "white", 64)
        yield frame


def render(bout, offline=False, demo=False, tick=0):
    if bout and bout.state in ("in", "post"):
        frame = fight_frame(bout, tick, offline)
        if demo:
            pen = ImageDraw.Draw(frame)
            pen.rectangle((46,0,63,5),fill="black")
            pixels(pen, 48, 1, "DEMO", "#ffb944", 64)
        return frame
    image = Image.new("RGB", (64, 32))
    draw = ImageDraw.Draw(image)
    title = "DEMO" if demo else (bout.card if bout else "UFC")
    put_mark(image)
    pixels(draw, 20, 0, title, "#ffae36", 64)
    for i, name in enumerate(bout.names if bout else ("NO FIGHTS", "")):
        y = 8 + i * 8
        win = bout and bout.state == "post" and bout.winner[i]
        draw.rectangle((0, y, 2, y+5), fill=("#ff5050", "#4b9aff")[i])
        pixels(draw, 5, y, name, "#63ff84" if win else "white", 57 if win else 64)
        if win:
            pixels(draw, 59, y, "W", "#63ff84", 64)
    footer = "FEED OFFLINE" if offline else (bout.detail if bout else "NO CARD")
    pixels(draw, 1, 26, footer, "#ffd04a" if offline else "#65e3da", 64)
    return image


def intro(bout, corner, demo=False):
    portrait = photo(bout.athlete_ids[corner])
    if portrait is None:
        return render(bout, demo=demo)
    image = Image.new("RGB", (64, 32))
    image.paste(portrait, (0, 1), portrait)
    draw = ImageDraw.Draw(image)
    color = ("#ff5050", "#4b9aff")[corner]
    draw.line((30, 1, 30, 30), fill=color)
    put_mark(image,32)
    if demo:
        pixels(draw, 48, 1, "DEMO", color, 64)
    name = bout.names[corner]
    pixels(draw, 32, 11, name[:8], "white", 64)
    pixels(draw, 32, 18, name[8:16], "white", 64)
    pixels(draw, 32, 26, "ON CARD" if not demo else "INTRO", "#65e3da", 64)
    return image


DEMO = [Bout("UFC", ("Muniz", "Allen"), "pre", "UPCOMING", athlete_ids=("3091099", "3902098")),
        Bout("UFC", ("Muniz", "Allen"), "in", "R2 3:18", athlete_ids=("3091099", "3902098")),
        Bout("UFC", ("Muniz", "Allen"), "post", "FINAL", (False, True), ("3091099", "3902098"), ("demo","1"), "Submission", timing="R2 3:18")]


def fetch():
    url = URL
    if os.environ.get("UFC_RESULTS_ONLY") == "1":
        from datetime import date, timedelta
        today = date.today()
        url += "?dates=" + (today - timedelta(days=28)).strftime("%Y%m%d") + "-" + today.strftime("%Y%m%d")
    request = Request(url, headers={"User-Agent": "ufc-led-scoreboard/1.0"})
    with urlopen(request, timeout=8) as response:
        payload = json.load(response)
        if os.environ.get("UFC_RESULTS_ONLY") == "1":
            for event in sorted(payload.get("events", []), key=lambda e: e.get("date",""), reverse=True):
                completed = [b for b in bouts({"events":[event]}) if b.state == "post"]
                if completed:
                    return completed
            return []
        return bouts(payload)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--driver", choices=["preview", "matrix"], default="preview")
    parser.add_argument("--mapping", default="regular")
    parser.add_argument("--gpio-slowdown", type=int, default=1)
    parser.add_argument("--brightness", type=int, choices=range(1, 101), default=50, metavar="1-100")
    args = parser.parse_args()
    matrix = None
    if args.driver == "matrix":
        from rgbmatrix import RGBMatrix, RGBMatrixOptions
        options = RGBMatrixOptions()
        options.rows, options.cols = 32, 64
        options.hardware_mapping = args.mapping
        options.gpio_slowdown = args.gpio_slowdown
        options.brightness = args.brightness
        matrix = RGBMatrix(options=options)
    card, refresh, index, offline = DEMO if args.demo else [], 0, 0, False
    if args.demo:
        guide.feed("Demo")
    def gid(b):
        return "-".join(b.key) if b.key and all(b.key) else "demo-"+b.state
    results = ResultFeed()
    played = set()
    eligible = set()
    previously_live = set()
    last_finish = None
    def display(frame):
        if os.environ.get("BOARD_FRAME"):
            target = Path(os.environ["BOARD_FRAME"])
            frame.save(target.with_suffix(".tmp"), format="PNG")
            target.with_suffix(".tmp").replace(target)
        elif matrix is not None:
            matrix.SetImage(frame)
        else:
            frame.resize((640, 320), Image.Resampling.NEAREST).save("preview.png")

    try:
        while True:
            if not args.demo and time.monotonic() >= refresh:
                try:
                    card = fetch()
                    offline = False
                    guide.feed("Connected")
                except (OSError, ValueError) as exc:
                    logging.warning("UFC feed unavailable: %s", exc)
                    offline = True
                    guide.feed("Offline")
                refresh = time.monotonic() + 30
            if not args.demo and not offline:
                results.update(card)
                newly_finished = [b for b in card if b.state=="post" and b.key in previously_live]
                if newly_finished:
                    last_finish = newly_finished[0].key
                previously_live = {b.key for b in card if b.state=="in"}
                eligible.update(b.key for b in card if b.state in ("pre", "in"))
                for finished in card:
                    if ((not guide.PIN or guide.PIN == gid(finished)) and finished.state == "post" and finished.method and finished.key in eligible
                            and finished.key not in played and not args.once):
                        for frame in celebration(finished):
                            display(frame)
                            time.sleep(.12)
                        played.add(finished.key)
                        display(render(finished))
                        time.sleep(3)
            live = [b for b in card if b.state == "in"]
            finals = [b for b in card if b.state == "post"]
            last_result = [b for b in finals if b.key == last_finish]
            pool = card if args.demo or offline else (live or last_result or card)
            if os.environ.get("UFC_RESULTS_ONLY") == "1":
                pool = finals
            listing = finals if os.environ.get("UFC_RESULTS_ONLY") == "1" else card
            if guide.PIN:
                pool = [b for b in listing if gid(b)==guide.PIN]
            entries = [guide.game(gid(b),b.names,b.detail,
                                  " · ".join(filter(None,[next((n for n,w in zip(b.names,b.winner) if w),""),b.method])) or b.timing,b.state=="in") for b in listing]
            screens = []
            for bout in pool:
                if bout.state == "pre" and bout.detail == "UPCOMING" and not offline:
                    screens.extend([(bout, 0), (bout, 1)])
                else:
                    screens.append((bout, None))
            bout, corner = screens[index % len(screens)] if screens else (None, None)
            guide.report(entries,gid(bout) if bout else "")
            if guide.PIN and not bout:
                time.sleep(2)
                continue
            if args.demo and bout and bout.state == "post" and bout.key not in played:
                for frame in celebration(bout):
                    display(frame)
                    time.sleep(.12)
                played.add(bout.key)
            frame = render(bout, offline, args.demo, index // max(1, len(screens))) if corner is None else intro(bout, corner, args.demo)
            display(frame)
            if args.once:
                return
            index += 1
            time.sleep(5 if args.demo else 8)
    except KeyboardInterrupt:
        pass
    finally:
        if matrix is not None:
            matrix.Clear()


if __name__ == "__main__":
    main()
