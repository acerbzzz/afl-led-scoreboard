import requests
import json
import time
from PIL import Image, ImageDraw, ImageFont
from rgbmatrix import RGBMatrix, RGBMatrixOptions

# Load API key from config.json
with open("config.json") as config_file:
    config = json.load(config_file)

API_KEY = config["api_key"]
UPDATE_INTERVAL = config["update_interval"]

# LED Matrix Configuration
options = RGBMatrixOptions()
options.rows = 32
options.cols = 64
options.chain_length = 1
options.parallel = 1
options.hardware_mapping = "regular"
matrix = RGBMatrix(options=options)

# Load font
font = ImageFont.truetype("arial.ttf", 10)

# Fetch live AFL scores from Squiggle API
def get_scores():
    url = f"https://api.squiggle.com.au/?q=games&year=2025&apikey={API_KEY}"
    response = requests.get(url)
    if response.status_code == 200:
        return response.json().get("games", [])
    return []

# Display scoreboard on the LED matrix
def display_scoreboard():
    while True:
        games = get_scores()
        image = Image.new("RGB", (64, 32), (0, 0, 0))
        draw = ImageDraw.Draw(image)

        if games:
            game = games[0]  # Display first game
            home_team = game["hteam"]
            away_team = game["ateam"]
            home_score = game["hscore"]
            away_score = game["ascore"]
            quarter = game.get("quarter", "Q1")
            time_left = game.get("clock", "00:00")

            draw.text((2, 2), f"{home_team} {home_score}", font=font, fill=(255, 255, 255))
            draw.text((2, 14), f"{away_team} {away_score}", font=font, fill=(255, 255, 255))
            draw.text((40, 2), f"{quarter}", font=font, fill=(255, 0, 0))
            draw.text((40, 14), f"{time_left}", font=font, fill=(0, 255, 0))

        matrix.SetImage(image)
        time.sleep(UPDATE_INTERVAL)

# Run scoreboard display
display_scoreboard()
