#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Self-contained, Python 2.7 / 3.7 compatible AFL HUB75 scoreboard for Pi Zero W.

Uses the original RGBMatrix/Pillow Python bindings. Does not import the newer
Python-3.10-only desktop app. Logo assets must be present; never show impostors.
"""
from __future__ import print_function

import argparse
from collections import deque
import errno
import json
import os
import re
import stat
import sys
import tempfile
import threading
import time
from datetime import datetime, timedelta
try:
    from urllib2 import Request, urlopen
except ImportError:  # Python 3 during tests
    from urllib.request import Request, urlopen

API = 'https://api.squiggle.com.au/?q=games;year=%s'
STANDINGS_API = 'https://api.squiggle.com.au/?q=standings;year=%s'
EVENTS = 'https://sse.squiggle.com.au/events'
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
TEAM_LIST = [
    (1, 'ADE', 'Adelaide', '#E31B23', 'Adelaide Crows'),
    (2, 'BRI', 'Brisbane', '#A21D4B', 'Brisbane Lions'),
    (3, 'CAR', 'Carlton', '#56C5D8', 'Carlton Blues'),
    (4, 'COL', 'Collingwood', '#FFFFFF', 'Collingwood Magpies'),
    (5, 'ESS', 'Essendon', '#ED1C24', 'Essendon Bombers'),
    (6, 'FRE', 'Fremantle', '#A62385', 'Fremantle Dockers'),
    (7, 'GEE', 'Geelong', '#99C8E0', 'Geelong Cats'),
    (8, 'GCS', 'Gold Coast', '#FFCA2F', 'Gold Coast Suns'),
    (9, 'GWS', 'GWS', '#F15A22', 'GWS Giants'),
    (10, 'HAW', 'Hawthorn', '#D9B16A', 'Hawthorn Hawks'),
    (11, 'MEL', 'Melbourne', '#DF1840', 'Melbourne Demons'),
    (12, 'NTH', 'North Melbourne', '#6DB2E8', 'North Melbourne Kangaroos'),
    (13, 'PTA', 'Port Adelaide', '#00ACB9', 'Port Adelaide Power'),
    (14, 'RIC', 'Richmond', '#FFD200', 'Richmond Tigers'),
    (15, 'STK', 'Stkilda', '#ED1C24', 'St Kilda Saints'),
    (16, 'SYD', 'Sydney', '#ED1C24', 'Sydney Swans'),
    (17, 'WCE', 'West Coast', '#F2CD27', 'West Coast Eagles'),
    (18, 'WBD', 'Western Bulldogs', '#4176CF', 'Western Bulldogs'),
]


def norm(text):
    return re.sub('[^a-z0-9]', '', str(text or '').lower())


def club(value):
    if value is None:
        raise ValueError('Missing Squiggle club')
    key = norm(value)
    if not key:
        raise ValueError('Empty Squiggle club')
    for team in TEAM_LIST:
        if key in [str(team[0]), norm(team[1]), norm(team[2]), norm(team[4])]:
            return team
        if team[0] == 9 and key in ('greaterwesternsydney', 'greaterwesternsydneygiants'):
            return team
        if team[0] == 15 and key in ('stkildasaints', 'stkilda'):
            return team
    raise ValueError('Unknown AFL club %r; a real logo is required' % (value,))


def match_favorite(game, favorite):
    if not favorite:
        return True
    needle = norm(favorite)
    try:
        return any(needle in (norm(str(t[0])), norm(t[1]), norm(t[2]), norm(t[4]))
                   for t in [club(game.get('hteam')), club(game.get('ateam'))])
    except ValueError:
        return False


def num(value):
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def score(game, side):
    goals, behinds, total = (num(game.get(side + x)) for x in ('goals', 'behinds', 'score'))
    if total is None and goals is not None and behinds is not None:
        total = 6 * goals + behinds
    gb = ('%s.%s' % (goals, behinds)) if goals is not None and behinds is not None else '-.-'
    return gb, '--' if total is None else str(total)


def live(game):
    value = num(game.get('complete')) or 0
    return value > 0 and value < 100


def status(game):
    if game.get('_demo'):
        return 'DEMO'
    if (num(game.get('complete')) or 0) >= 100:
        return 'FINAL'
    if live(game):
        text = str(game.get('timestr') or '').upper()
        match = re.search(r'Q[1-4]', text)
        return match.group(0) if match else 'LIVE'
    return 'NEXT'


def game_key(game):
    return str(game.get('date') or '')


def games_ranked(games, favorite, now=None):
    """Live first, upcoming next, then latest final. Uses AU-local date string."""
    if now is None:
        # A broad ordering fence: enough for season standings, not a game clock.
        now = datetime.utcnow() + timedelta(hours=10)
    today = now.strftime('%Y-%m-%d')
    selected = [g for g in games if match_favorite(g, favorite)]
    playing = sorted((g for g in selected if live(g)), key=game_key)
    upcoming = sorted((g for g in selected if (num(g.get('complete')) or 0) == 0
                       and game_key(g)[:10] >= today), key=game_key)
    final = sorted((g for g in selected if (num(g.get('complete')) or 0) >= 100),
                   key=game_key, reverse=True)
    return playing + upcoming + final


# Tiny 3x5 glyphs, carefully sized for the single 64x32 panel.
PIX = {
    '0': ('111', '101', '101', '101', '111'),
    '1': ('010', '110', '010', '010', '111'),
    '2': ('111', '001', '111', '100', '111'),
    '3': ('111', '001', '111', '001', '111'),
    '4': ('101', '101', '111', '001', '001'),
    '5': ('111', '100', '111', '001', '111'),
    '6': ('111', '100', '111', '101', '111'),
    '7': ('111', '001', '010', '010', '010'),
    '8': ('111', '101', '111', '101', '111'),
    '9': ('111', '101', '111', '001', '111'),
    'A': ('010', '101', '111', '101', '101'),
    'B': ('110', '101', '110', '101', '110'),
    'C': ('011', '100', '100', '100', '011'),
    'D': ('110', '101', '101', '101', '110'),
    'E': ('111', '100', '110', '100', '111'),
    'F': ('111', '100', '110', '100', '100'),
    'G': ('011', '100', '101', '101', '011'),
    'H': ('101', '101', '111', '101', '101'),
    'I': ('111', '010', '010', '010', '111'),
    'J': ('001', '001', '001', '101', '010'),
    'K': ('101', '101', '110', '101', '101'),
    'L': ('100', '100', '100', '100', '111'),
    'M': ('101', '111', '111', '101', '101'),
    'N': ('101', '111', '111', '111', '101'),
    'O': ('010', '101', '101', '101', '010'),
    'P': ('110', '101', '110', '100', '100'),
    'Q': ('010', '101', '101', '111', '011'),
    'R': ('110', '101', '110', '101', '101'),
    'S': ('011', '100', '010', '001', '110'),
    'T': ('111', '010', '010', '010', '010'),
    'U': ('101', '101', '101', '101', '111'),
    'V': ('101', '101', '101', '101', '010'),
    'W': ('101', '101', '111', '111', '101'),
    'X': ('101', '101', '010', '101', '101'),
    'Y': ('101', '101', '010', '010', '010'),
    'Z': ('111', '001', '010', '100', '111'),
    '.': ('000', '000', '000', '000', '010'),
    '-': ('000', '000', '111', '000', '000'),
    ' ': ('000', '000', '000', '000', '000'),
    '?': ('111', '001', '010', '000', '010'),
    '%': ('101', '001', '010', '100', '101'),
    '!': ('010', '010', '010', '000', '010')
}


def pixel_text(draw, x, y, text, color):
    for c in str(text).upper():
        for dy, bits in enumerate(PIX.get(c, PIX['?'])):
            for dx, val in enumerate(bits):
                if val == '1':
                    draw.point((x + dx, y + dy), fill=color)
        x += 4


def remove_light_logo_background(image):
    """Remove only light outer backdrop pixels, not white details inside crests.

    Some bundled club images are RGBA PNG files with fully opaque, pale-grey
    backgrounds despite their .bmp extension. On an LED panel those become
    glaring white rectangles. Flood filling from the edges avoids erasing
    white text and features enclosed inside each club crest.
    """
    from collections import deque
    rgba = image.convert('RGBA')
    px = rgba.load()
    width, height = rgba.size

    def light_background(x, y):
        r, g, b, alpha = px[x, y]
        return alpha > 0 and min(r, g, b) >= 185 and max(r, g, b) - min(r, g, b) <= 58

    pending = deque()
    seen = set()

    def add(x, y):
        if (x, y) not in seen and light_background(x, y):
            seen.add((x, y))
            pending.append((x, y))

    for x in range(width):
        add(x, 0)
        add(x, height - 1)
    for y in range(height):
        add(0, y)
        add(width - 1, y)

    while pending:
        x, y = pending.popleft()
        r, g, b, _ = px[x, y]
        px[x, y] = (r, g, b, 0)
        if x > 0:
            add(x - 1, y)
        if x + 1 < width:
            add(x + 1, y)
        if y > 0:
            add(x, y - 1)
        if y + 1 < height:
            add(x, y + 1)

    return rgba


def compact_logo_art(image_class, original, size):
    """Make a 16px LED icon from the emblem, not the 32px emblem + wordmark.

    The bundled club crests have tiny lettering at the bottom; when shrunk
    unchanged it becomes an unreadable, bright rectangle. The larger 32px
    original remains untouched and only this Pi Zero rendering is adapted.
    """
    alpha = remove_light_logo_background(original)
    if alpha.size[0] >= 24 and alpha.size[1] >= 24:
        alpha = alpha.crop((0, 0, alpha.size[0],
                            max(1, int(alpha.size[1] * 0.78))))
    bounds = alpha.split()[-1].getbbox()
    if bounds is None:
        raise IOError('Club logo contains no visible emblem')
    alpha = alpha.crop(bounds)
    quality = getattr(image_class, 'LANCZOS', getattr(image_class, 'ANTIALIAS', 1))
    alpha.thumbnail((size, size), quality)
    output = image_class.new('RGBA', (size, size), (0, 0, 0, 0))
    output.paste(alpha, ((size - alpha.size[0]) // 2,
                         (size - alpha.size[1]) // 2))
    px = output.load()
    for y in range(size):
        for x in range(size):
            r, g, b, opacity = px[x, y]
            if opacity < 110:
                px[x, y] = (0, 0, 0, 0)
                continue
            spread = max(r, g, b) - min(r, g, b)
            # White logo details remain visible, but no longer overpower
            # a low-brightness physical HUB75 panel.
            if min(r, g, b) > 185 and spread < 50:
                r, g, b = int(r * 0.72), int(g * 0.72), int(b * 0.72)
            elif spread > 35 and max(r, g, b) < 155:
                r = min(255, int(r * 1.25))
                g = min(255, int(g * 1.25))
                b = min(255, int(b * 1.25))
            px[x, y] = (r, g, b, opacity)
    return output


def outline_fremantle_shield(image):
    """Preserve the original anchor crest while dimming the large purple fill.

    On a 16px HUB75 panel a fully bright purple shield reads as a rectangle.
    Reduce only interior purple pixels, retain the outer outline, and gently
    lift the near-white anchor strokes. Other club emblems are unchanged.
    """
    source = image.convert('RGBA')
    original = source.copy().load()
    px = source.load()
    width, height = source.size
    for y in range(height):
        for x in range(width):
            r, g, b, a = original[x, y]
            if a < 110:
                continue
            purple = b > max(65, r * 1.3) and b > g * 1.5 and g < 105
            if purple:
                boundary = (x == 0 or y == 0 or x == width - 1 or
                            y == height - 1)
                if not boundary:
                    for nx, ny in ((x-1, y), (x+1, y),
                                   (x, y-1), (x, y+1)):
                        if original[nx, ny][3] < 110:
                            boundary = True
                            break
                if boundary:
                    px[x, y] = (min(130, max(78, int(r * 1.5))),
                                min(55, int(g * 1.5)),
                                min(185, int(b * 1.4)), a)
                else:
                    px[x, y] = (max(7, int(r * 0.25)),
                                max(1, int(g * 0.20)),
                                max(18, int(b * 0.27)), a)
            elif min(r, g, b) >= 100 and max(r, g, b)-min(r, g, b) < 55:
                px[x, y] = (min(225, int(r * 1.18)),
                            min(225, int(g * 1.18)),
                            min(225, int(b * 1.18)), a)
    return source


def logo(image_class, name, size=16, directory=None):
    path = os.path.join(directory or os.path.join(BASE, 'logos'), name + '.bmp')
    if not os.path.isfile(path):
        raise IOError('MANDATORY club logo missing: %s' % path)
    with image_class.open(path) as original:
        if original.size[0] < 12 or original.size[1] < 12:
            raise IOError('Club logo too small: %s' % path)
        icon = compact_logo_art(image_class, original, size)
        return outline_fremantle_shield(icon) if name == 'Fremantle' else icon


# A 64x32 panel can accommodate exactly two 16px-tall crests. Give each
# team half the height, with its abbreviation/status above its AFL score.
# All text is drawn at native pixel resolution (never scaled/blurred).
BIG_NUMBERS = {
    '0': ('01110', '10001', '10011', '10101', '11001', '10001', '01110'),
    '1': ('00100', '01100', '00100', '00100', '00100', '00100', '01110'),
    '2': ('01110', '10001', '00001', '00010', '00100', '01000', '11111'),
    '3': ('11110', '00001', '00001', '01110', '00001', '00001', '11110'),
    '4': ('00010', '00110', '01010', '10010', '11111', '00010', '00010'),
    '5': ('11111', '10000', '10000', '11110', '00001', '00001', '11110'),
    '6': ('01110', '10000', '10000', '11110', '10001', '10001', '01110'),
    '7': ('11111', '00001', '00010', '00100', '01000', '01000', '01000'),
    '8': ('01110', '10001', '10001', '01110', '10001', '10001', '01110'),
    '9': ('01110', '10001', '10001', '01111', '00001', '00001', '01110'),
    '-': ('00000', '00000', '00000', '11111', '00000', '00000', '00000'),
}


def big_score(draw, right, y, text, color):
    """Right-justify the points total using 5x7 digits, never beyond x=63."""
    text = str(text)[:3]
    start = right - len(text) * 6
    for offset, char in enumerate(text):
        bitmap = BIG_NUMBERS.get(char, BIG_NUMBERS['-'])
        for dy, row in enumerate(bitmap):
            for dx, value in enumerate(row):
                if value == '1':
                    draw.point((start + offset * 6 + dx, y + dy), fill=color)


def draw_game(game, logo_dir=None):
    from PIL import Image, ImageDraw
    frame = Image.new('RGB', (64, 32), (0, 0, 0))
    d = ImageDraw.Draw(frame)
    if not game:
        pixel_text(d, 6, 13, 'NO AFL GAMES', '#FFFFFF')
        return frame

    # Each row is 16 pixels high. Crest occupies x=0..15, and everything
    # else starts after the colored separator at x=16.
    for y, key, side in ((0, 'hteam', 'h'), (16, 'ateam', 'a')):
        team = club(game.get(key))
        crest = logo(Image, team[2], 16, logo_dir)
        frame.paste(crest, (0, y), crest)
        d.line((16, y + 1, 16, y + 14), fill=team[3])
        pixel_text(d, 18, y + 2, team[1], team[3])
        if y == 0:
            match_state = status(game)[:7]
            state_color = '#31C8E8' if game.get('_demo') else '#FFD34D'
            pixel_text(d, 34, y + 2, match_state, state_color)
        else:
            pixel_text(d, 34, y + 2,
                       ('R%s' % str(game.get('round', '-'))[:2])[:7], '#54D0FF')
        goals_behinds, points = score(game, side)
        # Leave a space between the 3x5 goals.behinds and large 5x7 points.
        pixel_text(d, 18, y + 9, goals_behinds[:6], '#BDCBDC')
        big_score(d, 64, y + 8, points, '#FFFFFF')
    d.line((17, 15, 63, 15), fill='#27303C')
    return frame


def pixel_text_scaled(draw, x, y, text, color, scale=2):
    """A crisp, native-pixel 2x glyph for goal celebrations."""
    for char in str(text).upper():
        for dy, row in enumerate(PIX.get(char, PIX['?'])):
            for dx, bit in enumerate(row):
                if bit == '1':
                    left, top = x + dx * scale, y + dy * scale
                    draw.rectangle((left, top, left + scale - 1,
                                    top + scale - 1), fill=color)
        x += 4 * scale


def draw_goal_frame(alert, phase, logo_dir=None):
    """Render one 64x32 goal flash with the actual scoring club's crest."""
    from PIL import Image, ImageDraw
    team = club(alert['team'])
    frame = Image.new('RGB', (64, 32), (0, 0, 0))
    draw = ImageDraw.Draw(frame)
    bright = phase % 2 == 0
    color = team[3]
    # Never fill the entire matrix; keep it legible and low-glare.
    outline = color if bright else '#242631'
    draw.rectangle((0, 0, 63, 31), outline=outline)
    crest = logo(Image, team[2], 20, logo_dir)
    frame.paste(crest, (2, 6), crest)
    pixel_text_scaled(draw, 24, 4, 'GOAL!',
                      '#FFE26B' if bright else '#A4B2D0', 2)
    pixel_text(draw, 27, 23, team[1], color)
    big_score(draw, 64, 21, alert.get('total', '--'), '#E3EAF4')
    if bright:
        for x, y in ((7, 2), (18, 3), (6, 28), (19, 28), (59, 2)):
            draw.point((x, y), fill='#FFE26B')
    return frame


