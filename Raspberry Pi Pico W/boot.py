import network
import time
import utime
import ntptime
import array
from machine import Pin
import rp2
from datetime import datetime, date

ssid = 'My_WiFi'
password = 'WiFi_Pass'

wlan = network.WLAN(network.STA_IF)
wlan.active(True)
wlan.connect(ssid, password)

max_wait = 10
while max_wait > 0:
    if wlan.status() < 0 or wlan.status() >= 3:
        break
    max_wait -= 1
    print('Waiting for connection...')
    time.sleep(1)

if wlan.status() != 3:
    raise RuntimeError('Network connection failed')
else:
    print('Wi-Fi connected')
    time.sleep(2)
    status = wlan.ifconfig()
    print( 'IP = ' + status[0] )
    time.sleep(2)

# Update the RTC
def update_rtc():
    print('Updating RTC from internet...')
    ntptime.settime()
    print('RTC updated:', utime.localtime())
update_rtc()

# Format and get today's date
today_date = date.today()
print("Today's date:", today_date)
today_string = today_date.isoformat()

# Configure the number of WS2812 LEDs.
NUM_LEDS = 160
PIN_NUM = 6
LED_BRIGHTNESS = 0.1 # Pick between 0 and 1

# Define the table as a list of lists
table = [
    ['2023-12-15',0,255,0,128,0,128],
    ['2023-12-22',0,0,255,0,0,255],
    ['2023-12-31',0,255,0,0,255,0],
    ['2024-01-06',128,0,128,128,0,128],
    ['2024-01-12',0,255,0,0,255,0],
    ['2024-01-19',0,0,255,0,0,255],

]

# Sort the table based on the dates
table.sort(key=lambda x: x[0])

@rp2.asm_pio(sideset_init=rp2.PIO.OUT_LOW, out_shiftdir=rp2.PIO.SHIFT_LEFT, autopull=True, pull_thresh=24)
def ws2812():
    T1 = 2
    T2 = 5
    T3 = 3
    wrap_target()
    label("bitloop")
    out(x, 1)               .side(0)    [T3 - 1]
    jmp(not_x, "do_zero")   .side(1)    [T1 - 1]
    jmp("bitloop")          .side(1)    [T2 - 1]
    label("do_zero")
    nop()                   .side(0)    [T2 - 1]
    wrap()

class NeoPixel(object):
    def __init__(self, pin=PIN_NUM, num=NUM_LEDS, brightness=0.1):
        self.pin = pin
        self.num = num
        self.brightness = brightness

        self.sm = rp2.StateMachine(0, ws2812, freq=8_000_000, sideset_base=Pin(PIN_NUM))
        self.sm.active(1)

        self.ar = array.array("I", [0 for _ in range(self.num)])

    def pixels_show(self):
        dimmer_ar = array.array("I", [0 for _ in range(self.num)])
        for i, c in enumerate(self.ar):
            r = int(((c >> 16) & 0xFF) * self.brightness)
            g = int(((c >> 8) & 0xFF) * self.brightness)
            b = int((c & 0xFF) * self.brightness)
            dimmer_ar[i] = (r << 16) + (g << 8) + b
        self.sm.put(dimmer_ar, 8)

    def pixels_set(self, i, color):
        self.ar[i] = (color[0] << 16) + (color[1] << 8) + color[2]
        
# Initializing colours dictionary
colors = {}

for row in table:
    date = row[0]
    color1 = (row[1], row[2], row[3])
    color2 = (row[4], row[5], row[6])
    colors[date] = (color1, color2)

led_grid = NeoPixel()

# Convert date strings to sortable integers for comparison
date_values = {date_str: int(date_str.replace('-', '')) for date_str in colors}

today_value = int(today_string.replace('-', ''))
next_date = None

for date_str in sorted(date_values.keys()):
    print("Checking date:", date_str, "Current date:", today_string)
    if date_values[date_str] > today_value:
        next_date = date_values[date_str]
        break

if today_value in date_values.values():
    date_key = next(key for key, value in date_values.items() if value == today_value)
    color1, color2 = colors[date_key]
elif next_date is not None:
    next_date_str = str(next_date)
    next_date_key = next(key for key, value in date_values.items() if value == next_date)
    color1, color2 = colors[next_date_key]
else:
    # If no active or next date is found, exit without changing LED colours
    print("No active or next date found")
    exit()

# Multiply each component of color1 and color2 by LED_BRIGHTNESS factor
color1_adjusted = tuple(int(component * LED_BRIGHTNESS) for component in color1)
color2_adjusted = tuple(int(component * LED_BRIGHTNESS) for component in color2)

# Instantiate NeoPixel class
led_strip = NeoPixel()

# Set the LEDs in the left 8 columns to color1_adjusted and the right 8 columns to color2_adjusted
for row in range(10):
    for col in range(16):
        if col < 8:
            led_strip.pixels_set(row * 16 + col, color1_adjusted)
        else:
            led_strip.pixels_set(row * 16 + col, color2_adjusted)

next_date_str = str(next_date)
formatted_next_date = f"{next_date_str[:4]}-{next_date_str[4:6]}-{next_date_str[6:]}"

led_strip.pixels_show()  # Display the changes
print(f"LED colours changed for {today_string if today_string in colors else formatted_next_date} with adjusted layout")
