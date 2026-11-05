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

    def test_squiggle_club_names_and_favorite_codes(self):
        game = {"hteam": "Fremantle", "ateam": "Brisbane Lions"}
        self.assertEqual(afl.team_data(game, "hteam")[:2], ("FRE", "Fremantle"))
        self.assertEqual(afl.team_data(game, "ateam")[:2], ("BRI", "Brisbane"))
        self.assertTrue(afl.matches_favorite(game, "FRE"))
        self.assertTrue(afl.matches_favorite(game, "BRI"))
        self.assertTrue(afl.matches_favorite({"hteam": "West Coast"}, "WCE"))
        self.assertEqual(afl.resolve_team("St Kilda")[0], "STK")

    def test_squiggle_naive_dates_are_melbourne_time(self):
        from zoneinfo import ZoneInfo
        mel = datetime(2026, 9, 26, 14, 30, tzinfo=ZoneInfo("Australia/Melbourne"))
        self.assertEqual(afl.iso_date("2026-09-26 14:30:00"), mel.astimezone(timezone.utc))

    def test_all_18_club_logos_required(self):
        self.assertEqual(afl.verify_all_logos(), 18)
        for _, full, _ in afl.TEAMS.values():
            crest = afl.logo_image(full, 96)
            self.assertEqual(crest.mode, "RGBA")
            self.assertEqual(crest.size, (96, 96))

    def test_missing_or_broken_logo_refuses_to_render(self):
        with tempfile.TemporaryDirectory() as temp:
            with patch.object(afl, "ROOT", Path(temp)):
                with self.assertRaises(afl.MissingLogoError):
                    afl.draw_game(self.game)
                with self.assertRaises(afl.MissingLogoError):
                    afl.draw_game_hd(self.game)
                with self.assertRaises(afl.MissingLogoError):
                    afl.verify_all_logos()
                logos = Path(temp) / "logos"
                logos.mkdir()
                (logos / "Fremantle.bmp").write_bytes(b"not a real image")
                with self.assertRaises(afl.MissingLogoError):
                    afl.logo_image("Fremantle", 32)

    def test_hd_uses_real_logos_not_team_initials(self):
        sentinel = (245, 0, 230)
        with patch.object(afl, "logo_image", side_effect=lambda full, size: afl.Image.new("RGBA", (size, size), sentinel + (255,))):
            frame = afl.draw_game_hd(self.game)
        self.assertEqual(frame.getpixel((139, 169 + 86)), sentinel)
        self.assertEqual(frame.getpixel((139, 366 + 86)), sentinel)

    def test_all_club_name_variants_resolve_to_logo(self):
        for name, expected in (("Brisbane Lions", "Brisbane"),
                               ("Sydney Swans", "Sydney"),
                               ("Adelaide Crows", "Adelaide"),
                               ("West Coast Eagles", "West Coast"),
                               ("Port Adelaide Power", "Port Adelaide")):
            self.assertEqual(afl.resolve_team(name)[1], expected)
        with self.assertRaises(afl.MissingLogoError):
            afl.draw_game_hd({"hteam": "Unknown Team", "ateam": "Fremantle"})

    def test_live_and_final(self):
        self.assertTrue(afl.is_live(self.game))
        self.game["complete"] = 100
        self.assertFalse(afl.is_live(self.game))
        self.assertEqual(afl.status_text(self.game), "FINAL")

    def test_game_priority_and_favorite(self):
        past = dict(self.game, id=1, complete=100, date="2026-05-01T05:00:00Z")
        up = dict(self.game, id=2, complete=0, date="2027-05-01T05:00:00Z", hteam=1, ateam=2)
        live = dict(self.game, id=3, complete=40, date="2026-05-02T05:00:00Z")
        now = datetime(2026, 6, 1, tzinfo=timezone.utc)
        self.assertEqual([g["id"] for g in afl.select_games([past, up, live], now=now)], [3, 2, 1])
        self.assertEqual([g["id"] for g in afl.select_games([past, up, live], favorite="FRE", now=now)], [3, 1])

    def test_compact_match_headers(self):
        self.assertEqual(afl.status_text(dict(self.game, complete=100)), "FINAL")
        self.assertEqual(afl.status_text(dict(self.game, timestr="Q4 12:37")), "Q4 12:37")
        self.assertEqual(afl.status_text(dict(self.game, timestr="Half Time")), "HALF TIME")
        self.assertEqual(afl.status_text(dict(self.game, timestr="3/4 Time")), "Q3 END")
        self.assertEqual(afl.status_text(dict(self.game, timestr="unknown")), "LIVE")
        scheduled = dict(self.game, complete=0, date="2026-09-26 14:30:00")
        self.assertEqual(afl.status_text(scheduled), "26SEP 14:30")
        self.assertLessEqual(len(afl.status_text(scheduled)), 11)

    def test_diagnostic_frames_preview_and_mock_matrix(self):
        frames = list(afl.diagnostic_frames())
        self.assertEqual(len(frames), 4)
        self.assertTrue(all(frame.size == (64, 32) for frame in frames))
        class FakeCanvas:
            def __init__(self): self.images = []
            def SetImage(self, frame): self.images.append(frame)
        class FakeMatrix:
            def __init__(self): self.canvases = []; self.swaps = 0
            def CreateFrameCanvas(self):
                canvas = FakeCanvas(); self.canvases.append(canvas); return canvas
            def SwapOnVSync(self, canvas): self.swaps += 1; return canvas
        matrix = FakeMatrix()
        with patch.object(afl.time, "sleep"):
            afl.run_hardware_test(matrix)
        self.assertEqual(matrix.swaps, 4)
        self.assertEqual(sum(len(c.images) for c in matrix.canvases), 4)
        self.assertNotEqual(frames[0].getpixel((0, 0)), frames[1].getpixel((0, 0)))

    def test_matrix_hardware_test_no_api(self):
        with patch.object(afl, "make_matrix", return_value=object()) as make:
            with patch.object(afl, "run_hardware_test") as test:
                self.assertEqual(afl.main(["--driver", "matrix", "--hardware-test"]), 0)
                self.assertEqual(make.call_count, 1)
                self.assertEqual(test.call_count, 1)

    def test_rotation_cycles_and_respects_favorite(self):
        first = dict(self.game, id=1, complete=100, date="2026-09-01T03:00:00Z")
        second = dict(self.game, id=2, complete=100, date="2026-09-02T03:00:00Z")
        third = dict(self.game, id=3, complete=100, date="2026-09-03T03:00:00Z", hteam=1, ateam=2)
        games = [first, second, third]
        self.assertEqual([afl.rotation_choice(games, i)["id"] for i in range(5)], [3, 2, 1, 3, 2])
        self.assertEqual([afl.rotation_choice(games, i, "FRE")["id"] for i in range(3)], [2, 1, 2])
        self.assertEqual([afl.rotation_choice(games, i, limit=2)["id"] for i in range(3)], [3, 2, 3])
        self.assertIsNone(afl.rotation_choice([], 0))
        with self.assertRaises(ValueError):
            afl.rotation_pool(games, limit=0)

    def test_event_stream_only_when_games_are_relevant(self):
        now = datetime(2026, 9, 1, 5, tzinfo=timezone.utc)
        future = dict(self.game, complete=0, date="2026-09-01T05:30:00Z")
        distant = dict(self.game, complete=0, date="2026-09-12T05:30:00Z")
        finished = dict(self.game, complete=100)
        self.assertTrue(afl.should_watch_events([future], now))
        self.assertTrue(afl.should_watch_events([dict(self.game, complete=33)], now))
        self.assertFalse(afl.should_watch_events([distant, finished], now))

    def test_rotation_once_uses_one_rest_request(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "preview.png"
            with patch.dict("os.environ", {"SQUIGGLE_CONTACT_EMAIL": "tester@example.org"}):
                with patch.object(afl, "season_games", return_value=[self.game]) as query:
                    self.assertEqual(afl.main(["--once", "--year", "2026", "--preview", str(target), "--rotate-limit", "4"]), 0)
                    self.assertEqual(query.call_count, 1)
            self.assertTrue(target.is_file())

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
                self.assertEqual(image.size, (1280, 640))

    def test_crisp_hd_and_legacy_pixel_preview(self):
        with tempfile.TemporaryDirectory() as temp:
            sharp = Path(temp) / "hd.png"
            blocky = Path(temp) / "pixel.png"
            self.assertEqual(afl.main(["--demo", "--preview", str(sharp)]), 0)
            self.assertEqual(afl.main(["--demo", "--preview-style", "pixel",
                                       "--preview", str(blocky)]), 0)
            with afl.Image.open(sharp) as image:
                self.assertEqual(image.size, (1280, 640))
                self.assertIsNotNone(image.getbbox())
            with afl.Image.open(blocky) as image:
                self.assertEqual(image.size, (640, 320))

    def test_hd_renders_squiggle_names_and_unknown_scores(self):
        game = dict(self.game, hteam="Fremantle", ateam="Brisbane Lions",
                    complete=100, hgoals=12, hbehinds=17, hscore=89,
                    agoals=14, abehinds=12, ascore=96)
        self.assertEqual(afl.draw_game_hd(game).size, (1280, 640))
        self.assertEqual(afl.draw_game_hd(None).size, (1280, 640))
        game.update(complete=0, hgoals=None, hbehinds=None, hscore=None)
        self.assertEqual(afl.draw_game_hd(game).size, (1280, 640))

    def test_quarter_live_and_final_labels(self):
        self.assertEqual(afl.status_text(dict(self.game, complete=100)), "FINAL")
        self.assertEqual(afl.status_text(dict(self.game, complete=65, timestr="Q3 14:26")), "Q3 14:26")
        self.assertIn("MAY", afl.status_text(dict(self.game, complete=0)))

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