def show_goal_animation(matrix, alert, stop=None):
    """Short animation followed by normal scoreboard restoration by caller."""
    for phase in range(6):
        if stop is not None and stop.is_set():
            break
        matrix.SetImage(draw_goal_frame(alert, phase))
        if stop is not None:
            if stop.wait(0.36):
                break
        else:
            time.sleep(0.36)


def goal_from_event(previous, current, ev_type, payload):
    """Only a genuine NEW Squiggle SSE goal can trigger an animation.

    A first game snapshot, a behind, stale replay, score correction or final
    fixture must not celebrate. Never infer goals from points-only changes.
    """
    if (ev_type != 'score' or not isinstance(payload, dict) or
            str(payload.get('type') or '').lower() != 'goal' or
            not isinstance(previous, dict) or not isinstance(current, dict) or
            not live(current)):
        return None
    side = payload.get('side')
    if side not in ('hteam', 'ateam'):
        return None
    score_side = 'h' if side == 'hteam' else 'a'
    old_goals = num(previous.get(score_side + 'goals'))
    new_goals = num(current.get(score_side + 'goals'))
    if old_goals is None or new_goals is None or new_goals <= old_goals:
        return None
    if (num(previous.get('complete')) or 0) >= 100:
        return None
    try:
        team = club(current.get(side))
    except ValueError:
        return None
    scorer = num(payload.get('team'))
    if scorer is not None and scorer != team[0]:
        return None
    return {'team': team[2], 'code': team[1], 'game_id': num(current.get('id')),
            'total': score(current, score_side)[1]}


