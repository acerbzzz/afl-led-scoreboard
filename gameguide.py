"""Publish the active channel's fixtures and feed health to the local remote."""
import json
import os
from pathlib import Path
import time

PIN = os.environ.get("BOARD_PIN", "")
checked = 0.0
health = "Connecting"

def feed(status, at=None):
    global checked, health
    health = status
    if status in ("Connected", "Cached"):
        checked = at if at is not None else time.time()

def game(key, teams, phase, detail="", live=False):
    return dict(id=str(key), teams=list(teams), phase=str(phase), detail=str(detail), live=bool(live))

def report(games, showing=""):
    target = os.environ.get("BOARD_GUIDE")
    if target:
        path = Path(target)
        tmp = path.with_suffix(".part")
        tmp.write_text(json.dumps(dict(games=games, showing=showing, checked=checked, health=health)))
        tmp.replace(path)
