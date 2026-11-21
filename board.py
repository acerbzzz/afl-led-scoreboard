"""Phone controller and single-owner matrix output."""
from collections import deque
import tempfile
from datetime import datetime
import base64
import argparse
import hmac
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
from urllib.parse import urlsplit

from sports import ROOT, URLS, draw, pixels
from PIL import Image, ImageDraw
sys.path.insert(0, str(ROOT / "afl"))
from afl_scoreboard import make_matrix

CHANNELS = ["AFL", "UFC", "UFC Results", *URLS]
DEFAULT = dict(sport="AFL", mode="Demo", brightness=50, names=["HOME","AWAY"],
               scores=["0","0"], phase="LIVE",pin="", favourites=[],delay=0,night=False,
               nightStart=22,nightEnd=7,nightBrightness=12)
lock = threading.Lock()
token = secrets.token_urlsafe(24)

def validated(data):
    if not isinstance(data, dict) or set(data) != set(DEFAULT):
        raise ValueError()
    if data["sport"] not in CHANNELS or data["mode"] not in ("Feed","Demo","Manual"):
        raise ValueError()
    if type(data["brightness"]) != int or not 1 <= data["brightness"] <= 100:
        raise ValueError()
    def short(v):
        return isinstance(v, str) and len(v) <= 32 and all(c.isprintable() for c in v)
    for key in ("names","scores"):
        if not isinstance(data[key],list) or len(data[key]) != 2 or not all(short(v) for v in data[key]):
            raise ValueError()
    if not isinstance(data["pin"],str) or len(data["pin"])>320:
        raise ValueError()
    if type(data["night"]) is not bool or not isinstance(data["favourites"],list) or len(data["favourites"])>64 or not all(isinstance(t,str) and 0<len(t)<=140 for t in data["favourites"]):
        raise ValueError()
    for key,low,high in (("delay",0,120),("nightStart",0,23),("nightEnd",0,23),("nightBrightness",1,100)):
        if type(data[key]) is not int or not low<=data[key]<=high:
            raise ValueError()
    if not short(data["phase"]):
        raise ValueError()
    return data

def png(frame):
    buf = BytesIO()
    frame.save(buf, "PNG")
    return buf.getvalue()