def update_live_state(state, ev_type, payload, alerts, favorite=None,
                      disable_goals=False):
    """Merge SSE payload once and queue at most one alert for each goal."""
    game_id = num(payload.get('id' if ev_type == 'game' else 'gameid')) if isinstance(payload, dict) else None
    previous = dict(state[game_id]) if game_id in state else None
    if not apply_event(state, ev_type, payload):
        return False
    if alerts is None:
        return False
    current = state.get(game_id)
    alert = None if disable_goals else goal_from_event(
        previous, current, ev_type, payload)
    if alert is None:
        alert = final_from_transition(previous, current)
    if alert is not None and match_favorite(current, favorite):
        alerts.append(alert)
        return True
    return False


def final_from_transition(previous, current):
    """Celebrate only a known match transitioning from LIVE to FINAL.

    This deliberately does not animate historic results, startup snapshots,
    late repeats, a match that never started, or matches without known scores.
    """
    if (not isinstance(previous, dict) or not isinstance(current, dict)
            or not live(previous)
            or (num(current.get('complete')) or 0) < 100):
        return None
    home = num(current.get('hscore'))
    away = num(current.get('ascore'))
    if home is None or away is None or home < 0 or away < 0:
        return None
    try:
        home_team = club(current.get('hteam'))
        away_team = club(current.get('ateam'))
    except ValueError:
        return None
    winner = home_team if home > away else away_team if away > home else None
    return {'kind': 'final', 'game_id': num(current.get('id')),
            'winner': winner[2] if winner else None,
            'code': winner[1] if winner else 'DRAW',
            'hteam': home_team[2], 'ateam': away_team[2],
            'home': home, 'away': away, 'margin': abs(home - away)}


