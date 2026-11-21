"""Offline check of every 64x32 renderer; safe to run before touching services."""
import sys
from pathlib import Path
from sports import EXAMPLES, draw
from scoreboard import DEMO, render
sys.path.insert(0, str(Path(__file__).parent / 'afl'))
from afl_scoreboard import demo_game, draw_game, verify_all_logos

verify_all_logos()
frames = [draw_game(demo_game())]
frames += [draw(sport, values) for sport, values in EXAMPLES.items()]
frames += [draw('AFL', ('LOADING', '', '', '', 'AFL'))]
frames += [render(fight) for fight in DEMO]
for frame in frames:
    assert frame.size == (64, 32) and frame.mode == 'RGB'
    assert frame.getbbox(), 'Empty display frame'
print('All sports, logos and UFC demo results rendered successfully.')
