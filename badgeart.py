"""Small offline crests, plus feed-supplied ESPN artwork for new cricket sides."""
import json
import re
from functools import lru_cache
from io import BytesIO
from pathlib import Path
from urllib.request import urlopen
from urllib.parse import urlsplit
from PIL import Image, ImageFilter, ImageChops

RESAMPLE = getattr(Image, "Resampling", Image)

ROOT = Path(__file__).resolve().parent
ASSETS = ROOT / "badges"
ALIASES = json.loads((ASSETS / "aliases.json").read_text())
feed_urls = {}

def key(value):
    return re.sub("[^a-z0-9]", "", str(value).lower())

def remember(sport, team):
    side = team.get("team") or team
    name = side.get("abbreviation") or side.get("shortDisplayName") or side.get("displayName")
    logo = side.get("logo") or team.get("logo")
    if not isinstance(logo,str):
        logo = (side.get("logos") or [{}])[0].get("href")
    tid = str(side.get("id") or team.get("id") or "")
    if not logo and sport == "Cricket" and tid.isdigit():
        logo = f"https://a.espncdn.com/i/teamlogos/cricket/500/{tid}.png"
    if name and isinstance(logo,str) and urlsplit(logo).scheme == "https" and urlsplit(logo).hostname == "a.espncdn.com":
        feed_urls[(sport,key(name))] = logo

@lru_cache(maxsize=256)
def scaled(source, w, h):
    try:
        if isinstance(source,Path):
            data = source.read_bytes()
        else:
            with urlopen(source,timeout=3) as response:
                data = response.read(1000001)
            if len(data)>1000000:
                return None
        with Image.open(BytesIO(data)) as im:
            if im.width*im.height > 4000000:
                return None
            mark = im.convert("RGBA")
        bounds = mark.getchannel("A").getbbox()
        if not bounds:
            return None
        mark = mark.crop(bounds)
        # Reserve an edge pixel so dark crests stay visible on a black panel.
        mark.thumbnail((max(1,w-2),max(1,h-2)), RESAMPLE.LANCZOS)
        alpha=mark.getchannel("A").point(lambda value: 0 if value<24 else 255 if value>180 else value)
        mark.putalpha(alpha)
        output=Image.new("RGBA",(mark.width+2,mark.height+2))
        output.paste(mark,(1,1))
        mask=output.getchannel("A")
        edge=ImageChops.subtract(mask.filter(ImageFilter.MaxFilter(3)),mask)
        halo=Image.new("RGBA",output.size,"#a6b9c8")
        halo.putalpha(edge.point(lambda value:value//2))
        halo.alpha_composite(output)
        return halo
    except (OSError,ValueError):
        return None

def badge(sport,name,w,h):
    league, team = key(sport),key(name)
    team = ALIASES.get(league,{}).get(team,team)
    if league == "afl":
        from afl.afl_scoreboard import resolve_team, logo_image
        full = resolve_team(name)[1]
        return logo_image(full,min(w,h)).convert("RGBA") if full else None
    if league.startswith("ufc"):
        league = team = "ufc"
    path=ASSETS / league / (team+".png")
    source = path if path.is_file() else feed_urls.get((sport,key(name)))
    return scaled(source,w,h) if source else None