def draw_final_frame(alert, phase, logo_dir=None):
    """Pixel-perfect full-time celebration on one 64x32 HUB75 panel."""
    from PIL import Image, ImageDraw
    frame = Image.new('RGB', (64, 32), (0, 0, 0))
    draw = ImageDraw.Draw(frame)
    winner = club(alert['winner']) if alert.get('winner') else None
    color = winner[3] if winner else '#54D0FF'
    draw.rectangle((0, 0, 63, 31), outline=color if phase % 2 == 0 else '#283040')
    if winner is not None:
        crest = logo(Image, winner[2], 20, logo_dir)
        frame.paste(crest, (1, 6), crest)
    else:
        home_crest = logo(Image, club(alert['hteam'])[2], 12, logo_dir)
        away_crest = logo(Image, club(alert['ateam'])[2], 12, logo_dir)
        frame.paste(home_crest, (2, 2), home_crest)
        frame.paste(away_crest, (2, 18), away_crest)
    pixel_text(draw, 26, 2, 'FULL TIME', '#FFF0A8' if phase % 2 == 0 else '#92B6D8')
    pixel_text(draw, 27, 12, winner[1] if winner else 'DRAW', color)
    result = ('BY %d' % alert['margin']) if winner else ('%d-%d' % (alert['home'], alert['away']))
    pixel_text(draw, 27, 22, result[:9], '#FFFFFF')
    return frame


