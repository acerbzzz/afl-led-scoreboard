import unittest
from dataclasses import replace
from unittest.mock import patch
from PIL import Image
from scoreboard import DEMO,render

class PortraitLayoutTests(unittest.TestCase):
    def test_live_has_both_real_portraits(self):
        with patch('scoreboard.photo',side_effect=[Image.new('RGBA',(30,30),'red'),Image.new('RGBA',(30,30),'blue')]):
            frame=render(DEMO[1])
        self.assertEqual(frame.getpixel((10,15)),(255,0,0))
        self.assertEqual(frame.getpixel((53,15)),(0,0,255))

    def test_final_shows_winner_portrait(self):
        with patch('scoreboard.photo',side_effect=[Image.new('RGBA',(30,30),'red'),Image.new('RGBA',(30,30),'blue')]):
            frame=render(DEMO[-1])
        self.assertEqual(frame.getpixel((12,18)),(0,0,255))
        self.assertIsNotNone(frame.crop((28,21,64,31)).getbbox())

    def test_missing_photos_keep_names_and_method(self):
        with patch('scoreboard.photo',return_value=None):
            frame=render(DEMO[-1])
            pending=render(replace(DEMO[-1],method=''))
        self.assertIsNotNone(frame.crop((0,8,64,18)).getbbox())
        self.assertNotEqual(frame.crop((0,21,64,31)).tobytes(),pending.crop((0,21,64,31)).tobytes())

    def test_long_names_keep_faces_when_name_page_changes(self):
        fight=replace(DEMO[1],names=('NURMAGOMEDOV','MAGOMEDSHARIPOV'))
        a,b=render(fight,tick=0),render(fight,tick=1)
        self.assertEqual(a.crop((0,6,21,27)).tobytes(),b.crop((0,6,21,27)).tobytes())
        self.assertNotEqual(a.crop((0,27,64,32)).tobytes(),b.crop((0,27,64,32)).tobytes())

    def test_one_missing_photo_keeps_other_fighter(self):
        with patch('scoreboard.photo',side_effect=[None,Image.new('RGBA',(30,30),'blue')]):
            frame=render(DEMO[1])
        self.assertEqual(frame.getpixel((53,15)),(0,0,255))
        self.assertIsNotNone(frame.crop((0,27,32,32)).getbbox())

class PortraitCacheTests(unittest.TestCase):
    def test_successful_download_survives_restart_without_network(self):
        import io,os,tempfile
        import portraits
        payload=io.BytesIO()
        Image.new('RGBA',(100,100),'red').save(payload,'PNG')
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ,{'BOARD_PORTRAITS':folder}):
            with patch('portraits.urlopen',return_value=io.BytesIO(payload.getvalue())):
                first=portraits._download('99887766')
            with patch('portraits._POOL.submit',side_effect=AssertionError('Unexpected network')):
                second=portraits.photo('99887766')
            self.assertEqual(first.tobytes(),second.tobytes())
        portraits._pictures.pop('99887766',None)

    def test_background_request_returns_without_waiting_and_recovers(self):
        import concurrent.futures,os,tempfile
        import portraits
        future=concurrent.futures.Future()
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ,{'BOARD_PORTRAITS':folder}), patch('portraits._POOL.submit',return_value=future) as submit:
            self.assertIsNone(portraits.photo('99887755'))
            self.assertIsNone(portraits.photo('99887755'))
            submit.assert_called_once()
            future.set_result(Image.new('RGBA',(30,30),'blue'))
            self.assertEqual(portraits.photo('99887755').getpixel((0,0)),(0,0,255,255))
        portraits._pictures.pop('99887755',None)
