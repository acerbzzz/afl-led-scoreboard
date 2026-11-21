import unittest
from dataclasses import replace

from sports import fixtures
from scoreboard import DEMO, render, short_method
from finishes import method_label

class ChannelTests(unittest.TestCase):
    def test_nrl_zero(self):
        self.assertEqual(fixtures("NRL", {"fixtures":[{"matchState":"Live","homeTeam":{"nickName":"Storm","score":0},"awayTeam":{"nickName":"Broncos","score":6}}]}),[("Storm","0","Broncos","6","Live")])

    def test_american_leagues(self):
        data = {"events":[{"competitions":[{"competitors":[{"team":{"abbreviation":"A"},"score":"0"},{"team":{"abbreviation":"B"},"score":"2"}],"status":{"type":{"shortDetail":"Final"}}}]}]}
        for sport in ("NFL","College Football","MLB","NBA","NBL"):
            self.assertEqual(fixtures(sport,data),[("A","0","B","2","Final")])

    def test_australian_cricket(self):
        sides = [{"abbreviation":"AUS","score":"154/3"},{"abbreviation":"IND"}]
        event = {"name":"Australia vs India","competitors":sides,"status":"in"}
        data = {"sports":[{"leagues":[{"events":[event,dict(event,name="Ireland vs England")]}]}]}
        self.assertEqual(fixtures("Cricket",data),[("AUS","154/3","IND","-","LIVE")])

    def test_final_keeps_method(self):
        for value, label in (("Technical Knockout","TKO"),("Submission","SUBMISSION"),("Decision - Split","DEC SD")):
            fight = replace(DEMO[-1],method=value)
            pending = replace(fight,method="")
            self.assertEqual(short_method(value),label)
            self.assertNotEqual(render(fight).crop((0,21,64,31)).tobytes(),render(pending).crop((0,21,64,31)).tobytes())
            self.assertEqual(render(fight,tick=30).tobytes(),render(fight).tobytes())
        self.assertEqual(method_label({"method":{"displayName":"KO/TKO"}}),"KO/TKO")

class WatchSettingsTests(unittest.TestCase):
    def test_cricket_current_innings_and_overs(self):
        teams = [{"id":"2","abbreviation":"AUS","score":"265 & 75/1 (22.3 ov, target 223)"},{"id":"6","abbreviation":"IND","score":"152 & 335"}]
        e = {"name":"Australia vs India","id":"91","fullStatus":{"battingTeamId":2},"competitors":teams,"status":"in"}
        catalog=[]
        rows=fixtures("Cricket",{"sports":[{"leagues":[{"events":[e]}]}]},catalog)
        self.assertEqual(rows,[("AUS","75/1","IND","335","LIVE")])
        self.assertEqual(catalog[0]["extra"],"22.3 OV")
        self.assertIn("target 223",catalog[0]["detail"])

    def test_brightness_wraps_midnight(self):
        from board import brightness,DEFAULT
        s=dict(DEFAULT,night=True,nightBrightness=12)
        self.assertEqual([brightness(s,h) for h in (21,22,0,6,7)], [20,12,12,12,20])
