import requests

SQUIGGLE_API_URL = "https://api.squiggle.com.au/?q=games"

def fetch_afl_scores():
    """Fetch live AFL scores from the Squiggle API"""
    try:
        response = requests.get(SQUIGGLE_API_URL)
        data = response.json()
        return data["games"]
    except Exception as e:
        print(f"Error fetching data: {e}")
        return []

if __name__ == "__main__":
    scores = fetch_afl_scores()
    print(scores)
