"""Download optional 500px transparent AFL club logos for the HD desktop preview.

These are third-party trademarks fetched directly from ESPN's public image CDN.
The files remain local and should not be committed or relicensed under GPL.
"""
from __future__ import annotations

import argparse
from io import BytesIO
from pathlib import Path
import shutil
import tempfile
from urllib.request import Request, urlopen

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
CDN = "https://a.espncdn.com/i/teamlogos/afl/500"
# Verified team-to-CDN-slug mapping from a public 2026 AFL teams response.
LOGO_SLUGS = {
    "Adelaide": "adel", "Brisbane": "bl", "Carlton": "carl",
    "Collingwood": "coll", "Essendon": "ess", "Fremantle": "fre",
    "Geelong": "geel", "Gold Coast": "suns", "GWS": "gws",
    "Hawthorn": "haw", "Melbourne": "melb", "North Melbourne": "nmfc",
    "Port Adelaide": "port", "Richmond": "rich", "Stkilda": "stk",
    "Sydney": "syd", "West Coast": "wce", "Western Bulldogs": "wb",
}
MAX_BYTES = 3_000_000


def verify_transparent_logo(data: bytes) -> Image.Image:
    """Require a genuine 160px+ transparent image, not a small enlarged sprite."""
    if len(data) > MAX_BYTES:
        raise ValueError("image is too large")
    with Image.open(BytesIO(data)) as source:
        if source.format != "PNG":
            raise ValueError("source is not a PNG")
        source.load()
        if min(source.size) < 160:
            raise ValueError(f"logo is too small: {source.size}")
        img = source.convert("RGBA")
    amin, amax = img.getchannel("A").getextrema()
    if amin == 255 or amax == 0:
        raise ValueError("logo must have visible detail and a transparent background")
    return img


def validate_existing(target: Path) -> int:
    missing = []
    for full in LOGO_SLUGS:
        path = target / f"{full}.png"
        if not path.is_file():
            missing.append(str(path))
            continue
        try:
            verify_transparent_logo(path.read_bytes())
        except (OSError, ValueError) as error:
            missing.append(f"{path}: {error}")
    if missing:
        raise RuntimeError(f"HD logos missing/invalid ({len(missing)}):\n" + "\n".join(missing))
    return len(LOGO_SLUGS)


def download_all(target: Path = ROOT / "logos_hd", opener=urlopen) -> int:
    """Stage and validate every asset before changing the installed logo set."""
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="afl-hd-", dir=target.parent) as folder:
        staging = Path(folder)
        for full, slug in LOGO_SLUGS.items():
            url = f"{CDN}/{slug}.png"
            request = Request(url, headers={"User-Agent": "AFL-LED-Scoreboard/1.0 (personal preview)", "Accept": "image/png"})
            try:
                with opener(request, timeout=18) as response:
                    data = response.read(MAX_BYTES + 1)
                image = verify_transparent_logo(data)
            except Exception as error:
                raise RuntimeError(f"Unable to download usable HD logo for {full} ({url}): {error}") from error
            image.save(staging / f"{full}.png", format="PNG", optimize=True)
            print(f"Verified HD crest: {full} ({image.width}x{image.height})", flush=True)
        validate_existing(staging)
        target.mkdir(parents=True, exist_ok=True)
        for full in LOGO_SLUGS:
            shutil.move(str(staging / f"{full}.png"), str(target / f"{full}.png"))
    return validate_existing(target)


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch all 18 HD transparent AFL team logos")
    parser.add_argument("--check", action="store_true", help="Check downloaded logos without network access")
    args = parser.parse_args()
    target = ROOT / "logos_hd"
    try:
        count = validate_existing(target) if args.check else download_all(target)
    except (OSError, RuntimeError) as error:
        parser.exit(1, str(error) + "\n")
    print(f"OK: all {count} transparent high-resolution AFL logos are ready in {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())