# src/squiggle_api.py

import requests
import pandas as pd

class SquiggleAPI:
    BASE_URL = "https://api.squiggle.com.au/"

    def fetch_data(self, endpoint, params=None):
        url = f"{self.BASE_URL}?q={endpoint}"
        if params:
            for key, value in params.items():
                url += f"&{key}={value}"
        response = requests.get(url)
        if response.status_code == 200:
            return response.json()
        else:
            response.raise_for_status()

    def get_teams(self):
        data = self.fetch_data('teams')
        return pd.DataFrame(data['teams'])

    def get_games(self, year=None):
        params = {'year': year} if year else {}
        data = self.fetch_data('games', params)
        return pd.DataFrame(data['games'])
