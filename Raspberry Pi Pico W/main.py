import network
import time
import utime
import ntptime
import array
from machine import Pin
import rp2

# --- WiFi Credentials ---
# !!! REPLACE WITH YOUR ACTUAL WIFI DETAILS !!!
SSID = 'MyWiFi'
PASSWORD = '12345678'

# --- NeoPixel Settings ---
NUM_LEDS = 160      # Number of LEDs in your strip
PIN_NUM = 6        # GPIO pin connected to Data In (DI/DIN)
LED_BRIGHTNESS = 0.02 # Brightness (0.0 to 1.0)

# --- LED Colors (RGB) ---
COLOR_BLUE = (0, 0, 255)   # Only recycling
COLOR_GREEN = (255, 0, 0)    # Green bin
COLOR_RED = (0, 255, 0)      # Error or undefined state
COLOR_OFF = (0, 0, 0)        # LEDs off
COLOR_PURPLE = (0, 128, 128) # Representing Black bin

# --- PIO Program for WS2812 LEDs ---
@rp2.asm_pio(
    sideset_init=rp2.PIO.OUT_LOW,
    out_shiftdir=rp2.PIO.SHIFT_LEFT,
    autopull=True,
    pull_thresh=24
)
def ws2812():
    T1 = 2
    T2 = 5
    T3 = 3
    wrap_target()
    label("bitloop")
    out(x, 1)               .side(0) [T3 - 1]
    jmp(not_x, "do_zero")   .side(1) [T1 - 1]
    jmp("bitloop")          .side(1) [T2 - 1]
    label("do_zero")
    nop()                   .side(0) [T2 - 1]
    wrap()

# --- NeoPixel Class ---
class NeoPixel:
    def __init__(self, pin_num=PIN_NUM, num_leds=NUM_LEDS, brightness=LED_BRIGHTNESS):
        self.pin_num = pin_num
        self.num_leds = num_leds
        self.brightness = max(0.0, min(1.0, brightness)) # Clamp brightness
        self.sm = rp2.StateMachine(0, ws2812, freq=8_000_000, sideset_base=Pin(self.pin_num))
        self.sm.active(1)
        # Array stores colors in GRB format for direct PIO use
        self.ar = array.array("I", [0] * self.num_leds)

    def pixels_show(self):
        # Apply brightness - Note: colors already stored in GRB format in self.ar
        dimmer_ar = array.array("I", [0] * self.num_leds)
        for i, c in enumerate(self.ar):
            g = int(((c >> 16) & 0xFF) * self.brightness) # Extract G
            r = int(((c >> 8) & 0xFF) * self.brightness)  # Extract R
            b = int((c & 0xFF) * self.brightness)         # Extract B
            dimmer_ar[i] = (g << 16) + (r << 8) + b       # Reassemble GRB with brightness
        self.sm.put(dimmer_ar, 8) # Send data to PIO state machine
        # A small delay might be needed by some strips after sending data
        # time.sleep_ms(1)

    def pixels_set(self, i, color):
        # Sets pixel 'i' to 'color' tuple (r, g, b)
        # Stores color in GRB format in the array
        if 0 <= i < self.num_leds:
            r, g, b = color
            # Store as GRB unsigned integer: (G << 16) + (R << 8) + B
            self.ar[i] = (g << 16) + (r << 8) + b

    def pixels_fill(self, color):
        # Fill all pixels with the same color
        r, g, b = color
        grb_color = (g << 16) + (r << 8) + b # Calculate GRB integer once
        for i in range(self.num_leds):
            self.ar[i] = grb_color

# --- WiFi Connection ---
def connect_wifi():
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    wlan.connect(SSID, PASSWORD)
    max_wait = 15 # Increased wait time
    while max_wait > 0:
        status = wlan.status()
        if status < 0 or status >= 3:
            break
        max_wait -= 1
        time.sleep(1)

    if wlan.status() != 3:
        return False
    else:
        config = wlan.ifconfig()
        return True

# --- Time Synchronization ---
def sync_time():
    # Pico RTC doesn't track timezones well, NTP usually provides UTC
    try:
        ntptime.settime() # Sets UTC time from NTP server
        # Get time immediately after sync
        current_utc_timestamp = utime.time()
        current_local_tuple = utime.localtime(current_utc_timestamp) # localtime() uses board's configured offset from UTC (usually 0)
        return True
    except Exception as e:
        # Common errors: OSError: -2 (No route to host / DNS failure?), OSError: 110 (ETIMEDOUT)
        return False

