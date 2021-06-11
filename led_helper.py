from gpiozero import LED
from apa102_pi.driver.apa102 import APA102  # for LEDs
import numpy as np
from time import sleep
import threading


class LedHelper:
    """
    Class to control the LEDs on the seeedstudio sound/LED card for the blueberry assistant.
    Functions are simply different ways of how the LEDs blink to give feedback for the user.
    """
    power = LED(5)
    power.on()
    leds = APA102(12)
    leds.clear_strip()
    led_lock = threading.Lock()
    color_wheel_values = {0: (255,0,0), 1: (255,127,0), 2: (255,255,0), 3:(127, 255, 0), 4: (0,255,0), 5: (0,255,127),
                          6: (0,255,255), 7: (0,127,255), 8: (0,0,255), 9: (127,0,255), 10: (255,0, 255),
                          11: (255,0,127)}

    def __init__(self):
        self.standby_leds = [3, 4, 5, 6]
        self.thinking_max_values = (0, 0, 255 - 16)
        self.listening_led_values = (12, 0, 192)
        self.standby_led_values = (8, 8, 8)
        self.thermo_led_value = 32

    def set_night_lights(self):
        """
        dimms the lEDs and filters out blue for better sleep
        :return:
        """
        self.thinking_max_values = (32, 8, 0)
        self.listening_led_values = (32, 4, 0)
        self.standby_led_values = (8, 8, 0)
        self.thermo_led_value = 4

    def set_listening_leds(self, rgb=None):
        """
        LEDs light up
        :param rgb: rgb int tuple
        :return:
        """
        if rgb is None:
            rgb = self.listening_led_values
        self.leds.clear_strip()
        for i in range(12):
            self.leds.set_pixel(i, *rgb)
        self.leds.show()

    def set_shutdown_leds(self, rgb=(2, 1, 0)):
        self.leds.clear_strip()
        for i in range(12):
            self.leds.set_pixel(i, *rgb)
        self.leds.show()

    def set_thinking_leds(self, stop, interval=1 / 20, f=0.75, max_values=None):
        """
        Leds blink sinusoidally to indicate the blueberry assistant is thinking
        :param stop: (bool) to end the thread
        :param interval: pause in between steps
        :param f: frequency of the sine
        :param max_values: amplitude of the sine
        :return:
        """
        if max_values is None:
            max_values = self.thinking_max_values
        ts = np.arange(0, 1 / f, interval)
        sin = np.sin(f * 2 * np.pi * ts)
        while True:
            for s in sin:
                r = 0.5 * max_values[0] * s + 0.5 * max_values[0]
                g = 0.5 * max_values[1] * s + 0.5 * max_values[1]
                b = 0.5 * max_values[2] * s + 0.5 * max_values[2]
                for i in range(12):  # standby_leds:
                    self.leds.set_pixel(i, int(r), int(g), int(b), bright_percent=100)
                self.leds.show()
                sleep(interval)
            if stop():
                break

    def set_standby_leds(self, standby_led_values=None):
        """
        four leds indicating blueberry is in standby
        :param standby_led_values:
        :return:
        """
        if standby_led_values is None:
            standby_led_values = self.standby_led_values
        for i in self.standby_leds:
                self.leds.set_pixel(i, *standby_led_values, bright_percent=25)
                self.leds.show()

    def run_color_wheel(self, stop, rgb=None):
        """
        leds start going on clockwise to symbolize a loading
        :param stop: (bool) to end the thread
        :param rgb: color of the LEDS (rgb) tuple
        :return:
        """
        if rgb is None:
            rgb = self.color_wheel_values
        else:
            rgb = [rgb]*12
        self.leds.clear_strip()
        while True:
            for i in np.arange(12):
                if stop():
                    break
                for j in np.arange(i+1):
                    self.leds.set_pixel(j, *rgb[j], bright_percent=10)
                self.leds.show()
                sleep(1)
            for i in np.arange(12):
                if stop():
                    break
                for j in np.arange(i+1):
                    self.leds.set_pixel(j, 0,0,0, bright_percent=10)
                self.leds.show()
                sleep(1)
            if stop():
                break
        self.leds.clear_strip()
