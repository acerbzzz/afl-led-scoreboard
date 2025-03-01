import time
from fetch_scores import fetch_afl_scores
from display import display_scores

def run_scoreboard():
    """Fetch AFL scores and display them continuously"""
    while True:
        games = fetch_afl_scores()
        display_scores(games)
        time.sleep(10)

if __name__ == "__main__":
    run_scoreboard()