# --- Date Handling Helpers ---
def get_current_date():
    # Returns (year, month, day) tuple based on device's current time (hopefully UTC)
    current_time_tuple = utime.localtime() # Use current device time
    return current_time_tuple[:3]

def date_to_tuple(date_str):
    # Parses YYYYMMDD string to (year, month, day) tuple
    try:
        return (int(date_str[:4]), int(date_str[4:6]), int(date_str[6:8]))
    except ValueError:
        return None

def date_compare(date1_tuple, date2_tuple):
    # Compares two (year, month, day) tuples.
    # Returns > 0 if date1 > date2, < 0 if date1 < date2, 0 if equal.
    if date1_tuple[0] != date2_tuple[0]:
        return date1_tuple[0] - date2_tuple[0]
    if date1_tuple[1] != date2_tuple[1]:
        return date1_tuple[1] - date2_tuple[1]
    return date1_tuple[2] - date2_tuple[2]

# --- ICS Parsing (Minimal) ---
def parse_ics(ics_content):
    # Very basic parser, assumes simple structure
    events = []
    current_event = {}
    in_event = False
    for line in ics_content.splitlines(): # Use splitlines() for robustness
        line = line.strip()
        if line == "BEGIN:VEVENT":
            in_event = True
            current_event = {}
        elif line == "END:VEVENT" and in_event:
            if "dtstart" in current_event and "rrule" in current_event and "summary" in current_event:
                 events.append(current_event)
            in_event = False
            current_event = {} # Reset for next event
        elif in_event and ":" in line:
            try:
                key, value = line.split(":", 1)
                # Handle potential parameters in DTSTART (e.g., DTSTART;VALUE=DATE:...)
                if key.startswith("DTSTART"):
                    if "VALUE=DATE" in key: # All-day event format YYYYMMDD
                         current_event["dtstart"] = value
                    else: # Might be DTSTART;TZID=...:YYYYMMDDTHHMMSSZ format
                         # Try to extract just the date part if it's a datetime
                         if 'T' in value:
                             current_event["dtstart"] = value.split('T')[0]
                         else: # Assume it's already YYYYMMDD if no 'T'
                             current_event["dtstart"] = value
                elif key == "RRULE":
                    current_event["rrule"] = value
                elif key == "SUMMARY":
                    current_event["summary"] = value
            except ValueError:
                continue # Skip malformed line
    return events

# --- Date Computation from RRULE (Simplified) ---
def compute_dates(dtstart, rrule, current_year):
    # Simplified: Handles only FREQ=WEEKLY and INTERVAL=n
    # Assumes DTSTART is the first occurrence and day of week is fixed by DTSTART
    # Does NOT parse BYDAY, COUNT, UNTIL etc. from RRULE
    # Returns list of (Y, M, D) tuples for the current year and potentially next year
    dates = []
    start_date_tuple = date_to_tuple(dtstart)
    if not start_date_tuple:
        return []

    # Try to extract interval
    interval = 1 # Default interval
    if 'INTERVAL=' in rrule:
        try:
            interval_part = rrule.split('INTERVAL=')[1]
            interval = int(interval_part.split(';')[0]) # Get integer before next semicolon or end
        except ValueError:
            interval = 1

    # !!! CRITICAL LIMITATION !!!
    # This code DOES NOT parse BYDAY from RRULE. It assumes ALL events occur
    # on the same day of the week as the DTSTART date.
    # If your collections are on different days, this function WILL BE WRONG.
    # Example RRULE needing better parsing: FREQ=WEEKLY;INTERVAL=2;BYDAY=WE

    # Calculate start time timestamp (potential issues with timezones/DST if not careful)
    try:
        # Use utime.mktime - expects (year, month, day, hour, min, sec, weekday, yearday)
        # We only care about the date part for weekly calculations
        start_weekday = time.gmtime(utime.mktime(start_date_tuple + (0,0,0,0,0)))[6] # Get weekday (Mon=0)
        current_date_secs = utime.mktime(start_date_tuple + (0,0,0,0,0)) # Seconds since epoch for DTSTART
    except OverflowError:
         return []
    except Exception as e:
         return []


    # Calculate end time (e.g., end of next year to be safe)
    end_year = current_year + 1
    end_limit_secs = utime.mktime((end_year, 12, 31, 0, 0, 0, 0, 0))

    seconds_per_week = 7 * 24 * 60 * 60
    seconds_increment = seconds_per_week * interval

    computed_count = 0
    # Loop through time, adding interval weeks
    while current_date_secs <= end_limit_secs:
        current_tuple = utime.localtime(current_date_secs) # Get (Y,M,D,H,M,S,Wday,Yday)
        current_ymd = current_tuple[:3]

        # Add date if it's within the target range (current year or start of next)
        if current_ymd[0] >= current_year -1: # Include calculation from start date even if last year
             # Add the date tuple (Y, M, D)
             if current_ymd not in dates: # Avoid duplicates if logic overlaps
                 dates.append(current_ymd)
                 computed_count +=1
        # Move to the next occurrence
        current_date_secs += seconds_increment
    return dates

