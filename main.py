# src/main.py

from squiggle_api import SquiggleAPI

def main():
    api = SquiggleAPI()

    # Fetch and display teams
    teams = api.get_teams()
    print("Teams:")
    print(teams)

    # Fetch and display games for a specific year
    year = 2023
    games = api.get_games(year=year)
    print(f"\nGames in {year}:")
    print(games)

if __name__ == "__main__":
    main()
