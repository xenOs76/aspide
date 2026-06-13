import time


class InactivityTimer:
    """Manages the inactivity timer for the NeoPixel display.

    Args:
        display (DisplayManager): The display manager instance to control LEDs.
        timeout_seconds (int): Duration of inactivity before turning off LEDs.
    """

    def __init__(self, display, timeout_seconds=30):
        self.display = display
        self.timeout_seconds = timeout_seconds
        self.last_activity_time = time.monotonic()
        self.strip_is_on = True

    def reset(self):
        """Resets the inactivity timer and wakes up the display if it was off."""
        self.last_activity_time = time.monotonic()
        if not self.strip_is_on:
            print("Waking up NeoPixels...")
            self.strip_is_on = True
            self.display.update_strip_color()

    def check(self):
        """Checks if the timeout has been reached and turns off the display if necessary."""
        if self.strip_is_on and (
            time.monotonic() - self.last_activity_time > self.timeout_seconds
        ):
            print("NeoPixel timeout reached. Turning off LEDs...")
            self.display.strip.fill((0, 0, 0))  # Turn off LEDs
            self.strip_is_on = False