# --- Get Next Bin Day Logic (Modified for Local Files) ---
def get_next_bin_day():
    # --- Time Sync is STILL NEEDED for accurate date comparisons ---
    if not sync_time():
         return None, [] # Indicate failure

    current_date_tuple = get_current_date()
    current_year = current_date_tuple[0]

    all_events = []
    # --- Define the paths to the local files on the Pico's filesystem ---
    # Assumes files are in the root directory. If you put them in a folder
    # named 'data', use "/data/B1-5.ics" for example.
    local_files = ["/B1-5.ics", "/G1-5.ics"]

    for file_path in local_files:
        try:
            # Open the local file for reading ('r')
            with open(file_path, 'r') as f:
                ics_content = f.read() # Read the entire file content
            # Parse the content read from the file
            parsed_events = parse_ics(ics_content)
            all_events.extend(parsed_events)

        except OSError as e:
            # OSError typically means "File not found" in MicroPython
            continue # Try the next file in the list
        except Exception as e:
            continue # Try the next file
    if not all_events:
        return None, []
    relevant_summaries = ["Recycling trolley collection", "Black bin collection", "Green bin collection"]
    bin_dates = []
    for event in all_events:
        summary = event.get("summary", "Unknown").strip()
        dtstart = event.get("dtstart")
        rrule = event.get("rrule")
        if summary in relevant_summaries and dtstart and rrule:
             dates = compute_dates(dtstart, rrule, current_year)
             for date_tuple in dates:
                 bin_dates.append((date_tuple, summary))
        else:
             pass # Skip irrelevant/incomplete events
    if not bin_dates:
        return None, []
    bin_dates.sort()
    next_collection_date = None
    next_collection_bins = []
    for date_tuple, summary in bin_dates:
        comparison = date_compare(date_tuple, current_date_tuple)
        if comparison > 0:
            if next_collection_date is None:
                next_collection_date = date_tuple
                next_collection_bins.append(summary)
            elif date_tuple == next_collection_date:
                if summary not in next_collection_bins:
                     next_collection_bins.append(summary)
            else:
                break # Stop searching
    if next_collection_date:
    else:
    return next_collection_date, next_collection_bins

# --- Update LEDs based on Bin Data (Handles Black+Green Split - LEFT/RIGHT) ---
def update_leds(led_strip, bins_for_next_day):
    BLACK_BIN = "Black bin collection"
    GREEN_BIN = "Green bin collection"
    RECYCLING_BIN = "Recycling trolley collection"
    has_black = BLACK_BIN in bins_for_next_day
    has_green = GREEN_BIN in bins_for_next_day
    has_recycling = RECYCLING_BIN in bins_for_next_day
    message = "Unknown State"

    # --- Priority 1: Handle specific Black AND Green case ---
    if has_black and has_green:
        message = "Next: Black bin + Green bin"
        if has_recycling: message += " + Recycling"

        matrix_width = 16 # Define matrix width (16 LEDs wide)
        mid_column = matrix_width // 2 # Split point is column 8

        for i in range(NUM_LEDS):
            # Calculate column index assuming simple L->R, Top->Bottom wiring
            # (index 0 is top-left, index 15 is top-right, index 16 is middle-left row 2)
            col = i % matrix_width

            # Split based on column index
            if col < mid_column: # Columns 0-7 = Left half
                led_strip.pixels_set(i, COLOR_GREEN)
            else: # Columns 8-15 = Right half
                led_strip.pixels_set(i, COLOR_PURPLE) # Purple represents black bin

    # --- Priorities 2, 3, 4, 5, Fallback remain the same as previous version ---
    # (Handling Black only, Green only, Recycling only, No bins/Error)
    elif has_black:
        led_strip.pixels_fill(COLOR_PURPLE)
        message = "Next: Black bin"
        if has_recycling: message += " + Recycling"
    elif has_green:
        led_strip.pixels_fill(COLOR_GREEN)
        message = "Next: Green bin"
        if has_recycling: message += " + Recycling"
    elif len(bins_for_next_day) == 1 and has_recycling:
        led_strip.pixels_fill(COLOR_BLUE)
        message = "Next: Recycling only"
    elif not bins_for_next_day:
        led_strip.pixels_fill(COLOR_RED)
        message = "Error or no bins found"
    else:
        led_strip.pixels_fill(COLOR_RED)
        message = "Error: Unknown bin combination"
    led_strip.pixels_show()

