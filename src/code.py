"""Main entry point for the Aspide firmware.

This script initializes the hardware (Rotary Encoder, NeoPixels, I2C),
manages the WiFi connection, and runs the main event loop for handling
user interactions (rotations, single/double/long pushes) to control
Home Assistant entities.
"""

import time
import microcontroller
import os

from adafruit_seesaw import digitalio, rotaryio, seesaw
import neopixel
import board

from colors import rgb_colors
from timeout import InactivityTimer
from ui import DisplayManager
from utils import ButtonPush, DEFAULT_HA_PHONE_HOME_INTERVAL, RotaryDial

# --- Hardware Initialization ---

i2c = board.STEMMA_I2C()  # Using built-in STEMMA QT connector
seesaw = seesaw.Seesaw(i2c, addr=0x36)
seesaw_product = (seesaw.get_version() >> 16) & 0xFFFF
print(f"Found product {seesaw_product}")

if seesaw_product != 4991:
    print("Warning: Unexpected seesaw product ID. Expected 4991")

# Button setup on seesaw pin 24
seesaw.pin_mode(24, seesaw.INPUT_PULLUP)
button = digitalio.DigitalIO(seesaw, 24)
button_held = False

# NeoPixel Ring setup
pixel_pin = board.A1
num_pixels = 18
strip = neopixel.NeoPixel(pixel_pin, num_pixels, brightness=0.5, auto_write=True)

# --- State Management ---

last_position = -1
position_direction = None
color = 0
color_step = 5

encoder = rotaryio.IncrementalEncoder(seesaw)
push = ButtonPush()
rotary_dial = RotaryDial()

# Custom Scene Color Parsing
ha_scene_colors_str = os.getenv("HA_SCENE_COLORS", "")
ha_scene_colors = (
    [c.strip() for c in ha_scene_colors_str.split(",")] if ha_scene_colors_str else []
)

ha_light_effect_colors_str = os.getenv("HA_LIGHT_EFFECT_COLORS", "")
ha_light_effect_colors = (
    [c.strip() for c in ha_light_effect_colors_str.split(",")]
    if ha_light_effect_colors_str
    else []
)

ha_brightness_colors_str = os.getenv("HA_LIGHT_BRIGHTNESS_COLORS", "")
ha_brightness_colors = (
    [c.strip() for c in ha_brightness_colors_str.split(",")]
    if ha_brightness_colors_str
    else []
)

# Initialize Managers
display = DisplayManager(
    strip, rotary_dial, ha_scene_colors, ha_light_effect_colors, ha_brightness_colors
)
neopixel_timeout = int(os.getenv("NEOPIXEL_TIMEOUT", 30))
timer = InactivityTimer(display, neopixel_timeout)


# --- Startup Sequence ---

strip.fill(rgb_colors["white"])
for p in range(num_pixels):
    strip[p] = rgb_colors["purple"]
    time.sleep(0.02)
strip.fill(rgb_colors["black"])

display.show_connecting_animation()
success = rotary_dial.wifi_connect()
print(f"Connection success: {success}")
if success:
    rotary_dial.initialize_ha()
    rotary_dial.ha_light_power(True)
    rotary_dial.online = True
display.show_connection_status(success)

_ha_phone_home_raw = os.getenv(
    "HA_PHONE_HOME_INTERVAL", str(DEFAULT_HA_PHONE_HOME_INTERVAL)
)
try:
    _ha_phone_home_seconds = int(_ha_phone_home_raw)
except (TypeError, ValueError):
    print(
        "Invalid HA_PHONE_HOME_INTERVAL; "
        f"using default {DEFAULT_HA_PHONE_HOME_INTERVAL}s"
    )
    _ha_phone_home_seconds = DEFAULT_HA_PHONE_HOME_INTERVAL

if _ha_phone_home_seconds <= 0:
    print(
        "HA_PHONE_HOME_INTERVAL must be > 0; "
        f"using default {DEFAULT_HA_PHONE_HOME_INTERVAL}s"
    )
    _ha_phone_home_seconds = DEFAULT_HA_PHONE_HOME_INTERVAL

