"""Two-team scoreboard channels. Only the active channel polls its provider."""
import gameguide as guide
import json
import re
import os
import sys
import time
from pathlib import Path
from urllib.request import Request, urlopen

from PIL import Image, ImageDraw

RESAMPLE = getattr(Image, "Resampling", Image)

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "ufc-led-scoreboard"))
from scoreboard import pixels, big_line
from badgeart import badge, remember

URLS = {
    "College Football": "https://site.api.espn.com/apis/site/v2/sports/football/college-football/scoreboard?groups=80&limit=200",
    "NRL": "https://www.nrl.com/draw/data?competition=111",
    "Cricket": "https://site.api.espn.com/apis/personalized/v2/scoreboard/header?sport=cricket&region=au",
}
for league, path in {"NFL":"football/nfl","MLB":"baseball/mlb","NBA":"basketball/nba","NBL":"basketball/nbl"}.items():
    URLS[league] = "https://site.api.espn.com/apis/site/v2/sports/" + path + "/scoreboard"
EXAMPLES = {
    "College Football": ("OSU","28","MICH","24","Q4 03:12"),
    "NFL": ("BUF","24","MIN","20","Q4 03:12"),
    "MLB": ("SF","4","LAD","2","TOP 8"),
    "NBA": ("GS","108","BOS","104","Q4 01:18"),
    "NBL": ("PER","82","SYD","78","Q4 02:10"),
    "NRL": ("BRONCOS", "18", "STORM", "12", "2ND HALF"),
    "Cricket": ("AUS", "154/3", "IND", "151/8", "18.2 OV"),
}

