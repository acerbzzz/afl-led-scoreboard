from rgbmatrix import RGBMatrix, RGBMatrixOptions, graphics
from PIL import Image

# LED Matrix Configuration
options = RGBMatrixOptions()
options.rows = 32
options.cols = 64
options.chain_length = 1
options.parallel = 1
options.hardware_mapping = "regular"  # Changed from "adafruit-hat"
matrix = RGBMatrix(options=options)

white = graphics.Color(255, 255, 255)
red = graphics.Color(255, 0, 0)

def load_team_logo(team_name):
    """Load BMP logo for a given team"""
    try:
        image = Image.open(f"logos/{team_name}.bmp")
        image = image.convert("RGB")
        return image
    except FileNotFoundError:
        print(f"Logo not found for {team_name}")
        return None

def display_scores(games):
    """Display scores on the LED matrix"""
    offscreen_canvas = matrix.CreateFrameCanvas()
    font = graphics.Font()
    font.LoadFont("fonts/7x13.bdf")

    offscreen_canvas.Clear()
    
    for game in games:
        team1 = game["hteam"]
        team2 = game["ateam"]
        score1 = f'{game["hgoals"]}.{game["hbehinds"]} ({game["hscore"]})'
        score2 = f'{game["agoals"]}.{game["abehinds"]} ({game["ascore"]})'
        quarter = game["quarter"]
        time_rem = game.get("clock", "Full Time" if quarter == "FT" else "")

        offscreen_canvas.Clear()

        # Load team logos
        logo1 = load_team_logo(team1)
        logo2 = load_team_logo(team2)

        # Draw team logos
        if logo1:
            matrix.SetImage(logo1, 0, 0)  # Left side
        if logo2:
            matrix.SetImage(logo2, 32, 0)  # Right side

        # Display scores and game info
        graphics.DrawText(offscreen_canvas, font, 2, 18, white, f"{score1} - {score2}")
        graphics.DrawText(offscreen_canvas, font, 2, 28, red, f"Q{quarter} {time_rem}")

        matrix.SwapOnVSync(offscreen_canvas)

    return offscreen_canvas

