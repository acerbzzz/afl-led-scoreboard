"""AFL LED scoreboard powered by the Squiggle REST and Event APIs.

Python 3.10+. No browser-side calls; physical hardware requires rgbmatrix.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from PIL import Image, ImageDraw

API = "https://api.squiggle.com.au/"
EVENTS = "https://sse.squiggle.com.au/events"
ROOT = Path(__file__).resolve().parent
CACHE = ROOT / ".cache"
SCORE_KEYS = ("hscore", "ascore", "hgoals", "agoals", "hbehinds", "abehinds")
TEAMS = {
    1: ("ADE", "Adelaide", "#E31B23"),
    2: ("BRI", "Brisbane", "#7A003C"),
    3: ("CAR", "Carlton", "#59CBE8"),
    4: ("COL", "Collingwood", "#FFFFFF"),
    5: ("ESS", "Essendon", "#E31B23"),
    6: ("FRE", "Fremantle", "#A62385"),
    7: ("GEE", "Geelong", "#86A8D1"),
    8: ("GCS", "Gold Coast", "#F8D548"),
    9: ("GWS", "GWS", "#F15A22"),
    10: ("HAW", "Hawthorn", "#D1A962"),
    11: ("MEL", "Melbourne", "#D50032"),
    12: ("NTH", "North Melbourne", "#56A0D8"),
    13: ("PTA", "Port Adelaide", "#00A7B5"),
    14: ("RIC", "Richmond", "#FFD200"),
    15: ("STK", "Stkilda", "#E31B23"),
    16: ("SYD", "Sydney", "#E31B23"),
    17: ("WCE", "West Coast", "#F1C02E"),
    18: ("WBD", "Western Bulldogs", "#2A6EC6"),
}


def contact_headers(email: str) -> dict[str, str]:
    """Squiggle requires a human-readable User-Agent containing a contact email."""
    if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email or ""):
        raise ValueError("Set SQUIGGLE_CONTACT_EMAIL to a real contact email before live API use")
    return {"User-Agent": f"AFL LED Scoreboard (github.com/acerbzzz/afl-led-scoreboard; {email})", "Accept": "application/json"}


def get_json(url: str, headers: dict[str, str], timeout: int = 15):
    with urlopen(Request(url, headers=headers), timeout=timeout) as resp:
        return json.load(resp)


def season_games(year: int, headers: dict[str, str], cache_minutes: int = 30, cache_dir: Path = CACHE) -> list[dict]:
    if not 2000 <= year <= 2100:
        raise ValueError("Year must be from 2000 to 2100")
    path = cache_dir / f"games_{year}.json"
    if path.exists() and time.time() - path.stat().st_mtime < cache_minutes * 60:
        try:
            cached = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(cached, list):
                return cached
        except (ValueError, OSError):
            pass
    try:
        result = get_json(f"{API}?q=games;year={year}", headers)
        games = result.get("games", [])
        if not isinstance(games, list):
            raise ValueError("Squiggle games response is invalid")
        cache_dir.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(games), encoding="utf-8")
        return games
    except (OSError, HTTPError, URLError, ValueError) as exc:
        if path.exists():
            try:
                cached = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(cached, list):
                    print(f"WARNING: network failure; using stale cached fixture: {exc}", file=sys.stderr)
                    return cached
            except (OSError, ValueError):
                pass
        raise RuntimeError(f"Cannot fetch Squiggle games: {exc}") from exc


def iso_date(value) -> datetime:
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(timezone.utc)
    except (ValueError, TypeError):
        return datetime.min.replace(tzinfo=timezone.utc)


def is_live(game: dict) -> bool:
    try:
        progress = int(game.get("complete") or 0)
    except (TypeError, ValueError):
        return False
    return 0 < progress < 100


def matches_favorite(game: dict, favorite: str | None) -> bool:
    if not favorite:
        return True
    needle = favorite.lower().replace(" ", "")
    for side in ("hteam", "ateam"):
        tid = game.get(side)
        name, full, _ = TEAMS.get(int(tid or 0), (str(tid), str(tid), "#FFFFFF")) if str(tid).isdigit() else (str(tid), str(tid), "#FFFFFF")
        if any(needle in text.lower().replace(" ", "") for text in (name, full, str(tid))):
            return True
    return False


def select_games(games: list[dict], favorite: str | None = None, now: datetime | None = None) -> list[dict]:
    now = now or datetime.now(timezone.utc)
    filtered = [g for g in games if matches_favorite(g, favorite)]
    live = sorted((g for g in filtered if is_live(g)), key=lambda g: iso_date(g.get("date")))
    future = sorted((g for g in filtered if not (int(g.get("complete") or 0)) and iso_date(g.get("date")) >= now), key=lambda g: iso_date(g.get("date")))
    finished = sorted((g for g in filtered if int(g.get("complete") or 0) >= 100), key=lambda g: iso_date(g.get("date")), reverse=True)
    return live + future + finished


def as_int(value):
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def format_scoring(game: dict, prefix: str) -> tuple[str, str]:
    goals, behinds, total = [as_int(game.get(f"{prefix}{field}")) for field in ("goals", "behinds", "score")]
    if total is None and goals is not None and behinds is not None:
        total = 6 * goals + behinds
    if goals is None or behinds is None:
        return "-.-", str(total) if total is not None else "--"
    return f"{goals}.{behinds}", str(total) if total is not None else "--"


def status_text(game: dict) -> str:
    if int(game.get("complete") or 0) >= 100:
        return "FULL TIME"
    if is_live(game):
        return str(game.get("timestr") or "LIVE")[:18].upper()
    when = iso_date(game.get("date"))
    if when.year <= 1:
        return "UPCOMING"
    # Always show Australian Eastern football time, respecting DST.
    mel = when.astimezone(ZoneInfo("Australia/Melbourne"))
    return mel.strftime("%d %b %I:%M%p")


def team_data(game: dict, side: str) -> tuple[str, str, str]:
    val = game.get(side)
    if str(val).isdigit():
        return TEAMS.get(int(val), (f"T{val}", "", "#AAAAAA"))
    text = str(val or "---")
    by_name = next((v for v in TEAMS.values() if text.lower() in (v[0].lower(), v[1].lower())), None)
    return by_name or (text[:3].upper(), "", "#AAAAAA")


def logo_image(full: str, size: int = 9):
    if not full:
        return None
    path = ROOT / "logos" / f"{full}.bmp"
    if not path.exists():
        return None
    try:
        with Image.open(path) as original:
            return original.convert("RGB").resize((size, size), Image.Resampling.LANCZOS)
    except (OSError, ValueError):
        return None


PIXELS = {
    "0": ("111", "101", "101", "101", "111"),
    "1": ("010", "110", "010", "010", "111"),
    "2": ("111", "001", "111", "100", "111"),
    "3": ("111", "001", "111", "001", "111"),
    "4": ("101", "101", "111", "001", "001"),
    "5": ("111", "100", "111", "001", "111"),
    "6": ("111", "100", "111", "101", "111"),
    "7": ("111", "001", "010", "010", "010"),
    "8": ("111", "101", "111", "101", "111"),
    "9": ("111", "101", "111", "001", "111"),
    "A": ("010", "101", "111", "101", "101"),
    "B": ("110", "101", "110", "101", "110"),
    "C": ("011", "100", "100", "100", "011"),
    "D": ("110", "101", "101", "101", "110"),
    "E": ("111", "100", "110", "100", "111"),
    "F": ("111", "100", "110", "100", "100"),
    "G": ("011", "100", "101", "101", "011"),
    "H": ("101", "101", "111", "101", "101"),
    "I": ("111", "010", "010", "010", "111"),
    "J": ("001", "001", "001", "101", "010"),
    "K": ("101", "101", "110", "101", "101"),
    "L": ("100", "100", "100", "100", "111"),
    "M": ("101", "111", "111", "101", "101"),
    "N": ("101", "111", "111", "111", "101"),
    "O": ("010", "101", "101", "101", "010"),
    "P": ("110", "101", "110", "100", "100"),
    "Q": ("010", "101", "101", "111", "011"),
    "R": ("110", "101", "110", "101", "101"),
    "S": ("011", "100", "010", "001", "110"),
    "T": ("111", "010", "010", "010", "010"),
    "U": ("101", "101", "101", "101", "111"),
    "V": ("101", "101", "101", "101", "010"),
    "W": ("101", "101", "111", "111", "101"),
    "X": ("101", "101", "010", "101", "101"),
    "Y": ("101", "101", "010", "010", "010"),
    "Z": ("111", "001", "010", "100", "111"),
    ".": ("000", "000", "000", "000", "010"),
    ":": ("000", "010", "000", "010", "000"),
    "-": ("000", "000", "111", "000", "000"),
    " ": ("000", "000", "000", "000", "000"),
    "?": ("111", "001", "010", "000", "010"),
}


def pixels(draw: ImageDraw.ImageDraw, pos: tuple[int, int], message: str, color: str) -> None:
    x, y = pos
    for char in message.upper():
        for py, row in enumerate(PIXELS.get(char, PIXELS["?"])):
            for px, bit in enumerate(row):
                if bit == "1":
                    draw.point((x + px, y + py), fill=color)
        x += 4


def draw_game(game: dict | None, width: int = 64, height: int = 32) -> Image.Image:
    if width != 64 or height != 32:
        raise ValueError("Version 1 supports one 64x32 LED panel")
    image = Image.new("RGB", (width, height), "#000000")
    draw = ImageDraw.Draw(image)
    if game is None:
        pixels(draw, (4, 13), "NO AFL GAMES", "white")
        return image
    pixels(draw, (1, 2), f"R{game.get('round', '?')}"[:4], "#58D4FF")
    pixels(draw, (18, 2), status_text(game)[:11], "#FFD34D")
    draw.line((0, 9, 63, 9), fill="#303030")
    for y, prefix, side in ((11, "h", "hteam"), (22, "a", "ateam")):
        short, full, color = team_data(game, side)
        logo = logo_image(full, 9)
        if logo is not None:
            image.paste(logo, (1, y))
        else:
            draw.rectangle((1, y + 1, 8, y + 8), fill=color)
        pixels(draw, (12, y + 2), short[:3], color)
        gb, total = format_scoring(game, prefix)
        pixels(draw, (28, y + 2), gb[:5], "#DDDDDD")
        # Pin total to the right edge while preventing overlap with goals.behinds.
        pixels(draw, (64 - 4 * min(len(total), 3), y + 2), total[:3], "#FFFFFF")
    return image


def apply_event(state: dict[int, dict], event_type: str, payload: dict) -> bool:
    """Merge documented Squiggle SSE event shapes; ignore unknown games/events."""
    if not isinstance(payload, dict):
        return False
    game_id = as_int(payload.get("id" if event_type == "game" else "gameid"))
    if game_id is None:
        return False
    if event_type == "game":
        state[game_id] = payload
        return True
    if game_id not in state:
        return False
    if event_type == "score":
        score = payload.get("score")
        if isinstance(score, dict):
            for k in SCORE_KEYS:
                if k in score:
                    state[game_id][k] = score[k]
        for k in ("timestr", "complete"):
            if k in payload:
                state[game_id][k] = payload[k]
        return True
    if event_type in ("timestr", "complete", "winner"):
        if event_type in payload:
            state[game_id][event_type] = payload[event_type]
        return True
    return False


def event_messages(response):
    """Read Server-Sent Events from a response, supporting multiline data."""
    event_type, data = "message", []
    for raw in response:
        line = raw.decode("utf-8", errors="replace").rstrip("\r\n")
        if not line:
            if data:
                try:
                    yield event_type, json.loads("\n".join(data))
                except json.JSONDecodeError:
                    pass
            event_type, data = "message", []
        elif line.startswith(":"):
            continue
        elif line.startswith("event:"):
            event_type = line[6:].strip()
        elif line.startswith("data:"):
            data.append(line[5:].lstrip(" "))
    if data:
        try:
            yield event_type, json.loads("\n".join(data))
        except json.JSONDecodeError:
            pass


def show(frame: Image.Image, mode: str, preview_path: Path, matrix=None) -> None:
    if mode == "matrix":
        if matrix is None:
            raise RuntimeError("matrix driver unavailable")
        canvas = matrix.CreateFrameCanvas()
        canvas.SetImage(frame)
        matrix.SwapOnVSync(canvas)
    else:
        preview_path.parent.mkdir(parents=True, exist_ok=True)
        # Nearest-neighbour preserves crisp LEDs for a browser/desktop preview.
        frame.resize((640, 320), Image.Resampling.NEAREST).save(preview_path)
        print(f"Preview updated: {preview_path}")


def make_matrix(args):
    try:
        from rgbmatrix import RGBMatrix, RGBMatrixOptions
    except ImportError as exc:
        raise RuntimeError("Install rpi-rgb-led-matrix Python bindings on your Pi before --driver matrix") from exc
    options = RGBMatrixOptions()
    options.rows = 32
    options.cols = 64
    options.chain_length = 1
    options.parallel = 1
    options.hardware_mapping = args.mapping
    options.brightness = args.brightness
    options.gpio_slowdown = args.gpio_slowdown
    return RGBMatrix(options=options)


def demo_game():
    return {"id": 9999, "round": 10, "year": 2026, "hteam": 6, "ateam": 17,
            "hgoals": 12, "hbehinds": 8, "hscore": 80,
            "agoals": 9, "abehinds": 10, "ascore": 64,
            "complete": 64, "timestr": "Q3 14:26", "date": "2026-05-24T05:20:00Z"}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Australian rules football 64x32 RGB LED scoreboard")
    parser.add_argument("--driver", choices=("preview", "matrix"), default="preview")
    parser.add_argument("--once", action="store_true", help="Render one REST snapshot and exit")
    parser.add_argument("--demo", action="store_true", help="Render a demo without using Squiggle")
    parser.add_argument("--year", type=int, default=datetime.now(ZoneInfo("Australia/Melbourne")).year)
    parser.add_argument("--favorite", help="Team name or code, e.g. FRE or Fremantle")
    parser.add_argument("--preview", type=Path, default=ROOT / "preview.png")
    parser.add_argument("--cache-minutes", type=int, default=30)
    parser.add_argument("--refresh-minutes", type=int, default=30, help="REST refresh interval; live scores use SSE")
    parser.add_argument("--mapping", default="regular", help="e.g. regular or adafruit-hat")
    parser.add_argument("--brightness", type=int, default=55)
    parser.add_argument("--gpio-slowdown", type=int, default=2)
    args = parser.parse_args(argv)
    if args.cache_minutes < 5 or args.refresh_minutes < 5:
        parser.error("Do not poll Squiggle faster than every five minutes; live updates use SSE")
    if not 1 <= args.brightness <= 100:
        parser.error("Brightness must be 1..100")
    matrix = make_matrix(args) if args.driver == "matrix" else None
    if args.demo:
        show(draw_game(demo_game()), args.driver, args.preview, matrix)
        return 0
    try:
        headers = contact_headers(os.environ.get("SQUIGGLE_CONTACT_EMAIL", ""))
    except ValueError as exc:
        parser.error(str(exc))
    # REST snapshot is only used for fixture bootstrap and occasional resync.
    # The Squiggle SSE event endpoint is used while a game is in progress.
    while True:
        try:
            games = season_games(args.year, headers, args.cache_minutes)
            state = {int(g["id"]): g for g in games if as_int(g.get("id")) is not None}
            choices = select_games(list(state.values()), args.favorite)
            selected = choices[0] if choices else None
            show(draw_game(selected), args.driver, args.preview, matrix)
            if args.once:
                return 0
            # SSE connects only while a game is live. No busy polling during the offseason.
            if selected and is_live(selected):
                try:
                    sse_headers = dict(headers, Accept="text/event-stream", **{"Cache-Control": "no-cache"})
                    game_id = int(selected["id"])
                    with urlopen(Request(f"{EVENTS}/{game_id}", headers=sse_headers), timeout=90) as stream:
                        for event_type, payload in event_messages(stream):
                            if apply_event(state, event_type, payload):
                                choices = select_games(list(state.values()), args.favorite)
                                selected = choices[0] if choices else None
                                show(draw_game(selected), args.driver, args.preview, matrix)
                                if not selected or not is_live(selected) or int(selected.get("id", -1)) != game_id:
                                    break
                except (OSError, HTTPError, URLError, TimeoutError) as exc:
                    print(f"SSE connection interrupted: {exc}; will reconnect", file=sys.stderr)
                    time.sleep(10)
            else:
                time.sleep(args.refresh_minutes * 60)
        except (RuntimeError, ValueError, OSError) as exc:
            print(f"Scoreboard error: {exc}", file=sys.stderr)
            if args.once:
                return 1
            time.sleep(60)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("Scoreboard stopped")
