import io
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import afl_scoreboard as afl


class ScoreboardTests(unittest.TestCase):
    def setUp(self):
        self.game = afl.demo_game()

    def test_goal_scoring(self):
        self.assertEqual(afl.format_scoring(self.game, "h"), ("12.8", "80"))
        self.assertEqual(afl.format_scoring(self.game, "a"), ("9.10", "64"))

    def test_score_not_fabricated(self):
        self.assertEqual(afl.format_scoring({"hscore": 70}, "h"), ("-.-", "70"))
        self.assertEqual(afl.format_scoring({}, "h"), ("-.-", "--"))

    def test_total_computed_when_missing(self):
        self.assertEqual(afl.format_scoring({"hgoals": 2, "hbehinds": 3}, "h"), ("2.3", "15"))

    def test_home_away(self):
        self.assertEqual(afl.team_data(self.game, "hteam")[0], "FRE")
        self.assertEqual(afl.team_data(self.game, "ateam")[0], "WCE")

    def test_live_and_final(self):
        self.assertTrue(afl.is_live(self.game))
        self.game["complete"] = 100
        self.assertFalse(afl.is_live(self.game))
        self.assertEqual(afl.status_text(self.game), "FULL TIME")

    def test_game_priority_and_favorite(self):
        past = dict(self.game, id=1, complete=100, date="2026-05-01T05:00:00Z")
        up = dict(self.game, id=2, complete=0, date="2027-05-01T05:00:00Z", hteam=1, ateam=2)
        live = dict(self.game, id=3, complete=40, date="2026-05-02T05:00:00Z")
        now = datetime(2026, 6, 1, tzinfo=timezone.utc)
        self.assertEqual([g["id"] for g in afl.select_games([past, up, live], now=now)], [3, 2, 1])
        self.assertEqual([g["id"] for g in afl.select_games([past, up, live], favorite="FRE", now=now)], [3, 1])

    def test_preview_is_64x32(self):
        frame = afl.draw_game(self.game)
        self.assertEqual(frame.size, (64, 32))
        self.assertNotEqual(frame.getbbox(), None)

    def test_empty_frame(self):
        self.assertEqual(afl.draw_game(None).size, (64, 32))

    def test_demo_main_no_api(self):
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / "afl.png"
            self.assertEqual(afl.main(["--demo", "--preview", str(target)]), 0)
            with afl.Image.open(target) as image:
                self.assertEqual(image.size, (640, 320))

    def test_headers_reject_missing_contact(self):
        with self.assertRaises(ValueError):
            afl.contact_headers("")
        self.assertIn("me@example.org", afl.contact_headers("me@example.org")["User-Agent"])

    def test_sse_score_event(self):
        state = {12: dict(self.game, id=12)}
        self.assertTrue(afl.apply_event(state, "score", {"gameid": 12, "score": {"hscore": 86, "hgoals": 13, "hbehinds": 8}, "timestr": "Q3 19:10"}))
        self.assertEqual(state[12]["hscore"], 86)
        self.assertEqual(state[12]["timestr"], "Q3 19:10")
        self.assertFalse(afl.apply_event(state, "score", {"gameid": 9999}))

    def test_event_stream_parser(self):
        raw = b": ping\n\nevent:score\ndata:{\"gameid\":12,\"score\":{\"hscore\":86}}\n\n"
        self.assertEqual(list(afl.event_messages(io.BytesIO(raw))), [("score", {"gameid": 12, "score": {"hscore": 86}})])

    def test_cache_prevents_repeat_request(self):
        with tempfile.TemporaryDirectory() as temp:
            with patch.object(afl, "get_json", return_value={"games": [self.game]}) as fetch:
                a = afl.season_games(2026, {"User-Agent": "x"}, cache_dir=Path(temp))
                b = afl.season_games(2026, {"User-Agent": "x"}, cache_dir=Path(temp))
            self.assertEqual(len(a), len(b))
            self.assertEqual(fetch.call_count, 1)

    def test_stale_cache_fallback(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "games_2026.json"
            path.write_text(json.dumps([self.game]))
            with patch.object(afl, "get_json", side_effect=OSError("offline")):
                games = afl.season_games(2026, {"User-Agent": "x"}, cache_minutes=0, cache_dir=Path(temp))
            self.assertEqual(games[0]["id"], 9999)


if __name__ == "__main__":
    unittest.main()
