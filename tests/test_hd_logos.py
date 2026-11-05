"""Offline assurance for the HD club crest upgrade."""
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image
import afl_scoreboard as afl
from scripts import fetch_hd_logos as hd


def valid_png():
    frame = Image.new("RGBA", (256, 220), (0, 0, 0, 0))
    for x in range(65, 190):
        for y in range(48, 160):
            frame.putpixel((x, y), (150, 50, 190, 255))
    output = io.BytesIO()
    frame.save(output, format="PNG")
    return output.getvalue()


class HdLogoTests(unittest.TestCase):
    def test_all_18_clubs_have_distinct_download_sources(self):
        self.assertEqual(set(hd.LOGO_SLUGS), {full for _, full, _ in afl.TEAMS.values()})
        self.assertEqual(len(set(hd.LOGO_SLUGS.values())), 18)
        self.assertTrue(all(slug.isalnum() for slug in hd.LOGO_SLUGS.values()))

    def test_reject_opaque_or_tiny_downloads(self):
        good = hd.verify_transparent_logo(valid_png())
        self.assertEqual(good.mode, "RGBA")
        image = Image.new("RGB", (256, 256), "white")
        out = io.BytesIO(); image.save(out, "PNG")
        with self.assertRaises(ValueError): hd.verify_transparent_logo(out.getvalue())
        img = Image.new("RGBA", (32, 32), (0, 0, 0, 0))
        out = io.BytesIO(); img.save(out, "PNG")
        with self.assertRaises(ValueError): hd.verify_transparent_logo(out.getvalue())

    def test_downloader_checks_all_files_and_preserves_old_set_on_error(self):
        payload = valid_png()
        class FakeResponse(io.BytesIO):
            pass
        def fake_ok(req, timeout=18):
            self.assertIn("a.espncdn.com", req.full_url)
            return FakeResponse(payload)
        with tempfile.TemporaryDirectory() as folder:
            destination = Path(folder) / "logos_hd"
            self.assertEqual(hd.download_all(destination, opener=fake_ok), 18)
            self.assertEqual(hd.validate_existing(destination), 18)
            existing = (destination / "Fremantle.png").read_bytes()
            def fake_fail(req, timeout=18):
                if req.full_url.endswith("bl.png"):
                    raise OSError("server offline")
                return FakeResponse(payload)
            with self.assertRaises(RuntimeError):
                hd.download_all(destination, opener=fake_fail)
            self.assertEqual((destination / "Fremantle.png").read_bytes(), existing)

    def test_hd_renders_transparent_logo_preferentially(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            (base / "logos_hd").mkdir()
            (base / "logos").mkdir()
            Image.new("RGB", (32, 32), "yellow").save(base / "logos" / "Fremantle.bmp")
            (base / "logos_hd" / "Fremantle.png").write_bytes(valid_png())
            with patch.object(afl, "ROOT", base):
                crest = afl.logo_image("Fremantle", 116)
                self.assertEqual(crest.size, (116, 116))
                self.assertEqual(crest.getpixel((0, 0))[3], 0)
                self.assertEqual(crest.getpixel((58, 58))[:3], (150, 50, 190))
                led = afl.logo_image("Fremantle", 12)
                rgb = led.getpixel((6, 6))[:3]
                self.assertTrue(all(abs(actual - expected) <= 2 for actual, expected in zip(rgb, (150, 50, 190))))

    def test_demo_markers_and_real_scores_not_mislabeled(self):
        demo = afl.demo_game()
        self.assertTrue(demo["_demo"])
        seen = []
        original = afl._center_text
        def record(*args, **kwargs):
            seen.append(args[2])
            return original(*args, **kwargs)
        with patch.object(afl, "_center_text", side_effect=record):
            image = afl.draw_game_hd(demo)
        self.assertEqual(image.size, (1280, 640))
        self.assertIn("DEMO", seen)
        self.assertNotIn("LIVE", seen)
        seen.clear()
        with patch.object(afl, "_center_text", side_effect=record):
            afl.draw_game_hd(dict(demo, _demo=False))
        self.assertIn("LIVE", seen)
        sample = afl.draw_game(demo)
        live = afl.draw_game(dict(demo, _demo=False))
        self.assertNotEqual(sample.crop((18, 2, 62, 8)).tobytes(), live.crop((18, 2, 62, 8)).tobytes())


if __name__ == "__main__": unittest.main()