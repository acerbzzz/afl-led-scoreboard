"""Real ESPN fighter cutouts, fetched in the background and retained offline."""
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
import os
from pathlib import Path
import time
from urllib.request import urlopen
from PIL import Image, ImageOps

RESAMPLE = getattr(Image, 'Resampling', Image)
_POOL = ThreadPoolExecutor(max_workers=2)
_pending = {}
_pictures = {}
_retry = {}


def cache_dir():
    return Path(os.environ.get('BOARD_PORTRAITS', str(Path.home()/'.cache/ufc-scoreboard/portraits')))


def crop_face(source):
    if source.width * source.height > 4_000_000:
        raise ValueError('Headshot too large')
    portrait = source.convert('RGBA')
    bounds = portrait.getchannel('A').getbbox()
    if not bounds:
        raise ValueError('Empty headshot')
    portrait = portrait.crop(bounds)
    size = min(portrait.width, portrait.height, max(1, round(portrait.height * .78)))
    left = (portrait.width - size) // 2
    portrait = portrait.crop((left, 0, left + size, size))
    return ImageOps.fit(portrait, (30, 30), method=RESAMPLE.LANCZOS)


def _download(athlete_id):
    url = 'https://a.espncdn.com/i/headshots/mma/players/full/{}.png'.format(athlete_id)
    with urlopen(url, timeout=3) as response:
        data = response.read(3_000_001)
    if len(data) > 3_000_000:
        raise ValueError('Headshot too large')
    with Image.open(BytesIO(data)) as source:
        portrait = crop_face(source)
    try:
        folder=cache_dir()
        folder.mkdir(parents=True, exist_ok=True)
        temp=folder/(athlete_id+'.tmp')
        portrait.save(temp, format='PNG')
        temp.replace(folder/(athlete_id+'.png'))
    except OSError:
        pass  # A read-only cache must not hide a successfully loaded portrait.
    return portrait


def photo(athlete_id):
    if not isinstance(athlete_id,str) or not athlete_id.isascii() or not athlete_id.isdigit() or len(athlete_id)>16:
        return None
    if athlete_id in _pictures:
        return _pictures[athlete_id]
    pending=_pending.get(athlete_id)
    if pending is not None:
        if not pending.done():
            return None
        del _pending[athlete_id]
        try:
            portrait=pending.result()
        except Exception:
            _retry[athlete_id]=time.monotonic()+300
            return None
        if len(_pictures)>=128:
            _pictures.pop(next(iter(_pictures)))
        _pictures[athlete_id]=portrait
        return portrait
    sample=Path(__file__).parent/'demo'/(athlete_id+'.png')
    for path in (sample,cache_dir()/(athlete_id+'.png')):
        try:
            with Image.open(path) as source:
                if source.size != (30,30):
                    raise ValueError('Invalid cached portrait')
                portrait=source.convert('RGBA')
            if len(_pictures)>=128:
                _pictures.pop(next(iter(_pictures)))
            _pictures[athlete_id]=portrait
            return portrait
        except (OSError,ValueError):
            pass
    if time.monotonic()>=_retry.get(athlete_id,0) and len(_pending)<16:
        _pending[athlete_id]=_POOL.submit(_download,athlete_id)
    return None