HA_PHONE_HOME_INTERVAL_NS = _ha_phone_home_seconds * 1_000_000_000
last_ha_phone_home = time.monotonic_ns()

# --- Main Event Loop ---

while True:
    # 1. Handle Encoder Rotation
    position = -encoder.position
    if position > last_position:
        timer.reset()
        position_direction = "increase"
        print(f"Position: {position}")

    if position < last_position:
        timer.reset()
        position_direction = "decrease"
        print(f"Position: {position}")

    if position == last_position:
        position_direction = None

    last_position = position

    if rotary_dial.online and position_direction:
        curr_mode = rotary_dial.mode_current()
        if position_direction == "increase":
            if curr_mode == "ha_light":
                print("Browsing light effects (preview only)...")
                rotary_dial.ha_light_select_next()
            elif curr_mode == "ha_brightness":
                print("Browsing brightness presets (preview only)...")
                rotary_dial.ha_brightness_select_next()
            elif curr_mode == "home_assistant":
                print("Switching to next HA scene...")
                rotary_dial.ha_scene_next()
        else:
            if curr_mode == "ha_light":
                print("Browsing light effects (preview only)...")
                rotary_dial.ha_light_select_prev()
            elif curr_mode == "ha_brightness":
                print("Browsing brightness presets (preview only)...")
                rotary_dial.ha_brightness_select_prev()
            elif curr_mode == "home_assistant":
                print("Switching to previous HA scene...")
                rotary_dial.ha_scene_prev()
        display.update_strip_color()

    # 2. Handle Button Presses
    if not button.value and not button_held:
        timer.reset()
        button_held = True
        push.add_pressed_time(time.monotonic_ns())

    if button.value and button_held:
        button_held = False
        push.add_released_time(time.monotonic_ns())
        print(push.status())

    # Process categorization
    if push.push_single():
        print("Single push detected")
        if rotary_dial.online:
            curr_mode = rotary_dial.mode_current()
            if curr_mode == "home_assistant":
                print("Activating HA Scene...")
                rotary_dial.ha_scene_activate()
            elif curr_mode == "ha_light":
                print("Activating light effect via HA...")
                rotary_dial.ha_light_apply_effect()
            elif curr_mode == "ha_brightness":
                print("Applying brightness preset via HA...")
                rotary_dial.ha_brightness_apply()
        push.reset_push()

    if push.push_double():
        print("Double push detected - Rebooting device...")
        # Visual feedback for reboot
        strip.fill(rgb_colors["red"])
        time.sleep(0.5)
        strip.fill(rgb_colors["black"])
        time.sleep(0.2)
        # Final save before reset to ensure NVM is up to date
        rotary_dial.save_state()
        microcontroller.reset()

    if push.push_long():
        print("Long push detected")
        if rotary_dial.online:
            rotary_dial.mode_next()
            curr_mode = rotary_dial.mode_current()
            print(f"\tSwitched to mode: {curr_mode}")
            if curr_mode == "ha_light":
                rotary_dial.ha_light_apply_effect()
            elif curr_mode == "ha_brightness":
                rotary_dial.ha_brightness_apply()
            display.update_strip_color()
        push.reset_push()

    # 3. Handle NeoPixel Timeout (Auto-Dim)
    timer.check()

    # 4. Periodic HA phone-home health check
    if (
        rotary_dial.online
        and time.monotonic_ns() - last_ha_phone_home >= HA_PHONE_HOME_INTERVAL_NS
    ):
        last_ha_phone_home = time.monotonic_ns()
        if not rotary_dial.phone_home_assistant():
            strip.fill(rgb_colors["red"])
            time.sleep(0.5)
            strip.fill(rgb_colors["black"])
            time.sleep(0.2)
            rotary_dial.save_state()
            microcontroller.reset()

    time.sleep(0.01)  # Prevent CPU hogging
