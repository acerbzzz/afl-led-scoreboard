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
