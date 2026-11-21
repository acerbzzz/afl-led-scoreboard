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

TEAM_CODES = {'BRONCOS':'BRI','STORM':'MEL','RABBITOHS':'SOU','ROOSTERS':'SYD',
              'COWBOYS':'NQL','DOLPHINS':'DOL','WARRIORS':'NZ','SEA EAGLES':'MAN',
              'BULLDOGS':'CBY','SHARKS':'CRO','RAIDERS':'CAN','PANTHERS':'PEN',
              'KNIGHTS':'NEW','TITANS':'GLD','EELS':'PAR','WESTS TIGERS':'WST','DRAGONS':'STG'}


def draw(sport, rows, flag="", details=None, tick=0):
    from ledlayout import text, large, footer, clean
    frame = Image.new("RGB", (64, 32))
    pen = ImageDraw.Draw(frame)
    a, x, b, y, phase = rows
    if not b and not x:
        large(frame,a,(0,5,64,17),'#dbe9f4',tick)
        footer(frame,[phase],flag,tick)
        return frame
    for index,(name,score,color) in enumerate(((a,x,'#97ceff'),(b,y,'#a8efc1'))):
        top=index*14
        mark=badge(sport,name,17,13)
        if mark is not None:
            frame.paste(mark,((17-mark.width)//2,top+(13-mark.height)//2),mark)
        else:
            # Honest fallback: a team code, never a made-up crest.
            text(frame,clean(name)[:3],(0,top,17,top+13),color)
        code=TEAM_CODES.get(clean(name),clean(name))[:4]
        text(frame,code,(17,top,32,top+13),color)
        large(frame,(score or '-') if len(str(score))<=8 else '--',(32,top+1,64,top+12),'white',tick)
        if details and str(details.get('possession',''))==str(index):
            pen.polygon([(29,top+9),(31,top+10),(29,top+11)],fill='#ffca62')
    pen.line((0,13,63,13),fill='#18232e')
    labels=[phase]+list((details or {}).get('pages',[]))
    bases=(details or {}).get('bases') if sport=='MLB' else None
    footer(frame,labels,flag,tick,right=52 if bases is not None else 64)
    if bases is not None:
        for field,cx,cy in (('onFirst',62,29),('onSecond',59,27),('onThird',56,29)):
            pen.polygon([(cx,cy-1),(cx+1,cy),(cx,cy+1),(cx-1,cy)],
                        fill='#ffd05e' if bases.get(field) else '#39424c')
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

def tv_details(sport, competition, teams, status):
    """Only display values actually supplied by the scoreboard provider."""
    info={'pages':[]}
    situation=competition.get('situation') or {}
    if not isinstance(situation,dict): return info
    pages=info['pages']
    possession=situation.get('possession')
    for i,t in enumerate(teams):
        if possession is not None and str(possession)==str(t.get('id') or (t.get('team') or {}).get('id')):
            info['possession']=str(i)
    state=(status.get('type') or {}).get('state') if isinstance(status,dict) else status
    if state!='in': return {'pages':[]}
    if sport in ('NFL','College Football'):
        down=situation.get('shortDownDistanceText') or situation.get('downDistanceText')
        if down: pages.append(str(down).replace(' and ',' & '))
        if situation.get('possessionText'): pages.append('BALL '+str(situation['possessionText']))
    elif sport=='MLB':
        if situation.get('balls') is not None and situation.get('strikes') is not None:
            pages.append('B%s S%s' % (situation['balls'],situation['strikes']))
        if situation.get('outs') is not None: pages.append(str(situation['outs'])+' OUT')
        if all(k in situation for k in ('onFirst','onSecond','onThird')):
            info['bases']={k:bool(situation.get(k)) for k in ('onFirst','onSecond','onThird')}
    elif sport in ('NBA','NBL'):
        if situation.get('shotClock') is not None: pages.append('SHOT '+str(situation['shotClock']))
        for team in teams:
            side=team.get('team') or team
            code=str(side.get('abbreviation') or side.get('shortDisplayName') or '')[:3]
            for stat in team.get('statistics') or []:
                if stat.get('name') in ('fouls','teamFouls') and stat.get('displayValue') is not None:
                    pages.append(code+(' TOT FOULS ' if stat['name']=='fouls' else ' FOULS ')+str(stat['displayValue']))
    if sport in ('NFL','College Football','NBA','NBL'):
        for team in teams:
            if team.get('timeouts') is not None:
                code=str((team.get('team') or team).get('abbreviation') or '')[:3]
                pages.append(code+' TO '+str(team['timeouts']))
    return info


def clock_phase(sport,status,fallback):
    if not isinstance(status,dict): return fallback
    kind=status.get('type') or {}
    if kind.get('state')!='in': return fallback
    if any(word in str(fallback).lower() for word in ('half','end','delay','suspend')): return fallback
    period=status.get('period')
    clock=status.get('displayClock')
    if sport in ('NFL','College Football','NBA','NBL') and period and clock:
        return ('Q'+str(period) if int(period)<=4 else 'OT'+str(int(period)-4))+' '+str(clock)
    return fallback


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
                item=guide.game(gid,(row[0],row[2]),row[4],row[1]+" – "+row[3],row[4].lower() in ("live","inprogress","firsthalf","secondhalf"))
                clock=g.get('clock') or {}
                info={'pages':[]}
                if isinstance(clock,dict):
                    for field in ('gameClock','displayClock'):
                        if clock.get(field) is not None:
                            info['pages'].append(str(clock[field])); break
                item['display']=info
                catalog.append(item)
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
            row = pair(teams,clock_phase(sport,status,phase or "SCHEDULED"))
            detail_info = tv_details(sport,c,teams,status)
            situation = c.get("situation") or {}
            extra = ""
            if sport in ("NFL","College Football"):
                extra = situation.get("shortDownDistanceText") or situation.get("downDistanceText") or ""
            elif sport == "MLB" and all(k in situation for k in ("onFirst","onSecond","onThird")):
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
                if sport=='Cricket':
                    detail_info={'pages':[]}
                    if extra: detail_info['pages'].append(extra)
                    target=re.search(r'target\s+(\d+)',score_detail,re.I)
                    if target: detail_info['pages'].append('TARGET '+target.group(1))
                    for i,t in enumerate(teams):
                        if batting and str(t.get('id'))==batting: detail_info['possession']=str(i)
                item['display']=detail_info
                catalog.append(item)
    return games

def publish(frame):
    target = Path(os.environ["BOARD_FRAME"])
    tmp = target.with_suffix(".tmp")
    frame.save(tmp, format="PNG")
    tmp.replace(target)

DEMO_DETAILS = {
    'NFL': {'possession':'0','pages':['3RD & 7','BALL BUF 34']},
    'College Football': {'possession':'0','pages':['2ND & GOAL','BALL MICH 6']},
    'MLB': {'pages':['B2 S1','1 OUT'],'bases':{'onFirst':True,'onSecond':False,'onThird':True}},
    'NBA': {'pages':['SHOT 14','GS TO 2','BOS TO 1']},
    'NBL': {'pages':['SHOT 12']},
    'NRL': {'pages':['62:18']},
    'Cricket': {'possession':'0','pages':['TARGET 152','AUS WON']},
}


def run(sport, demo):
    games, next_update, index, offline = [], 0, 0, False
    catalog = []
    while True:
        if demo:
            games = [EXAMPLES[sport]]
            r = games[0]
            catalog = [guide.game("demo", (r[0],r[2]),r[4],r[1]+" – "+r[3],True)]
            catalog[0]["display"]=DEMO_DETAILS.get(sport,{})
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
        selected = available[(index // 5) % len(available)] if available else None
        chosen = catalog[selected] if selected is not None else {}
        guide.report(catalog,chosen.get("id",""))
        if chosen or not guide.PIN:
            rows = games[selected] if chosen else ("NO FEED" if offline else "NO MATCH","","","",sport)
            publish(draw(sport, rows, "OFFLINE" if offline else "DEMO" if demo else "",
                         chosen.get('display'),index))
        index += 1
        time.sleep(4)

if __name__ == "__main__":
    run(sys.argv[1], "--demo" in sys.argv)