def show_final_animation(matrix, alert, stop=None):
    for phase in range(8):
        if stop is not None and stop.is_set():
            break
        matrix.SetImage(draw_final_frame(alert, phase))
        if stop is not None:
            if stop.wait(0.40):
                break
        else:
            time.sleep(0.40)


def normalize_standings(data):
    """Validate real Squiggle standings; no invented ranks or points."""
    if not isinstance(data, dict) or not isinstance(data.get('standings'), list):
        raise ValueError('Squiggle did not return standings')
    rows = []
    used_teams, used_ranks = set(), set()
    for item in data['standings']:
        if not isinstance(item, dict):
            continue
        rank, pts = num(item.get('rank')), num(item.get('pts'))
        wins = num(item.get('wins'))
        if rank is None or not 1 <= rank <= 18 or pts is None or pts < 0:
            continue
        try:
            team = club(item.get('id') if item.get('id') is not None else item.get('name'))
            pct = float(item['percentage'])
        except (ValueError, TypeError, KeyError):
            continue
        if pct < 0 or pct > 2000 or pct != pct or team[0] in used_teams or rank in used_ranks:
            continue
        used_teams.add(team[0])
        used_ranks.add(rank)
        rows.append({'rank': rank, 'team': team[2], 'code': team[1],
                     'pts': pts, 'percentage': pct, 'wins': wins})
    rows.sort(key=lambda row: row['rank'])
    return rows


def standings_path(year):
    return os.path.join(os.path.dirname(cache_path(year)),
                        'pi_zero_standings_%s.json' % year)


def get_standings(year, headers, cache_minutes=60):
    """Fetch the ACTUAL AFL ladder (q=standings, NOT predictive q=ladder)."""
    path = standings_path(year)
    if os.path.isfile(path) and time.time() - os.stat(path).st_mtime < cache_minutes * 60:
        with open(path, 'r') as stream:
            return normalize_standings(json.load(stream))
    try:
        response = urlopen(Request(STANDINGS_API % year, headers=headers), timeout=20)
        try:
            parsed = json.loads(response.read().decode('utf-8'))
        finally:
            response.close()
        standings = normalize_standings(parsed)
        if not standings:
            raise ValueError('Squiggle returned no valid ladder positions')
        tmp = path + '.part'
        with open(tmp, 'w') as stream:
            json.dump(parsed, stream)
        os.rename(tmp, path)
        return standings
    except Exception as exc:
        if os.path.isfile(path):
            print('WARNING: Showing stale AFL ladder (%s)' % exc, file=sys.stderr)
            with open(path, 'r') as stream:
                return normalize_standings(json.load(stream))
        raise