class Handler(BaseHTTPRequestHandler):
    def send(self, data, mime, code=200):
        self.send_response(code)
        self.send_header("Content-Type",mime)
        self.send_header("Content-Length",str(len(data)))
        self.send_header("Cache-Control","no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        path = urlsplit(self.path).path
        if path == "/":
            self.send((ROOT/"phone.html").read_bytes(), "text/html; charset=utf-8")
        elif path == "/api":
            with lock:
                current = (state["sport"],state["mode"],state["pin"],state["delay"])
                synced = current == display_key
                payload = dict(state=state.copy(), channels=CHANNELS, token=token,
                               status=status if synced else "Changing selection",
                               guide=listing if synced else empty_guide(), actualBrightness=actual_brightness)
            self.send(json.dumps(payload).encode(), "application/json")
        elif path == "/panel.png":
            with lock:
                data = preview
            self.send(data, "image/png")
        else:
            self.send_error(404)

    def do_POST(self):
        if self.path != "/api" or not hmac.compare_digest(self.headers.get("X-Board-Key",""), token):
            return self.send_error(403)
        try:
            size = int(self.headers.get("Content-Length","0"))
            if not 0 < size <= 16384:
                raise ValueError()
            change = json.loads(self.rfile.read(size))
            if not isinstance(change,dict):
                raise ValueError()
            with lock:
                new = validated({**state,**change})
                if (new["sport"],new["mode"]) != (state["sport"],state["mode"]):
                    new["pin"] = ""
                temp = statefile.with_suffix(".tmp")
                temp.write_text(json.dumps(new))
                temp.replace(statefile)
                state.update(new)
        except (ValueError,TypeError):
            return self.send_error(400)
        self.send(b"{}", "application/json")

    def log_message(self, *args):
        pass

def worker(s, target):
    sport = s["sport"]
    env = dict(os.environ, BOARD_FRAME=str(target),BOARD_PIN=s["pin"],BOARD_GUIDE=str(target.with_name("guide.json")))
    if sport == "AFL":
        cmd = [ROOT/"afl/afl_scoreboard.py","--cache-dir",statefile.parent/"afl-cache"]
    elif sport.startswith("UFC"):
        cmd = [ROOT/"ufc-led-scoreboard/scoreboard.py"]
        env["UFC_RESULTS_ONLY"] = str(int(sport == "UFC Results"))
    else:
        cmd = [ROOT/"sports.py", sport]
    if s["mode"] == "Demo":
        cmd.append("--demo")
    return subprocess.Popen([sys.executable,*cmd], env=env)

def stop(proc):
    if proc and proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()

def brightness(s, hour):
    start,end = s["nightStart"],s["nightEnd"]
    dim = start<=hour<end if start<=end else hour>=start or hour<end
    return min(s["brightness"],s["nightBrightness"]) if s["night"] and dim else s["brightness"]


def empty_guide():
    return dict(games=[],showing="",checked=0,health="Connecting")


def display(matrix):
    global preview,status,listing,actual_brightness,display_key
    tmp = tempfile.TemporaryDirectory()
    target = Path(tmp.name)/"current.png"
    guide_path = target.with_name("guide.json")
    held = statefile.parent/"pinned.json"
    queue = deque()
    proc = previous = manual_card = last_visible = None
    retry = stamp = gstamp = 0
    try:
        while True:
            with lock:
                s = state.copy()
            sport,mode,pin,delay = (s[k] for k in ("sport","mode","pin","delay"))
            key = (sport,mode,pin,delay)
            now = time.monotonic()
            switched = key != previous
            if switched:
                stop(proc)
                proc = None
                previous = key
                queue.clear()
                target.unlink(missing_ok=True)
                guide_path.unlink(missing_ok=True)
                stamp = gstamp = retry = 0
                manual_card = None
                guide = empty_guide()
                visible = draw(sport,("LOADING","","","","TV DELAY" if delay else sport))
                message = "Buffering TV delay" if delay else "Loading "+sport
                last_visible = None
                held_game = None
                if pin and held.exists():
                    cache = json.loads(held.read_text())
                    if cache["key"] == list(key):
                        last_visible = base64.b64decode(cache["png"])
                        visible = Image.open(BytesIO(last_visible)).convert("RGB")
                        guide = cache["guide"]
                        held_game = next((g for g in guide["games"] if g["id"]==pin),None)
                        guide["health"] = "Reconnecting"
                        message = "Showing saved pinned game"
                with lock:
                    display_key = key
                    listing = guide
                    preview = png(visible)
                    status = message
                if matrix:
                    matrix.SetImage(visible)
            actual_brightness = brightness(s,datetime.now().hour)
            if matrix:
                matrix.brightness = actual_brightness
            frame = None
            changed = False
            if mode == "Manual":
                if s != manual_card:
                    manual_card = s
                    a,b = s["names"]
                    x,y = s["scores"]
                    frame = draw(sport,(a,x,b,y,s["phase"]),"MANUAL")
                    guide = dict(empty_guide(),health="Manual")
                    changed = True
            elif sport=="AFL" and mode=="Feed" and not os.environ.get("SQUIGGLE_CONTACT_EMAIL"):
                with lock:
                    status="AFL feed needs the Squiggle contact email"
            else:
                if proc is not None and proc.poll() is not None:
                    if not (sport=="AFL" and mode=="Demo" and proc.returncode==0):
                        proc=None
                        retry=now+10
                        with lock:
                            status="Channel stopped · retrying in 10 seconds"
                            listing=dict(listing,health="Retrying")
                if proc is None and now>=retry:
                    proc=worker(s,target)
                if guide_path.exists() and guide_path.stat().st_mtime_ns!=gstamp:
                    with guide_path.open() as f:
                        gstamp=os.fstat(f.fileno()).st_mtime_ns
                        guide=json.load(f)
                    changed=True
                if target.exists() and target.stat().st_mtime_ns!=stamp:
                    with Image.open(target) as im:
                        stamp=os.fstat(im.fp.fileno()).st_mtime_ns
                        frame=im.convert("RGB")
            if frame is not None or changed:
                queue.append((now+(delay if mode!="Manual" else 0),frame,guide))
            while queue and queue[0][0]<=now:
                _,ready,meta=queue.popleft()
                if ready is not None:
                    data=png(ready)
                    if matrix:
                        matrix.SetImage(ready)
                    with lock:
                        preview=data
                    if pin and meta["showing"]==pin:
                        held_game=next((g for g in meta["games"] if g["id"]==pin),held_game)
                    if pin and meta["showing"]==pin and data!=last_visible:
                        cache=dict(key=key,png=base64.b64encode(data).decode(),guide=meta)
                        temp=held.with_suffix(".tmp")
                        temp.write_text(json.dumps(cache))
                        temp.replace(held)
                        last_visible=data
                if (meta["health"]=="Offline" or (pin and not meta["showing"])) and (ready is not None or last_visible):
                    overlay = ready.copy() if ready is not None else Image.open(BytesIO(last_visible)).convert("RGB")
                    pen = ImageDraw.Draw(overlay)
                    pen.rectangle((0,0,31,5),fill="black")
                    pixels(pen,0,1,"OFFLINE" if meta["health"]=="Offline" else "HELD","#ffbf50",32)
                    if matrix:
                        matrix.SetImage(overlay)
                    with lock:
                        preview=png(overlay)
                health=meta["health"]
                message = "Waiting for pinned game" if pin and not meta["showing"] else sport+" · "+health
                if pin and not meta["showing"] and last_visible:
                    message="Holding last pinned score"
                    if held_game and not any(g["id"]==pin for g in meta["games"]):
                        meta=dict(meta,games=[held_game,*meta["games"]])
                with lock:
                    listing=meta
                    status=message
            time.sleep(.10 if sport.startswith("UFC") else .25)
    finally:
        stop(proc)
        tmp.cleanup()
        if matrix:
            matrix.Clear()

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--matrix",action="store_true")
    parser.add_argument("--mapping",default="regular")
    parser.add_argument("--gpio-slowdown",type=int,default=2)
    parser.add_argument("--port",type=int,default=8765)
    parser.add_argument("--data",type=Path,default=Path.home()/".pi-scoreboard")
    args = parser.parse_args()
    args.brightness = 50
    matrix = make_matrix(args) if args.matrix else None
    if os.geteuid() == 0 and args.matrix:
        import pwd
        daemon = pwd.getpwnam("daemon")
        os.setgroups([])
        os.setgid(daemon.pw_gid)
        os.setuid(daemon.pw_uid)
    args.data.mkdir(exist_ok=True, parents=True)
    statefile = args.data.resolve()/"settings.json"
    state = json.loads(statefile.read_text()) if statefile.exists() else DEFAULT.copy()
    if state.get("sport") == "A-League":
        state["sport"] = "AFL"
    state=validated({**DEFAULT,**state})
    listing=empty_guide()
    display_key=None
    actual_brightness=state["brightness"]
    status = "Starting scoreboard"
    preview = png(Image.new("RGB",(64,32)))
    server = ThreadingHTTPServer(("0.0.0.0",args.port),Handler)
    threading.Thread(target=server.serve_forever,daemon=True).start()
    display(matrix)
