"""AFL LED scoreboard powered by the Squiggle REST and Event APIs.

Python 3.10+. No browser-side calls; physical hardware requires rgbmatrix.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from PIL import Image, ImageDraw, ImageFont, ImageOps

API = "https://api.squiggle.com.au/"
EVENTS = "https://sse.squiggle.com.au/events"
ROOT = Path(__file__).resolve().parent
CACHE = Path(os.environ.get("AFL_SCOREBOARD_CACHE_DIR", str(ROOT / ".cache")))
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

# Squiggle returns full club names (sometimes with nicknames), not just IDs.
TEAM_ALIASES = {
    "brisbanelions": 2,
    "fremantledockers": 6,
    "geelongcats": 7,
    "goldcoastsuns": 8,
    "greaterwesternsydney": 9,
    "gwsgiants": 9,
    "northmelbournekangaroos": 12,
    "portadelaidepower": 13,
    "stkildasaints": 15,
    "st.kilda": 15,
    "westcoasteagles": 17,
    "adelaidecrows": 1,
    "carltonblues": 3,
    "collingwoodmagpies": 4,
    "essendonbombers": 5,
    "hawthornhawks": 10,
    "melbournedemons": 11,
    "richmondtigers": 14,
    "sydneyswans": 16,
    "westernbulldogs": 18,
}


def normalize_team(value) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value or "").lower())


def resolve_team(value) -> tuple[str, str, str]:
    if str(value).isdigit():
        return TEAMS.get(int(value), (f"T{value}", "", "#AAAAAA"))
    label = str(value or "---")
    key = normalize_team(label)
    for team in TEAMS.values():
        if key in (normalize_team(team[0]), normalize_team(team[1])):
            return team
    team_id = TEAM_ALIASES.get(key)
    return TEAMS[team_id] if team_id is not None else (label[:3].upper(), "", "#AAAAAA")


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
        result = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        # Squiggle's zone-less match times use Australian Eastern local time.
        if result.tzinfo is None:
            result = result.replace(tzinfo=ZoneInfo("Australia/Melbourne"))
        return result.astimezone(timezone.utc)
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
    needle = normalize_team(favorite)
    for side in ("hteam", "ateam"):
        value = game.get(side)
        short, full, _ = resolve_team(value)
        if any(needle in normalize_team(text) for text in (short, full, value)):
            return True
    return False


def select_games(games: list[dict], favorite: str | None = None, now: datetime | None = None) -> list[dict]:
    now = now or datetime.now(timezone.utc)
    filtered = [g for g in games if matches_favorite(g, favorite)]
    live = sorted((g for g in filtered if is_live(g)), key=lambda g: iso_date(g.get("date")))
    future = sorted((g for g in filtered if not (int(g.get("complete") or 0)) and iso_date(g.get("date")) >= now), key=lambda g: iso_date(g.get("date")))
    finished = sorted((g for g in filtered if int(g.get("complete") or 0) >= 100), key=lambda g: iso_date(g.get("date")), reverse=True)
    return live + future + finished



def rotation_pool(games: list[dict], favorite: str | None = None, limit: int = 6, now: datetime | None = None) -> list[dict]:
    """Choose the most relevant games once per display step; no network calls."""
    if limit < 1:
        raise ValueError("rotation limit must be at least 1")
    return select_games(games, favorite, now)[:limit]


def rotation_choice(games: list[dict], index: int, favorite: str | None = None,
                    limit: int = 6, now: datetime | None = None) -> dict | None:
    pool = rotation_pool(games, favorite, limit, now)
    return pool[index % len(pool)] if pool else None


def should_watch_events(games: list[dict], now: datetime | None = None) -> bool:
    """Hold one SSE connection when games are active or due to start soon."""
    now = now or datetime.now(timezone.utc)
    for game in games:
        if is_live(game):
            return True
        if (as_int(game.get("complete")) or 0) == 0:
            start = iso_date(game.get("date"))
            if now - timedelta(hours=2) <= start <= now + timedelta(hours=1):
                return True
    return False


def follow_events(state: dict[int, dict], lock: threading.Lock,
                  stop: threading.Event, headers: dict[str, str]) -> None:
    """Follow all live games on one long-lived stream, independently of display rotation."""
    event_headers = dict(headers, Accept="text/event-stream", **{"Cache-Control": "no-cache"})
    while not stop.is_set():
        with lock:
            watch = should_watch_events(list(state.values()))
        if not watch:
            stop.wait(30)
            continue
        try:
            with urlopen(Request(EVENTS, headers=event_headers), timeout=90) as stream:
                for event_type, payload in event_messages(stream):
                    if stop.is_set():
                        return
                    with lock:
                        apply_event(state, event_type, payload)
        except (OSError, HTTPError, URLError, TimeoutError, ValueError) as exc:
            print(f"SSE connection interrupted: {exc}; reconnecting", file=sys.stderr)
        stop.wait(10)  # A closed stream must not result in a tight reconnect loop.


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
    """Short, readable text that fits inside a 64-pixel-wide matrix header."""
    raw = str(game.get("timestr") or "").strip().upper()
    if (as_int(game.get("complete")) or 0) >= 100 or raw == "FULL TIME":
        return "FINAL"
    if is_live(game):
        if "3/4 TIME" in raw or "THREE QUARTER" in raw:
            return "Q3 END"
        if "HALF TIME" in raw or "1/2 TIME" in raw:
            return "HALF TIME"
        if "1/4 TIME" in raw or "QUARTER TIME" in raw:
            return "Q1 END"
        match = re.search(r"\bQ[1-4]\b", raw)
        return raw[match.start():][:11] if match else "LIVE"
    when = iso_date(game.get("date"))
    if when.year <= 1:
        return "UPCOMING"
    mel = when.astimezone(ZoneInfo("Australia/Melbourne"))
    return mel.strftime("%d%b %H:%M").upper()  # e.g. 26SEP 14:30, 11 chars


def team_data(game: dict, side: str) -> tuple[str, str, str]:
    return resolve_team(game.get(side))


class MissingLogoError(RuntimeError):
    """A required AFL club logo is missing, unreadable, or unidentified."""


def logo_image(full: str, size: int = 9) -> Image.Image:
    """Load a real club image. There is deliberately no initials/colour fallback."""
    if size < 1:
        raise ValueError("Logo size must be positive")
    if not full:
        raise MissingLogoError("Club has no recognised logo mapping; check the Squiggle team name")
    legacy = ROOT / "logos" / f"{full}.bmp"
    if not legacy.is_file():
        raise MissingLogoError(f"Required AFL club logo missing: {legacy}")
    # Prefer transparent high-resolution artwork on BOTH displays, including
    # native LED output. Keep the bundled real club crest for offline use.
    hd = ROOT / "logos_hd" / f"{full}.png"
    path = hd if hd.is_file() else legacy
    try:
        with Image.open(path) as source:
            source.load()
            min_dimension = 160 if path == hd else 16
            if min(source.size) < min_dimension:
                raise ValueError(f"logo image is smaller than {min_dimension}x{min_dimension}")
            image = source.convert("RGBA")
            if path == hd and image.getchannel("A").getextrema()[0] == 255:
                raise ValueError("HD club logo must have a transparent background")
            # Never stretch a crest to a square; contain and center it on alpha.
            scaled = ImageOps.contain(image, (size, size), method=Image.Resampling.LANCZOS)
            output = Image.new("RGBA", (size, size), (0, 0, 0, 0))
            output.paste(scaled, ((size - scaled.width) // 2, (size - scaled.height) // 2))
            return output
    except (OSError, ValueError) as exc:
        raise MissingLogoError(f"Required AFL club logo unreadable: {path} ({exc})") from exc


def verify_all_logos() -> int:
    """Fail early if ANY of the 18 club assets is absent or unreadable."""
    errors = []
    for _, full, _ in TEAMS.values():
        try:
            logo_image(full, 32)
        except MissingLogoError as exc:
            errors.append(str(exc))
    if errors:
        raise MissingLogoError("AFL logos are mandatory; fix these assets:\n" + "\n".join(errors))
    return len(TEAMS)


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
    # Native 64x32 composition: 5px header, 1px divider, two 12px crests.
    # Bigger logos are the first priority; all scoring fits without clipping.
    pixels(draw, (0, 0), f"R{game.get('round', '?')}"[:4], "#58D4FF")
    demo = bool(game.get("_demo"))
    status_color = "#30DAF5" if demo else ("#37E881" if is_live(game) else ("#FF6B75" if status_text(game) == "FINAL" else "#FFD34D"))
    pixels(draw, (18, 0), "DEMO" if demo else status_text(game)[:11], status_color)
    draw.line((0, 6, 63, 6), fill="#303030")
    draw.line((12, 19, 63, 19), fill="#202732")
    for y, prefix, side in ((7, "h", "hteam"), (20, "a", "ateam")):
        short, full, color = team_data(game, side)
        logo = logo_image(full, 12)
        image.paste(logo, (0, y), logo)
        pixels(draw, (13, y + 3), short[:3], color)
        gb, total = format_scoring(game, prefix)
        pixels(draw, (27, y + 3), gb[:5], "#DDDDDD")
        # Right-align up to three digits of points at the matrix's outer edge.
        rendered_total = total[:3]
        pixels(draw, (64 - 4 * len(rendered_total), y + 3), rendered_total, "#FFFFFF")
    return image



HD_WIDTH, HD_HEIGHT = 1280, 640


def _font(size: int, bold: bool = False):
    """Pillow bundles DejaVu fonts on most platforms, with a safe fallback."""
    name = "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"
    try:
        return ImageFont.truetype(name, size)
    except OSError:
        return ImageFont.load_default()


def _center_text(draw: ImageDraw.ImageDraw, middle: tuple[int, int], text: str,
                 font, fill: str) -> None:
    left, top, right, bottom = draw.textbbox((0, 0), text, font=font)
    draw.text((middle[0] - (right - left) / 2 - left,
               middle[1] - (bottom - top) / 2 - top), text, font=font, fill=fill)


def _bounded_text(draw: ImageDraw.ImageDraw, text: str, max_width: int,
                  preferred_size: int, minimum_size: int = 20, bold: bool = False):
    """Size text to fit a given area rather than silently clipping the team name."""
    for size in range(preferred_size, minimum_size - 1, -2):
        font = _font(size, bold)
        if draw.textbbox((0, 0), text, font=font)[2] <= max_width:
            return font
    return _font(minimum_size, bold)


def draw_game_hd(game: dict | None) -> Image.Image:
    """High-resolution desktop-only scoreboard; never upscale the tiny LED raster."""
    canvas = Image.new("RGB", (HD_WIDTH, HD_HEIGHT), "#07111d")
    draw = ImageDraw.Draw(canvas)
    for y in range(HD_HEIGHT):
        offset = int(11 * y / HD_HEIGHT)
        draw.line((0, y, HD_WIDTH, y), fill=(7 + offset, 17 + offset, 29 + offset))

    draw.rounded_rectangle((24, 24, 1256, 616), radius=30,
                           fill="#0b1525", outline="#2b3d52", width=2)
    draw.rectangle((28, 26, 1252, 32), fill="#12bdc7")
    demo = bool(game and game.get("_demo"))
    header = "AFL  /  DEMO SCOREBOARD" if demo else "AFL  /  LIVE SCOREBOARD"
    draw.text((65, 60), header, font=_font(38, True), fill="#ffffff")

    if game is None:
        _center_text(draw, (640, 342), "NO AFL GAMES AVAILABLE", _font(48, True), "#b8c6d9")
        return canvas

    round_no = game.get("round")
    is_grand_final = bool(as_int(game.get("is_grand_final")))
    is_final = bool(as_int(game.get("is_final")))
    round_name = ("GRAND FINAL" if is_grand_final else "FINALS" if is_final
                  else (f"ROUND {round_no}" if round_no is not None else "AFL"))
    date_value = iso_date(game.get("date"))
    if date_value.year > 1:
        date_text = date_value.astimezone(ZoneInfo("Australia/Melbourne")).strftime("%d %b %Y  •  %I:%M %p AET")
        date_text = date_text.replace(" 0", " ")
    else:
        date_text = "TIME TO BE CONFIRMED"
    draw.text((66, 113), f"{round_name}    {date_text}", font=_font(24), fill="#9eb0c5")

    complete = as_int(game.get("complete")) or 0
    if demo:
        state_label, detail, state_color = "DEMO", "SIMULATED SCORES", "#30daf5"
    elif complete >= 100:
        state_label, detail, state_color = "FULL TIME", "FINAL RESULT", "#44d9ab"
    elif is_live(game):
        state_label, detail, state_color = "LIVE", status_text(game), "#fb686e"
    else:
        state_label, detail, state_color = "UPCOMING", "MATCH PREVIEW", "#f5c85d"
    draw.rounded_rectangle((1010, 61, 1208, 115), radius=22,
                           fill="#1b283a", outline=state_color, width=2)
    _center_text(draw, (1109, 87), state_label, _font(25, True), state_color)
    draw.text((1017, 120), detail[:19], font=_font(16), fill="#9eb0c5")

    for y, side, prefix in ((169, "hteam", "h"), (366, "ateam", "a")):
        short, full, color = team_data(game, side)
        draw.rounded_rectangle((55, y, 1225, y + 175), radius=22,
                               fill="#142135", outline="#30415a", width=2)
        draw.rounded_rectangle((57, y + 2, 64, y + 173), radius=3, fill=color)
        draw.ellipse((77, y + 23, 204, y + 150), fill="#0b1423", outline=color, width=3)
        # Larger, transparent native-resolution crest with aspect ratio preserved.
        crest = logo_image(full, 116)
        canvas.paste(crest, (83, y + 29), crest)
        raw_name = game.get(side)
        display_name = (str(raw_name) if raw_name and not str(raw_name).isdigit() else full or short)
        display_name = display_name.replace("Stkilda", "St Kilda")
        draw.text((226, y + 37), display_name,
                  font=_bounded_text(draw, display_name, 475, 39, 24, bold=True), fill="#f0f5fa")
        draw.text((228, y + 102), "HOME" if side == "hteam" else "AWAY",
                  font=_font(18, True), fill="#8398b4")
        gb, total = format_scoring(game, prefix)
        score_font = _bounded_text(draw, gb, 225, 52, 30, bold=True)
        right_gb = 985
        gb_width = draw.textbbox((0, 0), gb, font=score_font)[2]
        draw.text((right_gb - gb_width, y + 55), gb, font=score_font, fill="#c3d1e2")
        draw.line((1015, y + 44, 1015, y + 136), fill="#34435a", width=2)
        total_font = _bounded_text(draw, total, 160, 91, 48, bold=True)
        b = draw.textbbox((0, 0), total, font=total_font)
        draw.text((1158 - (b[2] - b[0]), y + 32), total,
                  font=total_font, fill="#ffffff")

    draw.text((66, 576), "6 POINTS = GOAL    •    1 POINT = BEHIND", font=_font(19), fill="#839ab3")
    draw.text((1018 if demo else 1055, 576),
              "SAMPLE DATA" if demo else "SQUIGGLE DATA",
              font=_font(17, True), fill="#7189a3")
    return canvas

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


def show(frame: Image.Image, mode: str, preview_path: Path, matrix=None,
         game: dict | None = None, preview_style: str = "hd") -> None:
    if mode == "matrix":
        if matrix is None:
            raise RuntimeError("matrix driver unavailable")
        canvas = matrix.CreateFrameCanvas()
        canvas.SetImage(frame.convert("RGB"))
        matrix.SwapOnVSync(canvas)
    else:
        preview_path.parent.mkdir(parents=True, exist_ok=True)
        if preview_style == "hd":
            output = draw_game_hd(game)
        elif preview_style == "pixel":
            # True 64x32 LED simulation, enlarged with intentionally visible pixels.
            output = frame.resize((640, 320), Image.Resampling.NEAREST)
        else:
            raise ValueError(f"Unknown preview style: {preview_style}")
        output.save(preview_path)
        print(f"Preview updated: {preview_path} ({output.width}x{output.height}, {preview_style})")


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


def diagnostic_frames():
    """A 64x32 RGB colour/wiring test followed by an AFL demo frame."""
    for name, color in (("RED", "#E52B34"), ("GREEN", "#00CC55"), ("BLUE", "#2266FF")):
        img = Image.new("RGB", (64, 32), color)
        draw = ImageDraw.Draw(img)
        draw.rectangle((2, 10, 61, 21), fill="black")
        pixels(draw, (6, 13), name, "white")
        yield img
    yield draw_game(demo_game())


def run_hardware_test(matrix, pause: float = 1.0) -> None:
    if matrix is None:
        raise RuntimeError("Hardware test needs an initialized RGB matrix")
    for frame in diagnostic_frames():
        show(frame, "matrix", ROOT / "preview.png", matrix)
        time.sleep(pause)
    print("Hardware diagnostic frames sent: red, green, blue, AFL demo")


def demo_game():
    return {"id": 9999, "round": 10, "year": 2026, "hteam": 6, "ateam": 17,
            "hgoals": 12, "hbehinds": 8, "hscore": 80,
            "agoals": 9, "abehinds": 10, "ascore": 64,
            "complete": 64, "timestr": "Q3 14:26", "date": "2026-05-24T05:20:00Z",
            "_demo": True}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Australian rules football 64x32 RGB LED scoreboard")
    parser.add_argument("--driver", choices=("preview", "matrix"), default="preview")
    parser.add_argument("--once", action="store_true", help="Render one REST snapshot and exit")
    parser.add_argument("--demo", action="store_true", help="Render a demo without using Squiggle")
    parser.add_argument("--hardware-test", action="store_true", help="Show RGB diagnostic frames on a real Pi matrix")
    parser.add_argument("--year", type=int, default=datetime.now(ZoneInfo("Australia/Melbourne")).year)
    parser.add_argument("--favorite", help="Team name or code, e.g. FRE or Fremantle")
    parser.add_argument("--preview", type=Path, default=ROOT / "preview.png")
    parser.add_argument("--preview-style", choices=("hd", "pixel"), default="hd",
                        help="Sharp 1280x640 desktop view (default) or exact LED pixel simulation")
    parser.add_argument("--cache-dir", type=Path, default=CACHE,
                        help="Writable on-disk Squiggle cache path (set for Pi services)")
    parser.add_argument("--cache-minutes", type=int, default=30)
    parser.add_argument("--refresh-minutes", type=int, default=30, help="REST refresh interval; live scores use SSE")
    parser.add_argument("--rotate-seconds", type=int, default=15, help="Seconds between displayed games")
    parser.add_argument("--rotate-limit", type=int, default=6, help="Maximum games to include in rotation")
    parser.add_argument("--mapping", default="regular", help="e.g. regular or adafruit-hat")
    parser.add_argument("--brightness", type=int, default=55)
    parser.add_argument("--gpio-slowdown", type=int, default=2)
    args = parser.parse_args(argv)
    if args.cache_minutes < 5 or args.refresh_minutes < 5:
        parser.error("Do not poll Squiggle faster than every five minutes; live updates use SSE")
    if not 1 <= args.brightness <= 100:
        parser.error("Brightness must be 1..100")
    if not 2 <= args.rotate_seconds <= 3600 or not 1 <= args.rotate_limit <= 30:
        parser.error("Rotation settings must be 2..3600 seconds and 1..30 games")
    if args.hardware_test and args.driver != "matrix":
        parser.error("--hardware-test requires --driver matrix on a Raspberry Pi")
    try:
        verified_count = verify_all_logos()
    except MissingLogoError as exc:
        parser.error(str(exc))
    matrix = make_matrix(args) if args.driver == "matrix" else None
    if args.hardware_test:
        run_hardware_test(matrix)
        return 0
    if args.demo:
        demo = demo_game()
        show(draw_game(demo), args.driver, args.preview, matrix, demo, args.preview_style)
        return 0
    try:
        headers = contact_headers(os.environ.get("SQUIGGLE_CONTACT_EMAIL", ""))
    except ValueError as exc:
        parser.error(str(exc))
    # One REST request per resync window; display rotation never polls Squiggle.
    # A separate daemon consumes the single all-games SSE stream near kickoff.
    lock = threading.Lock()
    stop = threading.Event()
    state: dict[int, dict] = {}
    next_refresh = 0.0
    step = 0
    watcher = None
    try:
        while True:
            now = time.monotonic()
            if now >= next_refresh:
                try:
                    games = season_games(args.year, headers, args.cache_minutes, args.cache_dir)
                    with lock:
                        for game in games:
                            game_id = as_int(game.get("id"))
                            if game_id is not None:
                                # Keep more recent in-memory SSE score information for live games.
                                if game_id not in state or not is_live(state[game_id]):
                                    state[game_id] = game
                                else:
                                    for field, value in game.items():
                                        if field not in SCORE_KEYS + ("timestr", "complete", "winner"):
                                            state[game_id][field] = value
                except (RuntimeError, ValueError, OSError) as exc:
                    print(f"Scoreboard error: {exc}", file=sys.stderr)
                    if args.once and not state:
                        return 1
                next_refresh = now + args.refresh_minutes * 60
            with lock:
                snapshot = [dict(game) for game in state.values()]
            selected = rotation_choice(snapshot, step, args.favorite, args.rotate_limit)
            show(draw_game(selected), args.driver, args.preview, matrix, selected, args.preview_style)
            if args.once:
                return 0
            if watcher is None:
                watcher = threading.Thread(target=follow_events,
                                          args=(state, lock, stop, headers), daemon=True)
                watcher.start()
            step += 1
            stop.wait(args.rotate_seconds)
    finally:
        stop.set()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("Scoreboard stopped")