# --- Main Execution Loop ---
def main():
    # Initialize NeoPixel strip early so we can show status
    led_strip = NeoPixel(PIN_NUM, NUM_LEDS, LED_BRIGHTNESS)
    led_strip.pixels_fill(COLOR_RED) # Start with Red to indicate booting/connecting
    led_strip.pixels_show()
    time.sleep(1) # Small delay
    if not connect_wifi():
        # Keep LEDs Red
        while True: time.sleep(60) # Stay here, maybe blink red?
    # Indicate WiFi connected (optional)
    led_strip.pixels_fill(COLOR_GREEN) # Green briefly for WiFi OK
    led_strip.pixels_show()
    time.sleep(2)
    led_strip.pixels_fill(COLOR_OFF) # Turn off before first check
    led_strip.pixels_show()
    while True:
        current_hour = utime.localtime()[3] # Get current hour (approx UTC)
        next_date, next_bins = get_next_bin_day() # Fetch and process data
        if next_date:
            update_leds(led_strip, next_bins)
        else:
            update_leds(led_strip, []) # Pass empty list to trigger error color

        # --- Sleep until next check (e.g., 3 AM next day) ---
        # Get current time again after processing
        current_time_secs = utime.time()
        current_time_tuple = utime.localtime(current_time_secs)
        # Target time: 3:00 AM tomorrow
        target_hour = 3
        target_min = 0
        # Be careful with date rollover using tuple manipulation
        # Using mktime is more robust
        secs_per_day = 24 * 3600
        tomorrow_secs = current_time_secs + secs_per_day
        tomorrow_tuple = utime.localtime(tomorrow_secs)
        # Construct target time tuple for tomorrow 3 AM
        target_time_tuple = (tomorrow_tuple[0], tomorrow_tuple[1], tomorrow_tuple[2],
                             target_hour, target_min, 0, 0, 0) # Y, M, D, H, M, S, Wday, Yday
        try:
            target_time_secs = utime.mktime(target_time_tuple)
        except OverflowError:
             target_time_secs = current_time_secs + secs_per_day # Fallback: sleep 24h
        # Calculate sleep duration
        sleep_seconds = target_time_secs - current_time_secs
        # Adjust if target time calculation resulted in the past (e.g., ran just after 3 AM)
        if sleep_seconds < 0:
            sleep_seconds += secs_per_day
        # Set a minimum sleep time to avoid busy-waiting if something is wrong
        if sleep_seconds < 60:
             sleep_seconds = 60
        # Convert to hours/minutes for display
        sleep_hours = int(sleep_seconds // 3600)
        sleep_minutes = int((sleep_seconds % 3600) // 60)
        time.sleep(sleep_seconds)

# --- Run Main Program ---
if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        # Attempt to set LEDs to solid Red to indicate fatal error
        try:
            # Re-initialize NeoPixel in case the error was related to it
            error_strip = NeoPixel(PIN_NUM, NUM_LEDS, 0.1) # Low brightness error
            error_strip.pixels_fill(COLOR_RED)
            error_strip.pixels_show()
        except Exception as final_e:
        # Loop forever flashing red? Or just sleep.
        while True:
            time.sleep(60) # Sleep indefinitely after error
