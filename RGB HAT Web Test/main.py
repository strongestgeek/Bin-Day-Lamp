#!/usr/bin/python

from bottle import get,request, route, run, static_file,template
import time, threading
import socket
from rpi_ws281x import Adafruit_NeoPixel, Color

s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
s.connect(('8.8.8.8',80))
ip=s.getsockname()[0]
print("IP = ", ip)

# LED strip configuration:
LED_COUNT      = 32      # Number of LED pixels.
LED_PIN        = 18      # GPIO pin connected to the pixels (must support PWM!).
LED_FREQ_HZ    = 800000  # LED signal frequency in hertz (usually 800khz)
LED_DMA        = 10      # DMA channel to use for generating signal (try 5)
LED_BRIGHTNESS = 20      # Set to 0 for darkest and 255 for brightest
LED_INVERT     = False   # True to invert the signal (when using NPN transistor level shift)

# Create NeoPixel object with appropriate configuration.
strip = Adafruit_NeoPixel(LED_COUNT, LED_PIN, LED_FREQ_HZ, LED_DMA, LED_INVERT, LED_BRIGHTNESS)
# Intialize the library (must be called once before other functions).
strip.begin()
strip.show()

rgb = 0
light_type = 'static'    #'static':static 'breath':breathe 'flash':flashing

#Access file root directory
@get("/")
def index():
    global rgb, light_type
    rgb = 0xffffff
    light_type = 'static'
    return static_file('index.html', './')

#Static files on web pages need to be transferred
@route('/<filename>')
def server_static(filename):
    return static_file(filename, root='./')

#POST method to obtain the RGB value transmitted by Ajax
@route('/rgb', method='POST')
def rgbLight():
    red = request.POST.get('red')
    green = request.POST.get('green')
    blue = request.POST.get('blue')
    #print('red='+ red +', green='+ green +', blue='+ blue)
    red = int(red)
    green = int(green)
    blue = int(blue)
    if 0 <= red <= 255 and 0 <= green <= 255 and 0 <= blue <= 255:
        global rgb
        rgb = (red<<16) | (green<<8) | blue

#POST method to obtain the type value transmitted by Ajax
@route('/lightType', method='POST')
def lightType():
    global light_type
    light_type = request.POST.get('type')
    print("lightType="+light_type)

#Light cycle detection control
def lightLoop():
        global rgb, light_type
        flashTime = [0.3, 0.2, 0.1, 0.05, 0.05, 0.1, 0.2, 0.5, 0.2] #Flashing time interval
        flashTimeIndex = 0 #Flash interval index
        f = lambda x: (-1/10000.0)*x*x + (1/50.0)*x #Use a parabola to simulate a breathing light
        x = 0
        while True:
                if light_type == 'static':   #Static display

                        for i in range(0,strip.numPixels()):
                                strip.setPixelColor(i, rgb)
                        strip.show()
                        time.sleep(0.05)
                elif light_type == 'breath': #Flashing display
                        green = int(((rgb & 0x00ff00)>>8) * f(x))
                        red = int(((rgb & 0xff0000) >> 16) * f(x))
                        blue = int((rgb & 0x0000ff) * f(x))
                        _rgb = int((red << 16) | (green << 8) | blue)
                        for i in range(0,strip.numPixels()):
                                strip.setPixelColor(i, _rgb)
                                strip.show()
                        time.sleep(0.02)
                        x += 1
                        if x >= 200:
                                x = 0
                elif light_type == 'flash':  #Breathing light display
                        for i in range(0,strip.numPixels()):
                                strip.setPixelColor(i, rgb)
                                strip.show()
                        time.sleep(flashTime[flashTimeIndex])
                        for i in range(0,strip.numPixels()):
                                strip.setPixelColor(i, 0)
                                strip.show()
                        time.sleep(flashTime[flashTimeIndex])
                        flashTimeIndex += 1
                        if flashTimeIndex >= len(flashTime):
                                flashTimeIndex = 0


#Open a new thread to be responsible for RGB lighting display
t = threading.Thread(target = lightLoop)
t.setDaemon(True)
t.start()

#Set the server IP address and port (tip: please set it to your Raspberry Pi IP address before use)
run(host=ip, port=8000)
