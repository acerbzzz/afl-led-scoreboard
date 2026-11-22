"""F1 sessions and classification on a 64x32 panel, with driver pinning."""
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import re
import sys
import time
from urllib.request import Request, urlopen
from PIL import Image
import gameguide as guide
from ledlayout import text, large, footer, pages, clean
from badgeart import badge

URL='https://site.api.espn.com/apis/site/v2/sports/racing/f1/scoreboard'
CORE='https://sports.core.api.espn.com/v2/sports/racing/leagues/f1/events/{event}/competitions/{session}/competitors/{driver}'


def get(url):
    with urlopen(Request(url,headers={'User-Agent':'Pi-scoreboard/1.0'}),timeout=8) as response:
        return json.load(response)


def number(value):
    try:
        n=int(value)
        return n if n>0 else None
    except (ValueError,TypeError):
        return None


def sessions(payload):
    if not isinstance(payload.get('events'),list):
        raise ValueError('F1 events missing')
    result=[]
    for event in payload['events']:
        for c in event.get('competitions',[]):
            status=c.get('status') or {}
            kind=status.get('type') or {}
            session_type=(c.get('type') or {}).get('abbreviation') or 'F1'
            drivers=[]
            for competitor in c.get('competitors',[]):
                athlete=competitor.get('athlete') or {}
                name=athlete.get('displayName') or athlete.get('fullName') or 'TBA'
                # A scheduled entry list is not a grid or classification.
                position=number(competitor.get('order')) if kind.get('state')!='pre' else None
                drivers.append(dict(id=str(competitor.get('id','')),name=name,
                    code=clean(athlete.get('abbreviation') or name.split()[-1])[:3],
                    position=position,winner=bool(competitor.get('winner')),team='',color='#a8c7e0',gap=''))
            drivers.sort(key=lambda d:d['position'] if d['position'] is not None else 999)
            result.append(dict(id=str(c.get('id','')),event=str(event.get('id','')),
                title=event.get('shortName') or event.get('name') or 'Grand Prix',
                date=c.get('date',''),kind=session_type,state=kind.get('state','pre'),
                phase=kind.get('shortDetail') or kind.get('description') or session_type,
                lap=number(status.get('period')) if session_type.lower() in ('race','sprint') and kind.get('state')!='pre' else None,
                drivers=drivers))
    return result


def choose(items):
    live=[s for s in items if s['state']=='in']
    completed=[s for s in items if s['state']=='post']
    # Prefer the active session, then latest completed, then upcoming.
    return (sorted(live,key=lambda s:s['date'],reverse=True) or
            sorted(completed,key=lambda s:s['date'],reverse=True) or
            sorted(items,key=lambda s:s['date']) or [None])[0]


def driver_key(session,driver):
    return session['event']+'-'+session['id']+'-'+driver['id']


def details(session,driver):
    if not all(str(v).isdigit() for v in (session['event'],session['id'],driver['id'])):
        return {}
    url=CORE.format(event=session['event'],session=session['id'],driver=driver['id'])
    info=get(url)
    vehicle=info.get('vehicle') or {}
    color=str(vehicle.get('teamColor') or '')
    result={'team':str(vehicle.get('manufacturer') or '')}
    if re.fullmatch('[0-9a-fA-F]{6}',color):result['color']='#'+color
    try:
        raw=get(url+'/statistics')
        stats={v['name']:v.get('displayValue','') for category in (raw.get('splits') or {}).get('categories',[]) for v in category.get('stats',[]) if 'name' in v}
        result['gap']=str(stats.get('gap') or stats.get('timeBehind') or '')
        result['elapsed']=str(stats.get('totalTime') or '')
        result['laps']=str(stats.get('lapsCompleted') or '')
    except (OSError,ValueError,TypeError):
        pass
    return result


