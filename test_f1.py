import unittest
from copy import deepcopy
from f1 import sessions,choose,draw,DEMO,driver_key

class F1Tests(unittest.TestCase):
    def event(self,state='in',kind='Race',period=18):
        return {'events':[{'id':'10','name':'Test GP','competitions':[{'id':'20','date':'2026-01-01','type':{'abbreviation':kind},'status':{'period':period,'type':{'state':state,'shortDetail':'Live'}},'competitors':[{'id':'2','order':2,'athlete':{'displayName':'Lando Norris'}},{'id':'1','order':1,'winner':True,'athlete':{'displayName':'Oscar Piastri'}}]}]}]}

    def test_orders_classification_and_reads_race_lap(self):
        s=sessions(self.event())[0]
        self.assertEqual([d['id'] for d in s['drivers']],['1','2'])
        self.assertEqual(s['lap'],18)
        self.assertEqual(driver_key(s,s['drivers'][0]),'10-20-1')

    def test_scheduled_entry_list_is_not_a_starting_grid(self):
        s=sessions(self.event('pre'))[0]
        self.assertIsNone(s['lap'])
        self.assertTrue(all(d['position'] is None for d in s['drivers']))

    def test_practice_period_is_not_race_lap(self):
        self.assertIsNone(sessions(self.event('in','FP1',32))[0]['lap'])

    def test_prefers_live_then_latest_completed(self):
        s=sessions(self.event())[0]
        old=dict(s,state='post',date='2026-01-01')
        recent=dict(s,state='post',date='2026-02-01')
        self.assertIs(choose([old,recent,s]),s)
        self.assertIs(choose([old,recent]),recent)
        self.assertIsNone(choose([]))

    def test_logo_and_all_views_are_nonempty(self):
        from badgeart import badge
        self.assertIsNotNone(badge('F1','F1',13,6))
        for s in (None,DEMO):
            image=draw(s,flag='DEMO')
            self.assertEqual(image.size,(64,32))
            self.assertIsNotNone(image.getbbox())
        for driver in DEMO['drivers']:
            image=draw(DEMO,flag='DEMO',driver=driver)
            self.assertIsNotNone(image.getbbox())

    def test_missing_gap_remains_missing(self):
        s=sessions(self.event())[0]
        self.assertEqual(s['drivers'][1]['gap'],'')
        self.assertEqual(s['drivers'][1]['team'],'')

    def test_leaderboard_wraps_without_skipping_first_page(self):
        s=deepcopy(DEMO)
        s['drivers'].append(dict(s['drivers'][0],id='9',code='RUS',position=4))
        self.assertEqual(draw(s,0).crop((0,7,64,26)).tobytes(),draw(s,4).crop((0,7,64,26)).tobytes())

    def test_invalid_payload_rejected(self):
        with self.assertRaises(ValueError):sessions({})
