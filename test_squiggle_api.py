# tests/test_squiggle_api.py

import unittest
from src.squiggle_api import SquiggleAPI

class TestSquiggleAPI(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.api = SquiggleAPI()

    def test_get_teams(self):
        teams = self.api.get_teams()
        self.assertIsInstance(teams, pd.DataFrame)
        self.assertFalse(teams.empty)

    def test_get_games(self):
        games = self.api.get_games(year=2023)
        self.assertIsInstance(games, pd.DataFrame)
        self.assertFalse(games.empty)

if __name__ == '__main__':
    unittest.main()
