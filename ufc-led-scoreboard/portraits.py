"""Small, cached ESPN cutouts for the introduction screens."""
from functools import lru_cache
from io import BytesIO
from pathlib import Path
from urllib.request import urlopen
from PIL import Image, ImageOps

RESAMPLE = getattr(Image, "Resampling", Image)


def crop_face(source):
    portrait = source.convert("RGBA")
    bounds = portrait.getchannel("A").getbbox()
    if not bounds:
        raise ValueError("Empty headshot")
    portrait = portrait.crop(bounds)
    size = min(portrait.width, portrait.height, max(1, round(portrait.height * .78)))
    left = (portrait.width - size) // 2
    portrait = portrait.crop((left, 0, left + size, size))
    return ImageOps.fit(portrait, (30, 30), method=RESAMPLE.LANCZOS)


@lru_cache(maxsize=128)
def photo(athlete_id):
    if not athlete_id.isascii() or not athlete_id.isdigit():
        return None
    sample = Path(__file__).parent / "demo" / (athlete_id + ".png")
    if sample.exists():
        with Image.open(sample) as source:
            return source.convert("RGBA")
    url = "https://a.espncdn.com/i/headshots/mma/players/full/{}.png".format(athlete_id)
    try:
        with urlopen(url, timeout=3) as response:
            data = response.read(3_000_001)
        if len(data) <= 3_000_000:
            with Image.open(BytesIO(data)) as source:
                return crop_face(source)
    except (ValueError, OSError):
        pass
    return None