def draw(session,tick=0,flag='',driver=None):
    image=Image.new('RGB',(64,32))
    mark=badge('F1','F1',13,6)
    if mark is not None:image.paste(mark,(0,0),mark)
    if not session:
        large(image,'NO SESSION',(0,9,64,20),'white')
        footer(image,['F1'],flag,tick)
        return image
    header='DEMO' if flag=='DEMO' else clean(session['kind'])[:4]
    text(image,header,(15,0,32,5),'#ff5050')
    lap='L'+str(session['lap']) if session['lap'] else ('FINAL' if session['state']=='post' else 'LIVE' if session['state']=='in' else 'NEXT')
    text(image,lap[:7],(34,0,64,5),'#ffca62')
    drivers=session['drivers']
    if driver is not None:
        rank='P'+str(driver['position']) if driver['position'] else '--'
        text(image,rank,(0,9,15,14),'#ffca62')
        large(image,driver.get('surname') or driver['name'].split()[-1],(17,7,64,17),driver['color'],tick)
        team_pages=pages(driver.get('team') or 'TEAM PENDING',16)
        text(image,team_pages[int(tick)%len(team_pages)],(0,20,64,25),'white')
        labels=[driver.get('gap') or ('WINNER' if driver['winner'] else session['phase'])]
        if driver.get('elapsed'):labels.append('TIME '+driver['elapsed'])
        if driver.get('laps'):labels.append(driver['laps']+' LAPS')
    else:
        start=((int(tick)//2)%max(1,(len(drivers)+2)//3))*3
        for row,d in enumerate(drivers[start:start+3]):
            y=7+row*7
            text(image,str(d['position'] or '--'),(0,y,9,y+5),'#ffca62')
            text(image,d['code'],(11,y,24,y+5),d['color'])
            gap=d.get('gap') or ('WIN' if d['winner'] else '-')
            fragments=pages(gap,9)
            text(image,fragments[int(tick)%len(fragments)],(27,y,64,y+5),'white',align='right')
        labels=[session['title'],session['kind']+' '+('FINAL' if session['state']=='post' else session['phase'])]
    # DEMO is already visible in the top bar; other flags reserve the footer.
    footer(image,labels,'' if flag=='DEMO' else flag,tick)
    return image


DEMO=dict(id='demo',event='demo',title='AUSTRALIAN GP',date='',kind='Race',state='in',phase='LIVE',lap=18,
    drivers=[dict(id='81',name='Oscar Piastri',code='PIA',position=1,winner=False,team='MCLAREN',color='#ff8700',gap='LEADER'),
             dict(id='4',name='Lando Norris',code='NOR',position=2,winner=False,team='MCLAREN',color='#ff8700',gap='+1.4'),
             dict(id='1',name='Max Verstappen',code='VER',position=3,winner=False,team='RED BULL',color='#67a4ff',gap='+3.2')])


def run(demo=False):
    current=None
    next_update=0
    offline=False
    tick=0
    pending={}
    cache={}
    pool=ThreadPoolExecutor(max_workers=2)
    try:
        while True:
            if demo:
                current=DEMO
                guide.feed('Demo')
            elif time.monotonic()>=next_update:
                try:
                    current=choose(sessions(get(URL)))
                    offline=False
                    guide.feed('Connected')
                except (OSError,ValueError,KeyError,TypeError) as exc:
                    print('F1 feed:',exc,flush=True)
                    offline=True
                    guide.feed('Offline')
                next_update=time.monotonic()+30
            drivers=current['drivers'] if current else []
            for d in drivers:
                key=driver_key(current,d)
                if key in pending and pending[key].done():
                    future=pending.pop(key)
                    try:cache[key]=(future.result(),time.monotonic()+120)
                    except Exception:cache[key]=({},time.monotonic()+120)
                if key in cache:d.update(cache[key][0])
            selected=next((d for d in drivers if driver_key(current,d)==guide.PIN),None)
            visible=[selected] if selected else drivers[((tick//2)%max(1,(len(drivers)+2)//3))*3:][:3]
            if not demo and not offline:
                for d in visible:
                    key=driver_key(current,d)
                    if key not in pending and time.monotonic()>=cache.get(key,({},0))[1] and len(pending)<4:
                        pending[key]=pool.submit(details,current.copy(),d.copy())
            listing=[]
            for d in drivers:
                description=' · '.join(filter(None,[d.get('team'),d.get('gap')]))
                item=guide.game(driver_key(current,d),[d['name']],
                    current['kind']+' '+('P'+str(d['position']) if d['position'] else 'UPCOMING'),description,current['state']=='in')
                listing.append(item)
            showing=driver_key(current,selected) if selected else driver_key(current,visible[0]) if visible else ''
            guide.report(listing,showing)
            if not guide.PIN or selected:
                frame=draw(current,tick,'DEMO' if demo else 'OFFLINE' if offline else '',selected)
                target=Path(os.environ['BOARD_FRAME'])
                temp=target.with_suffix('.tmp')
                frame.save(temp,format='PNG')
                temp.replace(target)
            tick+=1
            time.sleep(4)
    finally:
        pool.shutdown(wait=False)


if __name__=='__main__':run('--demo' in sys.argv)
