import unittest

from scoreboard import DEMO, bouts, render


class FightBoardTests(unittest.TestCase):
    def fight(self, state, winner=False):
        return {"competitors": [{"athlete": {"shortName": "A. Silva"}, "winner": winner},
                                {"athlete": {"lastName": "Park"}}],
                "status": {"period": 2, "displayClock": "3:15",
                           "type": {"state": state, "description": "Final"}}}

    def parse(self, *fights):
        return bouts({"events": [{"shortName": "UFC 334", "competitions": fights}]})

    def test_live_round_and_clock(self):
        fight, = self.parse(self.fight("in"))
        self.assertEqual((fight.names, fight.detail), (("Silva", "Park"), "R2 3:15"))

    def test_final_winner(self):
        fight, = self.parse(self.fight("post", True))
        self.assertEqual(fight.winner, (True, False))
        self.assertIn((99, 255, 132), render(fight).getdata())

    def test_incomplete_fight_skipped(self):
        self.assertEqual(self.parse({"competitors": []}), [])

    def test_offline_and_empty_frames(self):
        self.assertEqual(render(None).size, (64, 32))
        self.assertNotEqual(render(DEMO[1]).tobytes(), render(DEMO[1], True).tobytes())

    def test_invalid_feed(self):
        with self.assertRaises(ValueError):
            bouts({})

class IntroTests(unittest.TestCase):
    def test_demo_has_distinct_portraits(self):
        from scoreboard import intro
        red, blue = [intro(DEMO[0], i, True) for i in range(2)]
        self.assertEqual(red.size, (64, 32))
        self.assertNotEqual(red.crop((0, 0, 30, 32)).tobytes(), blue.crop((0, 0, 30, 32)).tobytes())

    def test_missing_photo_uses_names(self):
        from scoreboard import intro
        from dataclasses import replace
        missing = replace(DEMO[1], athlete_ids=("", ""))
        self.assertEqual(intro(missing, 0).tobytes(), render(missing).tobytes())

class FinishTests(unittest.TestCase):
    def test_all_methods_animate_and_keep_portraits(self):
        from dataclasses import replace
        from scoreboard import celebration
        for label in ("KO/TKO", "Submission", "Decision - Split", "Disqualification", "Doctor stoppage"):
            fight = replace(DEMO[-1], method=label)
            frames = list(celebration(fight))
            self.assertGreater(len({f.tobytes() for f in frames}), 1)
            self.assertEqual(frames[0].crop((0,0,64,24)).tobytes(), render(fight).crop((0,0,64,24)).tobytes())

    def test_ordered_judge_cards_and_method(self):
        fight = FightBoardTests().fight("post", True)
        fight["status"]["result"] = {"displayName": "Decision - Split"}
        for c, scores in zip(fight["competitors"], ((29,28,29),(28,29,28))):
            c["linescores"] = [{"linescores":[{"displayValue":str(n)} for n in scores]}]
        parsed = FightBoardTests().parse(fight)[0]
        self.assertEqual(parsed.cards, ("29-28","28-29","29-28"))
        self.assertEqual(parsed.method, "Decision - Split")