def draw_ladder_frame(rows, page, logo_dir=None):
    """Two complete 16px team-crest rows per page, across all 18 teams."""
    from PIL import Image, ImageDraw
    frame = Image.new('RGB', (64, 32), (0, 0, 0))
    draw = ImageDraw.Draw(frame)
    if not rows:
        pixel_text(draw, 2, 10, 'NO LADDER DATA', '#D9B16A')
        return frame
    start = (page % ((len(rows) + 1) // 2)) * 2
    for slot, row in enumerate(rows[start:start + 2]):
        y = 16 * slot
        team = club(row['team'])
        crest = logo(Image, team[2], 16, logo_dir)
        frame.paste(crest, (0, y), crest)
        draw.line((16, y + 1, 16, y + 14), fill=team[3])
        pixel_text(draw, 18, y + 1, '%02d' % row['rank'], '#FFFFFF')
        pixel_text(draw, 28, y + 1, team[1], team[3])
        pixel_text(draw, 47, y + 1, 'P', '#99C1D1')
        points = str(row['pts'])[:3]
        pixel_text(draw, 64 - 4 * len(points), y + 1, points, '#FFFFFF')
        if row['wins'] is not None:
            pixel_text(draw, 18, y + 9, 'W%d' % row['wins'], '#B8D5E3')
        pct = ('%d%%' % int(round(row['percentage'])))[:6]
        pixel_text(draw, 64 - 4 * len(pct), y + 9, pct, '#B8D5E3')
    draw.line((17, 15, 63, 15), fill='#27303C')
    return frame


def draw_ladder_intro(demo=False):
    from PIL import Image, ImageDraw
    frame = Image.new('RGB', (64, 32), (0, 0, 0))
    draw = ImageDraw.Draw(frame)
    pixel_text_scaled(draw, 7, 2, 'AFL', '#63CFFF', 2)
    pixel_text_scaled(draw, 7, 17, 'LADDER', '#FFDD66', 2)
    if demo:
        pixel_text(draw, 46, 2, 'DEMO', '#CD86E9')
    return frame


def demo_standings():
    """Synthetic numbers are restricted to explicitly labelled offline demos."""
    return normalize_standings({'standings': [
        {'id': 6, 'rank': 1, 'pts': 64, 'wins': 16, 'percentage': 137.3},
        {'id': 17, 'rank': 2, 'pts': 60, 'wins': 15, 'percentage': 125.0},
        {'id': 2, 'rank': 3, 'pts': 56, 'wins': 14, 'percentage': 117.4},
        {'id': 14, 'rank': 4, 'pts': 52, 'wins': 13, 'percentage': 114.2}]})


def demo_game():
    return {'id': 0, 'round': 10, 'hteam': 'Fremantle', 'ateam': 'West Coast',
            'hgoals': 12, 'hbehinds': 8, 'hscore': 80,
            'agoals': 9, 'abehinds': 10, 'ascore': 64,
            'complete': 64, 'timestr': 'Q3 14:26', '_demo': True}


def verify_logos(directory=None):
    for team in TEAM_LIST:
        from PIL import Image
        logo(Image, team[2], 16, directory)
    return 18


def contact(email):
    if not re.match(r'^[^\s@]+@[^\s@]+\.[^\s@]+$', email or ''):
        raise ValueError('Set a real contact email with --email or local AFL email configuration')
    return {'User-Agent': 'AFL LED Scoreboard (github.com/acerbzzz/afl-led-scoreboard; %s)' % email,
            'Accept': 'application/json'}


def read_email(explicit=None):
    if explicit:
        return explicit
    e = os.environ.get('SQUIGGLE_CONTACT_EMAIL', '')
    if e:
        return e
    # Root-owned file created by install_pi_zero.sh; no email is in Git.
    path = '/etc/afl-led-scoreboard-contact'
    if os.path.isfile(path):
        with open(path, 'r') as f:
            return f.read().strip()
    return ''


def cache_path(year):
    """Use a private writable cache even after RGBMatrix drops privileges.

    The Pi driver starts with root permissions, but later runs as a restricted
    account. The Git checkout belongs to 'pi', so writing BASE/.cache fails.
    A UID-specific directory in the system temp area avoids chmod/chown on
    project files and preserves stale-cache fallback during normal operation.
    """
    uid = os.geteuid()
    directory = os.path.join(tempfile.gettempdir(),
                             'afl-led-scoreboard-cache-%s' % uid)
    try:
        os.makedirs(directory, 0o700)
    except OSError as exc:
        if exc.errno != errno.EEXIST:
            raise
    # Do not follow a hostile /tmp symlink or share other users' files.
    info = os.lstat(directory)
    if (not stat.S_ISDIR(info.st_mode) or info.st_uid != uid or
            stat.S_IMODE(info.st_mode) & 0o077):
        raise IOError('AFL cache directory must be private to the running user')
    return os.path.join(directory, 'pi_zero_games_%s.json' % year)


def get_season(year, headers, cache_minutes=30):
    path = cache_path(year)
    if os.path.isfile(path) and time.time() - os.stat(path).st_mtime < cache_minutes * 60:
        with open(path, 'r') as f:
            return json.load(f)
    try:
        req = Request(API % year, headers=headers)
        resp = urlopen(req, timeout=20)
        try:
            data = json.loads(resp.read().decode('utf-8'))
        finally:
            resp.close()
        if not isinstance(data, dict):
            raise ValueError('Invalid Squiggle response')
        games = data.get('games')
        if not isinstance(games, list):
            raise ValueError('Invalid Squiggle games response')
        tmp = path + '.part'
        with open(tmp, 'w') as f:
            json.dump(games, f)
        os.rename(tmp, path)
        return games
    except Exception as exc:
        if os.path.isfile(path):
            print('WARNING: Squiggle unavailable; displaying stale cached games (%s)' % exc, file=sys.stderr)
            with open(path, 'r') as f:
                return json.load(f)
        raise


def event_messages(lines):
    event, data = 'message', []
    for raw in lines:
        if not isinstance(raw, str):
            raw = raw.decode('utf-8', 'replace')
        line = raw.strip('\r\n')
        if not line:
            if data:
                try:
                    yield event, json.loads('\n'.join(data))
                except ValueError:
                    pass
            event, data = 'message', []
        elif line.startswith('event:'):
            event = line[6:].strip()
        elif line.startswith('data:'):
            data.append(line[5:].lstrip())
    if data:
        try:
            yield event, json.loads('\n'.join(data))
        except ValueError:
            pass


def apply_event(state, event, payload):
    if not isinstance(payload, dict):
        return False
    game_id = num(payload.get('id' if event == 'game' else 'gameid'))
    if game_id is None:
        return False
    if event == 'game':
        state[game_id] = payload
        return True
    if game_id not in state:
        return False
    target = state[game_id]
    if event == 'score':
        details = payload.get('score')
        if isinstance(details, dict):
            for k in ('hscore', 'ascore', 'hgoals', 'agoals', 'hbehinds', 'abehinds'):
                if k in details:
                    target[k] = details[k]
        for k in ('complete', 'timestr'):
            if k in payload:
                target[k] = payload[k]
        return True
    if event in ('timestr', 'complete'):
        if event in payload:
            target[event] = payload[event]
        return True
    return False


def watch_needed(games):
    if any(live(g) for g in games):
        return True
    now = datetime.utcnow() + timedelta(hours=10)
    for g in games:
        if num(g.get('complete')) in (None, 0):
            text = str(g.get('date') or '')[:19].replace('T', ' ')
            try:
                dt = datetime.strptime(text, '%Y-%m-%d %H:%M:%S')
            except ValueError:
                continue
            if -timedelta(hours=2) <= dt - now <= timedelta(hours=1):
                return True
    return False


def event_worker(state, lock, stop, headers, alerts=None, wakeup=None,
                 favorite=None, disable_goals=False):
    hdr = dict(headers)
    hdr['Accept'] = 'text/event-stream'
    while not stop.is_set():
        with lock:
            active = watch_needed(list(state.values()))
        if not active:
            stop.wait(30)
            continue
        try:
            response = urlopen(Request(EVENTS, headers=hdr), timeout=90)
            try:
                for ev_type, payload in event_messages(response):
                    if stop.is_set():
                        break
                    with lock:
                        new_goal = update_live_state(
                            state, ev_type, payload, alerts, favorite,
                            disable_goals)
                        if new_goal and wakeup is not None:
                            wakeup.set()
            finally:
                response.close()
        except Exception as exc:
            print('Squiggle event stream reconnect: %s' % exc, file=sys.stderr)
        stop.wait(10)


def create_matrix(args):
    from rgbmatrix import RGBMatrix, RGBMatrixOptions
    options = RGBMatrixOptions()
    for key, value in (('rows', 32), ('cols', 64), ('chain_length', 1),
                       ('parallel', 1), ('hardware_mapping', 'regular'),
                       ('brightness', args.brightness), ('gpio_slowdown', args.slowdown)):
        setattr(options, key, value)
    for key, value in (('multiplexing', args.multiplexing), ('row_address_type', args.row_addr_type),
                       ('scan_mode', args.scan_mode)):
        if value != 0:
            if not hasattr(options, key):
                raise RuntimeError('Installed rgbmatrix bindings do not support %s; test using C++ demo' % key)
            setattr(options, key, value)
    return RGBMatrix(options=options)


def main(argv=None):
    parser = argparse.ArgumentParser(description='AFL LED scoreboard for original Pi Zero W (Python 2.7)')
    parser.add_argument('--demo', action='store_true', help='Clearly labelled synthetic test')
    parser.add_argument('--demo-upgrades', action='store_true',
                        help='Offline final-siren plus ladder demo, using simulated data')
    parser.add_argument('--ladder-only', action='store_true',
                        help='Rotate through all real AFL ladder positions')
    parser.add_argument('--ladder-every', type=int, default=0,
                        help='Show the next ladder page every N match screens; 0 disables')
    parser.add_argument('--demo-goal', action='store_true',
                        help='Show an offline goal animation without live scores')
    parser.add_argument('--no-goal-animation', action='store_true',
                        help='Disable celebrations for live score events')
    parser.add_argument('--once', action='store_true', help='Draw one real fixture and exit after 20s')
    parser.add_argument('--preview', action='store_true', help='Write a 640x320 PNG without GPIO')
    parser.add_argument('--email', help='Squiggle identification email (not saved in Git)')
    parser.add_argument('--year', type=int, default=datetime.utcnow().year)
    parser.add_argument('--favorite', default=None, help='e.g. FRE')
    parser.add_argument('--rotate-seconds', type=int, default=15)
    parser.add_argument('--brightness', type=int, default=25)
    parser.add_argument('--slowdown', type=int, default=2)
    parser.add_argument('--multiplexing', type=int, default=0)
    parser.add_argument('--row-addr-type', type=int, default=0)
    parser.add_argument('--scan-mode', type=int, default=0)
    args = parser.parse_args(argv)
    if not 2000 <= args.year <= 2100:
        parser.error('Invalid AFL season year')
    if args.ladder_every < 0 or args.ladder_every > 99:
        parser.error('Use --ladder-every 0..99')
    if args.rotate_seconds < 5 or not 1 <= args.brightness <= 100:
        parser.error('Rotate interval >=5 seconds and brightness 1..100 required')
    try:
        verify_logos()
        # Read the root-owned Squiggle contact file BEFORE RGBMatrix starts.
        # The matrix driver can drop privileges to 'daemon' during init,
        # making /etc/afl-led-scoreboard-contact (mode 0600) unreadable.
        # Offline demo mode never requires the contact file.
        headers = None if (args.demo or args.demo_goal or args.demo_upgrades) else contact(read_email(args.email))
        matrix = None if args.preview else create_matrix(args)
        if args.demo or args.demo_goal or args.demo_upgrades:
            demo = demo_game()
            frame = draw_game(demo)
            if args.preview:
                from PIL import Image
                frame.resize((640, 320), Image.NEAREST).save(os.path.join(BASE, 'pi_zero_preview.png'))
                if args.demo_goal:
                    result = draw_goal_frame({'team': 'Fremantle', 'total': '86'}, 0)
                    result.resize((640, 320), Image.NEAREST).save(
                        os.path.join(BASE, 'pi_zero_goal_preview.png'))
                    print('Wrote pi_zero_goal_preview.png; simulated goal only')
                elif args.demo_upgrades:
                    finished = dict(demo, complete=100)
                    final = draw_final_frame(final_from_transition(demo, finished), 0)
                    final.resize((640, 320), Image.NEAREST).save(
                        os.path.join(BASE, 'pi_zero_final_preview.png'))
                    ladder = draw_ladder_frame(demo_standings(), 0)
                    ladder.resize((640, 320), Image.NEAREST).save(
                        os.path.join(BASE, 'pi_zero_ladder_preview.png'))
                    print('Wrote simulated final and ladder previews (no live data)')
                else:
                    print('Wrote pi_zero_preview.png; demo scores only')
            elif args.demo_upgrades:
                from PIL import Image
                print('SIMULATED FINAL and LADDER; no Squiggle connection.')
                matrix.SetImage(frame)
                time.sleep(1)
                finished = dict(demo, complete=100, hscore=80, ascore=64)
                alert = final_from_transition(demo, finished)
                show_final_animation(matrix, alert)
                rows = demo_standings()
                matrix.SetImage(draw_ladder_intro(demo=True))
                time.sleep(1.5)
                for page in range(2):
                    matrix.SetImage(draw_ladder_frame(rows, page))
                    time.sleep(4)
                matrix.SetImage(frame)
                time.sleep(3)
                matrix.Clear()
            elif args.demo_goal:
                matrix.SetImage(frame)
                time.sleep(1)
                print('SIMULATED Fremantle goal; no live data.')
                show_goal_animation(matrix, {'team': 'Fremantle', 'total': '86'})
                demo.update({'hgoals': 13, 'hscore': 86})
                matrix.SetImage(draw_game(demo))
                time.sleep(5)
                matrix.Clear()
            else:
                matrix.SetImage(frame)
                print('AFL DEMO is on the matrix for 20 seconds (no live data).')
                time.sleep(20)
                matrix.Clear()
            return 0
        lock = threading.RLock()
        stop = threading.Event()
        alerts = deque(maxlen=5)
        wakeup = threading.Event()
        state = {}
        standings = []
        last_standings_fetch = 0
        ladder_page = 0
        worker = None
        last_fetch = 0
        turn = 0
        while True:
            if (args.ladder_only or args.ladder_every) and time.time() - last_standings_fetch >= 60 * 60:
                try:
                    standings = get_standings(args.year, headers)
                except Exception as exc:
                    print('AFL ladder fetch failed: %s' % exc, file=sys.stderr)
                last_standings_fetch = time.time()
            if not args.ladder_only and time.time() - last_fetch >= 30 * 60:
                try:
                    games = get_season(args.year, headers)
                    with lock:
                        for g in games:
                            game_id = num(g.get('id'))
                            if game_id is None:
                                continue
                            if game_id not in state or not live(state[game_id]):
                                state[game_id] = g
                            else:
                                for k, v in g.items():
                                    if k not in ('hscore', 'ascore', 'hgoals', 'agoals', 'hbehinds', 'abehinds', 'complete', 'timestr'):
                                        state[game_id][k] = v
                except Exception as exc:
                    print('Squiggle fixture fetch failed: %s' % exc, file=sys.stderr)
                    if args.once and not state:
                        return 1
                last_fetch = time.time()
            with lock:
                next_goal = alerts.popleft() if alerts else None
            if next_goal is not None:
                if next_goal.get('kind') == 'final':
                    print('FINAL SIREN: %s (game %s)' % (
                        next_goal['code'], next_goal['game_id']))
                    if not args.preview:
                        show_final_animation(matrix, next_goal, stop)
                else:
                    print('GOAL: %s (game %s)' % (
                        next_goal['code'], next_goal['game_id']))
                    if not args.preview:
                        show_goal_animation(matrix, next_goal, stop)
            with lock:
                pool = games_ranked(list(state.values()), args.favorite)
                chosen = dict(pool[turn % min(6, len(pool))]) if pool else None
            show_ladder = args.ladder_only or (args.ladder_every > 0
                             and turn > 0 and turn % (args.ladder_every + 1)
                             == args.ladder_every)
            if show_ladder:
                frame = draw_ladder_frame(standings, ladder_page)
                print('AFL LADDER page %s, season %s' %
                      (ladder_page + 1, args.year))
                ladder_page += 1
            else:
                frame = draw_game(chosen)
            if args.preview:
                from PIL import Image
                frame.resize((640, 320), Image.NEAREST).save(os.path.join(BASE, 'pi_zero_preview.png'))
            else:
                matrix.SetImage(frame)
            if not show_ladder:
                print('AFL %s: %s vs %s' % (
                    status(chosen) if chosen else 'NONE',
                    chosen.get('hteam') if chosen else '-',
                    chosen.get('ateam') if chosen else '-'))
            if args.once:
                if not args.preview:
                    time.sleep(20)
                    matrix.Clear()
                return 0
            if not args.ladder_only and worker is None:
                worker = threading.Thread(target=event_worker, args=(
                    state, lock, stop, headers,
                    alerts, wakeup, args.favorite, args.no_goal_animation))
                worker.daemon = True
                worker.start()
            turn += 1
            with lock:
                have_pending_goal = bool(alerts)
                if not have_pending_goal:
                    wakeup.clear()
            if not have_pending_goal:
                wakeup.wait(args.rotate_seconds)
    except KeyboardInterrupt:
        return 0
    except Exception as exc:
        print('AFL error: %s' % exc, file=sys.stderr)
        return 1
    finally:
        if 'matrix' in locals() and matrix is not None:
            matrix.Clear()
        if 'stop' in locals():
            stop.set()
    return 0


if __name__ == '__main__':
    sys.exit(main())