def draw(sport, rows, flag=""):
    frame = Image.new("RGB", (64, 32))
    pen = ImageDraw.Draw(frame)
    a, x, b, y, phase = rows
    for col, name, score, color in ((0,a,x,"#97ceff"), (32,b,y,"#a8efc1")):
        if not name:
            continue
        mark = badge(sport,name,30,20)
        if mark:
            frame.paste(mark,(col+(32-mark.width)//2,(20-mark.height)//2),mark)
        else:
            pen.rounded_rectangle((col+4,1,col+27,18),radius=4,outline=color)
            pixels(pen,col+8,8,name[:4],color,col+26)
        if not score:
            pixels(pen,col,21,name[:8],color,col+32)
            continue
        # Shorten the label first so long cricket scores retain every digit.
        code = name[:max(0,min(3,7-len(score)))]
        label = (code+" "+score).strip()
        strip = Image.new("RGB",(max(1,len(label)*4-1),4))
        ink = ImageDraw.Draw(strip)
        pixels(ink,0,0,code,color,strip.width)
        pixels(ink,(len(code)+1)*4 if code else 0,0,score,"white",strip.width)
        strip = strip.resize((min(31,strip.width),6),RESAMPLE.NEAREST)
        frame.paste(strip,(col+(32-strip.width)//2,21))
    footer = (flag+" " if flag else "") + phase
    pixels(pen, 0, 28, footer, "#ffd05e", 64)
    return frame

def pair(teams, phase):
    values = []
    for team in teams:
        side = team.get("team") or team
        name = side.get("abbreviation") or side.get("nickName") or side.get("shortDisplayName") or side.get("displayName") or "TBA"
        score = team.get("score")
        if isinstance(score, dict):
            score = score.get("displayValue")
        values.extend((str(name), str(score) if score is not None else "-"))
    return (*values, str(phase))

def fixtures(sport, data, catalog=None):
    if sport == "NRL":
        rows = []
        for g in data["fixtures"]:
            if not (g.get("homeTeam") and g.get("awayTeam")):
                continue
            row = pair([g["homeTeam"],g["awayTeam"]],g.get("matchState") or g.get("matchMode") or "NRL")
            rows.append(row)
            if catalog is not None:
                gid = g.get("matchCentreUrl") or str(g.get("matchId") or (row[0]+row[2]+str((g.get("clock") or {}).get("kickOffTimeLong",""))))
                catalog.append(guide.game(gid,(row[0],row[2]),row[4],row[1]+" – "+row[3],row[4].lower() in ("live","inprogress","firsthalf","secondhalf")))
        return rows
    if sport == "Cricket":
        events = []
        for group in data["sports"]:
            for league in group.get("leagues", []):
                for g in league.get("events", []):
                    label = (league.get("name","") + " " + g.get("name","") + " " + g.get("shortName","")).lower()
                    if any(word in label for word in ("australia","big bash","sheffield","aus ","aus-w")):
                        events.append(g)
    else:
        events = data["events"]
    games = []
    for g in events:
        c = (g.get("competitions") or [g])[0]
        teams = c.get("competitors") or []
        if len(teams) == 2:
            status = c.get("status") or g.get("status") or {}
            phase = (status.get("type",{}).get("shortDetail") or status.get("detail") or status.get("description")) if isinstance(status,dict) else status
            for team in teams:
                remember(sport,team)
            row = pair(teams,phase or "SCHEDULED")
            situation = c.get("situation") or {}
            extra = ""
            if sport in ("NFL","College Football"):
                extra = situation.get("shortDownDistanceText") or situation.get("downDistanceText") or ""
            elif sport == "MLB" and any(k in situation for k in ("onFirst","onSecond","onThird")):
                extra = "BASE " + "".join(str(i) if situation.get(k) else "-" for i,k in enumerate(("onFirst","onSecond","onThird"),1))
            score_detail = row[1]+" – "+row[3]
            if sport=="Cricket":
                full = g.get("fullStatus") or {}
                batting = str(full.get("battingTeamId") or "")
                compact = []
                for t, raw in zip(teams,(row[1],row[3])):
                    innings = raw.partition("(")[0].split("&")[-1].strip()
                    compact.append(innings or "-")
                    overs = re.search(r"\(([0-9.]+)(?:/[0-9.]+)?\s*ov",raw)
                    if overs and batting and str(t.get("id"))==batting:
                        extra=overs.group(1)+" OV"
                phase = g.get("summary") or row[4]
                if phase in ("in","post","pre"):
                    phase = {"in":"LIVE","post":"FINAL","pre":"UPCOMING"}[phase]
                row=(row[0],compact[0],row[2],compact[1],phase)
                if full.get("longSummary"):
                    score_detail += " · "+full["longSummary"]
            games.append(row)
            if catalog is not None:
                live = (status.get("type") or {}).get("state") == "in" if isinstance(status,dict) else status == "in"
                gid = g.get("id") or c.get("id") or (row[0]+row[2]+str(g.get("date","")))
                fullnames = [(t.get("team") or t).get("displayName") or n for t,n in zip(teams,(row[0],row[2]))]
                item = guide.game(gid,fullnames,row[4],score_detail+(" · "+extra if extra else ""),live)
                item["extra"] = extra
                catalog.append(item)
    return games

def publish(frame):
    target = Path(os.environ["BOARD_FRAME"])
    tmp = target.with_suffix(".tmp")
    frame.save(tmp, format="PNG")
    tmp.replace(target)

def run(sport, demo):
    games, next_update, index, offline = [], 0, 0, False
    catalog = []
    while True:
        if demo:
            games = [EXAMPLES[sport]]
            r = games[0]
            catalog = [guide.game("demo", (r[0],r[2]),r[4],r[1]+" – "+r[3],True)]
            guide.feed("Demo")
        elif time.monotonic() >= next_update:
            try:
                req = Request(URLS[sport], headers={"User-Agent":"Mozilla/5.0 (Pi sports scoreboard)"})
                with urlopen(req, timeout=10) as r:
                    fresh = []
                    games = fixtures(sport, json.load(r),fresh)
                    catalog = fresh
                    guide.feed("Connected")
                offline = False
            except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
                print(exc, file=sys.stderr, flush=True)
                offline = True
                guide.feed("Offline")
            next_update = time.monotonic() + 60
        available = [i for i,g in enumerate(catalog) if not guide.PIN or g["id"] == guide.PIN]
        selected = available[index % len(available)] if available else None
        chosen = catalog[selected] if selected is not None else {}
        guide.report(catalog,chosen.get("id",""))
        if chosen or not guide.PIN:
            rows = games[selected] if chosen else ("NO FEED" if offline else "NO MATCH","","","",sport)
            if chosen.get("extra") and index % 2:
                rows = (*rows[:4],chosen["extra"])
            publish(draw(sport, rows, "OFFLINE" if offline else "DEMO" if demo else ""))
        index += 1
        time.sleep(10)

if __name__ == "__main__":
    run(sys.argv[1], "--demo" in sys.argv)
