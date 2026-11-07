#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Self-contained, Python 2.7 / 3.7 compatible AFL HUB75 scoreboard for Pi Zero W.

Uses the original RGBMatrix/Pillow Python bindings. Does not import the newer
Python-3.10-only desktop app. Logo assets must be present; never show impostors.
"""
from __future__ import print_function

import argparse
import json
import os
import re
import sys
import threading
import time
from datetime import datetime, timedelta
try:
    from urllib2 import Request, urlopen
except ImportError:  # Python 3 during tests
    from urllib.request import Request, urlopen

API = 'https://api.squiggle.com.au/?q=games;year=%s'
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
    '?': ('111', '001', '010', '000', '010')
}


def pixel_text(draw, x, y, text, color):
    for c in str(text).upper():
        for dy, bits in enumerate(PIX.get(c, PIX['?'])):
            for dx, val in enumerate(bits):
                if val == '1':
                    draw.point((x + dx, y + dy), fill=color)
        x += 4


def logo(image_class, name, size=16, directory=None):
    path = os.path.join(directory or os.path.join(BASE, 'logos'), name + '.bmp')
    if not os.path.isfile(path):
        raise IOError('MANDATORY club logo missing: %s' % path)
    with image_class.open(path) as original:
        if original.size[0] < 12 or original.size[1] < 12:
            raise IOError('Club logo too small: %s' % path)
        alpha = original.convert('RGBA')
        quality = getattr(image_class, 'LANCZOS', getattr(image_class, 'ANTIALIAS', 1))
        alpha.thumbnail((size, size), quality)
        output = image_class.new('RGBA', (size, size), (0, 0, 0, 0))
        output.paste(alpha, ((size - alpha.size[0]) // 2,
                             (size - alpha.size[1]) // 2))
        return output


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
    directory = os.path.join(BASE, '.cache')
    if not os.path.isdir(directory):
        os.makedirs(directory)
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


def event_worker(state, lock, stop, headers):
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
                        apply_event(state, ev_type, payload)
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
    if args.rotate_seconds < 5 or not 1 <= args.brightness <= 100:
        parser.error('Rotate interval >=5 seconds and brightness 1..100 required')
    try:
        verify_logos()
        matrix = None if args.preview else create_matrix(args)
        if args.demo:
            frame = draw_game(demo_game())
            if args.preview:
                from PIL import Image
                frame.resize((640, 320), Image.NEAREST).save(os.path.join(BASE, 'pi_zero_preview.png'))
                print('Wrote pi_zero_preview.png; demo scores only')
            else:
                matrix.SetImage(frame)
                print('AFL DEMO is on the matrix for 20 seconds (no live data).')
                time.sleep(20)
                matrix.Clear()
            return 0
        headers = contact(read_email(args.email))
        lock = threading.RLock()
        stop = threading.Event()
        state = {}
        worker = None
        last_fetch = 0
        turn = 0
        while True:
            if time.time() - last_fetch >= 30 * 60:
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
                pool = games_ranked(list(state.values()), args.favorite)
                chosen = dict(pool[turn % min(6, len(pool))]) if pool else None
            frame = draw_game(chosen)
            if args.preview:
                from PIL import Image
                frame.resize((640, 320), Image.NEAREST).save(os.path.join(BASE, 'pi_zero_preview.png'))
            else:
                matrix.SetImage(frame)
            print('AFL %s: %s vs %s' % (status(chosen) if chosen else 'NONE', chosen.get('hteam') if chosen else '-', chosen.get('ateam') if chosen else '-'))
            if args.once:
                if not args.preview:
                    time.sleep(20)
                    matrix.Clear()
                return 0
            if worker is None:
                worker = threading.Thread(target=event_worker, args=(state, lock, stop, headers))
                worker.daemon = True
                worker.start()
            turn += 1
            stop.wait(args.rotate_seconds)
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
