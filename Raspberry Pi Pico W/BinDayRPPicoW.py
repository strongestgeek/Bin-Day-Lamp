import datetime
import time
import socket
from rpi_ws281x import Adafruit_NeoPixel, Color

s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
s.connect(('8.8.8.8',80))
ip=s.getsockname()[0]
print("IP = ", ip)

# LED strip configuration:
LED_COUNT      = 160     # Number of LED pixels.
LED_PIN        = 6       # GPIO pin connected to the pixels (must support PWM!).
LED_FREQ_HZ    = 800000  # LED signal frequency in hertz (usually 800khz)
LED_DMA        = 5       # DMA channel to use for generating signal (try 5)
LED_BRIGHTNESS = 20      # Set to 0 for darkest and 255 for brightest
LED_INVERT     = False   # True to invert the signal (when using NPN transistor level shift)

# Create NeoPixel object with appropriate configuration.
strip = Adafruit_NeoPixel(LED_COUNT, LED_PIN, LED_FREQ_HZ, LED_DMA, LED_INVERT, LED_BRIGHTNESS)
# Intialize the library (must be called once before other functions).
strip.begin()
strip.show()

# Function to set LED colours for rotated halves
def set_rotated_color(color1, color2):
    for i in range(LED_COUNT // 2):  # Loop through the left half of LED pixels
        strip.setPixelColor(i, color1)  # Set color for the left half
    for i in range(LED_COUNT // 2, LED_COUNT):  # Loop through the right half of LED pixels
        strip.setPixelColor(i, color2)  # Set color for the right half
    strip.show()

# Read colours from the file and store them in a dictionary
colors = {}
with open('colours.txt', 'r') as file:
    for line in file:
        values = line.strip().split(',')
        date = values[0]  # First value is the date
        color1 = Color(int(values[1]), int(values[2]), int(values[3]))  # RGB values for first color
        color2 = Color(int(values[4]), int(values[5]), int(values[6]))  # RGB values for second color
        colors[date] = (color1, color2)  # Store both colors as a tuple

# Get today's date in the same format as in the file
today = datetime.date.today().strftime("%Y-%m-%d")

# Check if today's date exists in the file
if today in colors:
    color1, color2 = colors[today]
    set_rotated_color(color1, color2)
    print(f"LED colours changed for {today} with new colors")
else:
    future_dates = [date for date in colors.keys() if date > today]
    if future_dates:
        next_date = min(future_dates)
        print(f"No color found for today's date, using future date: {next_date}")
        color1, color2 = colors[next_date]
        set_rotated_color(color1, color2)
    else:
        print("No color found for today's date or future dates")
