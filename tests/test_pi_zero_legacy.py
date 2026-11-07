import io
import importlib.util
import os
import sys
import tempfile
import threading
import unittest
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

HERE = Path(__file__).resolve().parents[1]
SCRIPT = HERE / 'scripts' / 'pi_zero_legacy.py'
spec = importlib.util.spec_from_file_location('pi_zero_legacy', SCRIPT)
afl = importlib.util.module_from_spec(spec)
spec.loader.exec_module(afl)


class LegacyTests(unittest.TestCase):
    def test_all_18_clubs_and_aliases(self):
        self.assertEqual(len(afl.TEAM_LIST), 18)
        self.assertEqual(afl.club('Fremantle Dockers')[1], 'FRE')
        self.assertEqual(afl.club('Brisbane Lions')[1], 'BRI')
        self.assertEqual(afl.club('West Coast Eagles')[1], 'WCE')
        self.assertEqual(afl.club('Port Adelaide Power')[1], 'PTA')
        self.assertEqual(afl.club(15)[1], 'STK')
        with self.assertRaises(ValueError):
            afl.club('not a real club')

    def test_scores_and_status(self):
        self.assertEqual(afl.score(afl.demo_game(), 'h'), ('12.8', '80'))
        self.assertEqual(afl.score(afl.demo_game(), 'a'), ('9.10', '64'))
        self.assertEqual(afl.score({'hgoals': 5, 'hbehinds': 4}, 'h'), ('5.4', '34'))
        self.assertEqual(afl.score({}, 'h'), ('-.-', '--'))
        self.assertEqual(afl.status(afl.demo_game()), 'DEMO')
        self.assertEqual(afl.status({'complete': 100}), 'FINAL')
        self.assertEqual(afl.status({'complete': 75, 'timestr': 'Q3 18:44'}), 'Q3')

    def test_logos_required_and_render(self):
        self.assertEqual(afl.verify_logos(str(HERE / 'logos')), 18)
        frame = afl.draw_game(afl.demo_game(), str(HERE / 'logos'))
        self.assertEqual(frame.size, (64, 32))
        self.assertTrue(frame.getbbox())
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(IOError):
                afl.draw_game(afl.demo_game(), temp)
        self.assertEqual(afl.draw_game(None).size, (64, 32))

    def test_16px_crests_fill_the_two_16px_rows(self):
        """A 16x16 crest belongs to each team and must not overlap scores."""
        from PIL import Image
        home = (185, 5, 160)
        away = (230, 170, 30)
        seen = []

        def fake_logo(cls, name, size, directory=None):
            seen.append((name, size))
            return Image.new('RGBA', (size, size),
                             (home if name == 'Fremantle' else away) + (255,))

        with mock.patch.object(afl, 'logo', side_effect=fake_logo):
            frame = afl.draw_game(afl.demo_game())
        self.assertEqual(frame.size, (64, 32))
        self.assertEqual(seen, [('Fremantle', 16), ('West Coast', 16)])
        self.assertEqual(frame.getpixel((8, 15)), home)
        self.assertEqual(frame.getpixel((8, 16)), away)
        self.assertEqual(frame.getpixel((8, 31)), away)
        # Team labels, goals.behinds and big total points all produce pixels.
        self.assertNotEqual(frame.getpixel((18, 2)), (0, 0, 0))
        self.assertNotEqual(frame.crop((18, 8, 42, 15)).getbbox(), None)
        self.assertNotEqual(frame.crop((46, 8, 64, 15)).getbbox(), None)

    def test_big_point_totals_are_right_aligned_and_bounded(self):
        from PIL import Image, ImageDraw
        image = Image.new('RGB', (64, 32))
        d = ImageDraw.Draw(image)
        afl.big_score(d, 64, 4, '120', 'white')
        self.assertIsNotNone(image.crop((46, 4, 64, 11)).getbbox())
        self.assertIsNone(image.crop((0, 4, 46, 11)).getbbox())
        image = Image.new('RGB', (64, 32))
        afl.big_score(ImageDraw.Draw(image), 64, 4, '--', 'white')
        self.assertIsNotNone(image.crop((52, 4, 64, 11)).getbbox())

    def test_opaque_logo_background_removed_but_details_kept(self):
        from PIL import Image
        pale = Image.new('RGBA', (12, 12), (247, 247, 247, 255))
        for x in range(3, 9):
            for y in range(3, 9):
                pale.putpixel((x, y), (22, 12, 67, 255))
        # A white emblem enclosed inside the dark crest must remain visible.
        pale.putpixel((5, 5), (255, 255, 255, 255))
        fixed = afl.remove_light_logo_background(pale)
        self.assertEqual(fixed.getpixel((0, 0))[3], 0)
        self.assertEqual(fixed.getpixel((11, 11))[3], 0)
        self.assertEqual(fixed.getpixel((5, 5)), (255, 255, 255, 255))
        self.assertEqual(fixed.getpixel((4, 4))[3], 255)

    def test_real_fremantle_logo_no_longer_has_solid_white_corners(self):
        from PIL import Image
        crest = afl.logo(Image, 'Fremantle', 16, str(HERE / 'logos'))
        self.assertEqual(crest.size, (16, 16))
        self.assertEqual(crest.getpixel((0, 0))[3], 0)
        self.assertEqual(crest.getpixel((15, 15))[3], 0)
        self.assertTrue(any(crest.getpixel((x, y))[3] >= 200
                            for x in range(3, 13) for y in range(3, 13)))

    def test_compact_club_symbol_removes_tiny_bottom_wordmark(self):
        from PIL import Image, ImageDraw
        art = Image.new('RGBA', (32, 32), (245, 242, 240, 255))
        draw = ImageDraw.Draw(art)
        draw.ellipse((9, 1, 23, 22), fill=(45, 12, 110, 255))
        draw.line((16, 3, 16, 18), fill=(255, 255, 255, 255), width=2)
        # Yellow lettering lies entirely beneath the main emblem.
        draw.rectangle((9, 27, 23, 29), fill=(245, 208, 0, 255))
        icon = afl.compact_logo_art(Image, art, 16)
        self.assertEqual(icon.size, (16, 16))
        self.assertEqual(icon.getpixel((0, 0))[3], 0)
        self.assertGreater(sum(px[3] > 127 for px in icon.getdata()), 24)
        self.assertFalse(any(r > 180 and 120 < g < 230 and b < 80 and a > 200
                             for r, g, b, a in icon.getdata()))
        self.assertLessEqual(max((r for r,g,b,a in icon.getdata()
                                  if a > 200 and abs(r-g) < 10 and abs(g-b) < 10),
                                 default=0), 185)

    def test_bundled_logos_remain_mandatory_and_renderable(self):
        from PIL import Image
        for team in afl.TEAM_LIST:
            icon = afl.logo(Image, team[2], 16, str(HERE / 'logos'))
            self.assertEqual(icon.size, (16,16))
            self.assertTrue(icon.getbbox(), team[2])

    def test_fremantle_shield_fill_darkened_anchor_remains_legible(self):
        from PIL import Image, ImageDraw
        art = Image.new('RGBA', (16, 16), (0, 0, 0, 0))
        draw = ImageDraw.Draw(art)
        draw.rectangle((3, 2, 12, 13), fill=(65, 15, 135, 255))
        draw.line((7, 4, 7, 11), fill=(195, 195, 195, 255))
        draw.line((5, 10, 9, 10), fill=(195, 195, 195, 255))
        reduced = afl.outline_fremantle_shield(art)
        self.assertLess(max(reduced.getpixel((5, 7))[:3]), 50)
        self.assertGreater(reduced.getpixel((3, 7))[2],
                           reduced.getpixel((5, 7))[2] * 3)
        self.assertGreater(reduced.getpixel((7, 6))[0], 195)
        self.assertEqual(reduced.getpixel((0, 0))[3], 0)
        self.assertEqual(reduced.getpixel((5, 7))[3], 255)

    def test_fremantle_real_asset_has_a_readable_anchor(self):
        from PIL import Image
        badge = afl.logo(Image, 'Fremantle', 16, str(HERE / 'logos'))
        self.assertEqual(badge.size, (16, 16))
        self.assertTrue(badge.getbbox())
        self.assertTrue(any(r >= 125 and g >= 125 and b >= 125 and a > 100
                            for r, g, b, a in badge.getdata()))

    def test_new_goal_from_sse_triggers_once_and_updates_score(self):
        from collections import deque
        state = {31: dict(afl.demo_game(), id=31, complete=48)}
        pending = deque(maxlen=5)
        payload = {'gameid': 31, 'type': 'goal', 'side': 'hteam',
                   'team': 6, 'complete': 49,
                   'score': {'hgoals': 13, 'hscore': 86, 'hbehinds': 8}}
        self.assertTrue(afl.update_live_state(state, 'score', payload, pending))
        self.assertEqual(list(pending)[0]['team'], 'Fremantle')
        self.assertEqual(list(pending)[0]['total'], '86')
        self.assertEqual(state[31]['hgoals'], 13)
        # Replayed SSE events cannot trigger a second goal animation.
        self.assertFalse(afl.update_live_state(state, 'score', payload, pending))
        self.assertEqual(len(pending), 1)

    def test_away_goal_and_favorite_selection(self):
        from collections import deque
        initial = dict(afl.demo_game(), id=31, complete=48)
        payload = {'gameid': 31, 'type': 'goal', 'side': 'ateam',
                   'team': 17, 'complete': 49,
                   'score': {'agoals': 10, 'ascore': 70}}
        pending = deque(maxlen=5)
        state = {31: dict(initial)}
        self.assertTrue(afl.update_live_state(state, 'score', payload, pending, 'WCE'))
        self.assertEqual(pending[0]['team'], 'West Coast')
        self.assertEqual(pending[0]['total'], '70')
        state = {31: dict(initial)}
        pending.clear()
        self.assertFalse(afl.update_live_state(state, 'score', payload, pending, 'GEE'))
        self.assertFalse(pending)

    def test_no_animation_for_behind_snapshot_points_only_or_final(self):
        from collections import deque
        base = dict(afl.demo_game(), id=31, complete=48)
        cases = [
            ('score', {'gameid': 31, 'type': 'behind', 'side': 'hteam',
                       'score': {'hbehinds': 9, 'hscore': 81}}),
            ('score', {'gameid': 31, 'side': 'hteam',
                       'score': {'hgoals': 13, 'hscore': 86}}),
            ('score', {'gameid': 31, 'type': 'goal', 'side': 'hteam',
                       'score': {'hscore': 86}}),
            ('score', {'gameid': 31, 'type': 'goal', 'side': 'hteam',
                       'team': 17, 'score': {'hgoals': 13, 'hscore': 86}}),
            ('score', {'gameid': 31, 'type': 'goal', 'side': 'hteam',
                       'complete': 100,
                       'score': {'hgoals': 13, 'hscore': 86}}),
            ('game', dict(base, hgoals=13, hscore=86)),
        ]
        for ev_type, payload in cases:
            state, alerts = {31: dict(base)}, deque()
            self.assertFalse(afl.update_live_state(state, ev_type, payload,
                                                  alerts))
            self.assertFalse(alerts)
        # With no baseline, even a 'goal' event is not a trustworthy new goal.
        state, alerts = {}, deque()
        self.assertFalse(afl.update_live_state(state, 'score',
                         cases[3][1], alerts))
        self.assertFalse(alerts)

    def test_goal_frames_keep_64x32_and_use_real_team_logos(self):
        from PIL import Image
        frames = [afl.draw_goal_frame({'team': 'Fremantle',
                                      'total': '86'}, phase)
                  for phase in range(6)]
        self.assertTrue(all(frame.size == (64, 32) for frame in frames))
        self.assertTrue(all(frame.getbbox() for frame in frames))
        self.assertNotEqual(frames[0].tobytes(), frames[1].tobytes())
        self.assertNotEqual(frames[1].tobytes(), frames[2].tobytes())
        self.assertTrue(afl.draw_goal_frame({'team': 'West Coast',
                           'total': '70'}, 0).getbbox())

    def test_offline_demo_goal_never_contacts_squiggle(self):
        with mock.patch.object(afl, 'urlopen', side_effect=AssertionError(
                'Offline goal demo must not call Squiggle')), \
             mock.patch.object(afl, 'read_email', side_effect=AssertionError(
                'Offline goal demo should not require Squiggle contact')):
            self.assertEqual(afl.main(['--demo-goal', '--preview']), 0)
        from PIL import Image
        with Image.open(HERE / 'pi_zero_goal_preview.png') as image:
            self.assertEqual(image.size, (640, 320))

    def test_goal_animation_emits_six_frames(self):
        class FakeMatrix(object):
            def __init__(self):
                self.frames = []
            def SetImage(self, frame):
                self.frames.append(frame.copy())
        matrix = FakeMatrix()
        with mock.patch.object(afl.time, 'sleep', return_value=None):
            afl.show_goal_animation(matrix, {'team': 'Fremantle', 'total': '86'})
        self.assertEqual(len(matrix.frames), 6)

    def test_full_time_event_only_on_live_to_final_transition(self):
        from collections import deque
        initial = dict(afl.demo_game(), id=101, complete=96)
        state, queue = {101: dict(initial)}, deque()
        event = {'gameid': 101, 'complete': 100}
        self.assertTrue(afl.update_live_state(state, 'complete', event, queue))
        self.assertEqual(len(queue), 1)
        self.assertEqual(queue[0]['kind'], 'final')
        self.assertEqual(queue[0]['winner'], 'Fremantle')
        self.assertEqual(queue[0]['margin'], 16)
        self.assertFalse(afl.update_live_state(state, 'complete', event, queue))
        self.assertEqual(len(queue), 1)
        # Startup history and unplayed fixtures must never trigger celebration.
        for complete in (0, 100):
            prior = dict(initial, complete=complete)
            state, queue = {101: prior}, deque()
            self.assertFalse(afl.update_live_state(state, 'complete', event, queue))
            self.assertEqual(len(queue), 0)

    def test_final_siren_away_win_draw_and_missing_score(self):
        home = dict(afl.demo_game(), id=17, complete=98)
        away_wins = dict(home, complete=100, ascore=93)
        result = afl.final_from_transition(home, away_wins)
        self.assertEqual((result['winner'], result['margin']), ('West Coast', 13))
        draw = dict(home, complete=100, ascore=80)
        self.assertIsNone(afl.final_from_transition(home, draw)['winner'])
        missing = dict(home, complete=100, hscore=None)
        self.assertIsNone(afl.final_from_transition(home, missing))
        final = afl.draw_final_frame(result, 0)
        self.assertEqual(final.size, (64, 32))
        self.assertNotEqual(final.tobytes(),
                            afl.draw_final_frame(result, 1).tobytes())
        self.assertEqual(afl.draw_final_frame(
            afl.final_from_transition(home, draw), 0).size, (64, 32))

    def test_standings_parse_rank_and_real_clubs(self):
        raw = {'standings': [
            {'id': 17, 'rank': 18, 'pts': 8, 'wins': 2, 'percentage': 72.3},
            {'id': 6, 'rank': 1, 'pts': 72, 'wins': 18, 'percentage': 145.2},
            {'id': 6, 'rank': 3, 'pts': 40, 'wins': 10, 'percentage': 100.0},
            {'id': 99, 'rank': 2, 'pts': 60, 'wins': 15, 'percentage': 118.0}
        ]}
        rows = afl.normalize_standings(raw)
        self.assertEqual(len(rows), 2)
        self.assertEqual([row['rank'] for row in rows], [1, 18])
        self.assertEqual(rows[0]['code'], 'FRE')
        self.assertEqual(rows[1]['pts'], 8)
        self.assertEqual(afl.draw_ladder_frame(rows, 0).size, (64, 32))
        self.assertEqual(afl.draw_ladder_frame(rows, 1).size, (64, 32))
        self.assertEqual(afl.draw_ladder_frame([], 0).size, (64, 32))
        with self.assertRaises(ValueError):
            afl.normalize_standings({'ladder': []})

    def test_real_standings_request_and_cache(self):
        class Response(object):
            def read(self):
                return (b'{"standings":[{"id":6,"rank":1,"pts":64,"wins":16,'
                        b'"percentage":128.3}]}')
            def close(self):
                pass
        with tempfile.TemporaryDirectory() as temp:
            with mock.patch.object(afl.tempfile, 'gettempdir', return_value=temp):
                with mock.patch.object(afl, 'urlopen', return_value=Response()) as call:
                    rows = afl.get_standings(2026, {'User-Agent':'test@example.org'})
                    self.assertEqual(rows[0]['team'], 'Fremantle')
                    self.assertEqual(call.call_args[0][0].get_full_url(),
                                     'https://api.squiggle.com.au/?q=standings;year=2026')
                with mock.patch.object(afl, 'urlopen',
                                       side_effect=AssertionError('No duplicate fetch')):
                    self.assertEqual(afl.get_standings(2026, {'User-Agent':'test@example.org'}), rows)

    def test_offline_upgrades_demo_no_email_or_network(self):
        with mock.patch.object(afl, 'urlopen', side_effect=AssertionError('No network')), \
             mock.patch.object(afl, 'read_email', side_effect=AssertionError('No contact')):
            self.assertEqual(afl.main(['--demo-upgrades','--preview']), 0)
        # The physical test exercises real animation; preview must remain 64x32-scaled.
        from PIL import Image
        with Image.open(HERE / 'pi_zero_preview.png') as frame:
            self.assertEqual(frame.size, (640, 320))

    def test_rotation(self):
        base = afl.demo_game()
        older = dict(base, id=1, complete=100, date='2026-09-21 18:00:00')
        newest = dict(base, id=2, complete=100, date='2026-09-26 18:00:00')
        upcoming = dict(base, id=3, complete=0, date='2027-05-01 19:00:00')
        live = dict(base, id=4, complete=60, date='2026-06-01 19:00:00')
        self.assertEqual([g['id'] for g in afl.games_ranked([older,newest,upcoming,live], 'FRE', now=datetime(2026,11,6))], [4,3,2,1])
        self.assertTrue(afl.match_favorite(live, 'FRE'))
        self.assertFalse(afl.match_favorite(live, 'GEE'))

    def test_event_merge(self):
        state = {99: {'id': 99, 'hscore': 30, 'hteam': 'Fremantle'}}
        self.assertTrue(afl.apply_event(state, 'score', {'gameid': 99, 'score': {'hscore': 36, 'hgoals': 6}, 'timestr': 'Q2'}))
        self.assertEqual(state[99]['hscore'], 36)
        self.assertTrue(afl.apply_event(state, 'complete', {'gameid': 99, 'complete': 100}))
        self.assertEqual(state[99]['complete'], 100)
        self.assertFalse(afl.apply_event(state, 'score', {'gameid': 111, 'score': {'hscore': 90}}))
        stream=io.BytesIO(b':ping\n\nevent: score\ndata: {"gameid":99,"score":{"hscore":36}}\n\n')
        self.assertEqual(list(afl.event_messages(stream)), [('score',{'gameid':99,'score':{'hscore':36}})])

    def test_contact_email_read_before_matrix_initialization(self):
        """Opening the root-only contact file must precede privilege dropping."""
        calls = []
        class FakeMatrix(object):
            def SetImage(self, img):
                calls.append('image')
            def Clear(self):
                calls.append('clear')
        def fake_read_email(explicit=None):
            calls.append('email')
            return 'test@example.org'
        def fake_create_matrix(args):
            calls.append('matrix')
            return FakeMatrix()
        def fake_season(year, headers):
            calls.append('season')
            self.assertIn('test@example.org', headers['User-Agent'])
            return [afl.demo_game()]
        with mock.patch.object(afl, 'read_email', side_effect=fake_read_email), \
             mock.patch.object(afl, 'create_matrix', side_effect=fake_create_matrix), \
             mock.patch.object(afl, 'get_season', side_effect=fake_season), \
             mock.patch.object(afl.time, 'sleep', return_value=None):
            self.assertEqual(afl.main(['--once', '--favorite', 'FRE']), 0)
        self.assertEqual(calls[:3], ['email', 'matrix', 'season'])

    def test_offline_demo_never_reads_contact_file(self):
        with mock.patch.object(afl, 'read_email', side_effect=AssertionError(
                'Demo must not read private Squiggle contact file')), \
             mock.patch.object(afl, 'urlopen', side_effect=AssertionError('No network')):
            self.assertEqual(afl.main(['--demo', '--preview']), 0)

    def test_cache_location_is_private_and_not_inside_pi_project(self):
        """RGBMatrix may drop from root to daemon; its cache must remain writable."""
        import stat
        with tempfile.TemporaryDirectory() as scratch:
            with mock.patch.object(afl.tempfile, 'gettempdir', return_value=scratch):
                path = afl.cache_path(2026)
                folder = os.path.dirname(path)
                self.assertTrue(folder.startswith(scratch + os.sep))
                self.assertNotIn('/afl-led-scoreboard/.cache', path)
                self.assertEqual(os.stat(folder).st_uid, os.geteuid())
                self.assertEqual(stat.S_IMODE(os.stat(folder).st_mode), 0o700)
                with open(path, 'w') as stream:
                    stream.write('[]')
                self.assertEqual(afl.cache_path(2026), path)

    def test_cache_rejects_symlink_in_shared_tmp_directory(self):
        with tempfile.TemporaryDirectory() as scratch:
            rogue = os.path.join(scratch, 'other')
            os.mkdir(rogue)
            name = os.path.join(scratch, 'afl-led-scoreboard-cache-%s' % os.geteuid())
            os.symlink(rogue, name)
            with mock.patch.object(afl.tempfile, 'gettempdir', return_value=scratch):
                with self.assertRaises(IOError):
                    afl.cache_path(2026)

    def test_fetched_season_is_cached_without_project_writes(self):
        class Response(object):
            def read(self):
                return b'{"games":[{"id":1,"hteam":"Fremantle","ateam":"West Coast"}]}'
            def close(self):
                pass
        with tempfile.TemporaryDirectory() as scratch:
            with mock.patch.object(afl.tempfile, 'gettempdir', return_value=scratch):
                with mock.patch.object(afl, 'urlopen', return_value=Response()) as fetch:
                    games = afl.get_season(2026, {'User-Agent':'test'})
                self.assertEqual(games[0]['id'], 1)
                with mock.patch.object(afl, 'urlopen', side_effect=AssertionError(
                        'Fresh cache should avoid network')):
                    self.assertEqual(afl.get_season(2026, {'User-Agent':'test'}), games)
                self.assertEqual(fetch.call_count, 1)

    def test_contact_required(self):
        with self.assertRaises(ValueError):
            afl.contact('')
        self.assertIn('test@example.org',afl.contact('test@example.org')['User-Agent'])

    def test_matrix_settings_mock(self):
        opts = SimpleNamespace(rows=None,cols=None,chain_length=None,parallel=None,hardware_mapping=None,brightness=None,gpio_slowdown=None,multiplexing=None,row_address_type=None,scan_mode=None)
        def mk():return opts
        fake = SimpleNamespace(RGBMatrixOptions=mk, RGBMatrix=lambda options: options)
        with mock.patch.dict(sys.modules, {'rgbmatrix': fake}):
            result = afl.create_matrix(SimpleNamespace(brightness=25,slowdown=2,multiplexing=1,row_addr_type=0,scan_mode=0))
        self.assertEqual(result.rows, 32)
        self.assertEqual(result.cols, 64)
        self.assertEqual(result.multiplexing, 1)

    def test_demo_preview_no_network(self):
        with mock.patch.object(afl, 'BASE', str(HERE)):
            with mock.patch.object(afl, 'urlopen', side_effect=AssertionError('Network called in demo')):
                code = afl.main(['--demo','--preview'])
        self.assertEqual(code, 0)
        from PIL import Image
        with Image.open(HERE / 'pi_zero_preview.png') as image:
            self.assertEqual(image.size, (640,320))


if __name__=='__main__':
    unittest.main()
