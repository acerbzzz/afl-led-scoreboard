import unittest
from unittest.mock import patch
from tempfile import TemporaryDirectory
from pathlib import Path
from PIL import Image
from sports import draw, fixtures, tv_details, EXAMPLES, DEMO_DETAILS
from ledlayout import footer, text
from badgeart import scaled

class LayoutTests(unittest.TestCase):
    def test_scores_and_logos_stay_put_while_details_rotate(self):
        for sport,row in EXAMPLES.items():
            a=draw(sport,row,'DEMO',DEMO_DETAILS[sport],0)
            b=draw(sport,row,'DEMO',DEMO_DETAILS[sport],1)
            self.assertEqual(a.crop((0,0,64,26)).tobytes(),b.crop((0,0,64,26)).tobytes(),sport)
            self.assertNotEqual(a.crop((0,27,64,32)).tobytes(),b.crop((0,27,64,32)).tobytes(),sport)

    def test_long_status_is_paginated_not_squeezed(self):
        frames=[]
        for tick in range(12):
            frame=Image.new('RGB',(64,32))
            footer(frame,['Australia need 123 runs from 70 balls'],'OFFLINE',tick)
            frames.append(frame.tobytes())
        self.assertGreater(len(set(frames)),3)
        with self.assertRaises(ValueError):
            text(Image.new('RGB',(64,32)),'THIS DOES NOT FIT',(0,0,10,5))

    def test_offline_label_does_not_cover_scores_or_ufc_method(self):
        from board import status_overlay
        from scoreboard import DEMO,render
        frame=draw('NBA',EXAMPLES['NBA'])
        self.assertEqual(frame.crop((0,0,64,26)).tobytes(),status_overlay(frame,'NBA','OFFLINE').crop((0,0,64,26)).tobytes())
        frame=render(DEMO[-1])
        self.assertEqual(frame.crop((0,8,64,32)).tobytes(),status_overlay(frame,'UFC','OFFLINE').crop((0,8,64,32)).tobytes())

    def test_missing_data_does_not_fabricate_counts(self):
        for sport in EXAMPLES:
            self.assertEqual(tv_details(sport,{},[],{'type':{'state':'in'}}),{'pages':[]})
        self.assertEqual(tv_details('MLB',{'situation':{'balls':3}},[],{'type':{'state':'post'}}),{'pages':[]})

    def test_nfl_possession_down_field_position_and_clock(self):
        teams=[{'id':'1','team':{'abbreviation':'BUF'},'score':'24','timeouts':2}, {'id':'2','team':{'abbreviation':'MIN'},'score':'20'}]
        c={'competitors':teams,'status':{'type':{'state':'in','shortDetail':'3:12 - 4th Quarter'},'period':4,'displayClock':'3:12'},'situation':{'possession':'1','shortDownDistanceText':'3rd & 7','possessionText':'BUF 34'}}
        catalog=[]
        rows=fixtures('NFL',{'events':[{'id':'x','competitions':[c]}]},catalog)
        self.assertEqual(rows[0][-1],'Q4 3:12')
        self.assertEqual(catalog[0]['display']['possession'],'0')
        self.assertEqual(catalog[0]['display']['pages'],['3rd & 7','BALL BUF 34','BUF TO 2'])

    def test_baseball_zero_counts_are_kept(self):
        d=tv_details('MLB',{'situation':{'balls':0,'strikes':0,'outs':0,'onFirst':True,'onSecond':False,'onThird':False}},[],{'type':{'state':'in'}})
        self.assertEqual(d['pages'],['B0 S0','0 OUT'])
        self.assertTrue(d['bases']['onFirst'])
        self.assertFalse(d['bases']['onSecond'])

    def test_transparent_rgb_padding_does_not_shrink_logo(self):
        with TemporaryDirectory() as folder:
            path=Path(folder)/'logo.png'
            im=Image.new('RGBA',(100,100),(255,255,255,0))
            for x in range(45,55):
                for y in range(45,55):im.putpixel((x,y),(255,0,0,255))
            im.save(path)
            result=scaled(path,17,13)
            self.assertGreaterEqual(result.width,11)
            self.assertLessEqual(result.height,13)
            self.assertEqual(result.getpixel((result.width//2,result.height//2))[:3],(255,0,0))

    def test_all_demo_teams_have_real_logos(self):
        from badgeart import badge
        for sport,row in EXAMPLES.items():
            for name in (row[0],row[2]):
                self.assertIsNotNone(badge(sport,name,17,13),(sport,name))

if __name__=='__main__':unittest.main()
