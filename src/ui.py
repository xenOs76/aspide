import time
from rainbowio import colorwheel
from colors import rgb_colors, get_color_from_name


class DisplayManager:
    """Manages all NeoPixel visual feedback and animations.

    Args:
        strip (neopixel.NeoPixel): The NeoPixel strip object.
        rotary_dial (RotaryDial): The rotary dial controller instance.
        ha_scene_colors (list[str]): List of configured scene color names.
    """

    def __init__(self, strip, rotary_dial, ha_scene_colors):
        self.strip = strip
        self.rotary_dial = rotary_dial
        self.ha_scene_colors = ha_scene_colors
        self.num_pixels = len(strip)

    def update_strip_color(self):
        """Updates the NeoPixel ring colors based on the current mode and active selection."""
        if not self.rotary_dial.online:
            self.strip.fill(rgb_colors["black"])
            return

        curr_mode = self.rotary_dial.mode_current()
        scene_idx = self.rotary_dial.scene_current_index()

        # Pixels 0 & 1: Mode Indicator
        if curr_mode == "wiz":
            mode_color = colorwheel(50)  # Yellowish for Wiz
            self.strip[0] = mode_color
            self.strip[1] = mode_color
            scene_color = self.rotary_dial.wiz_light_scene_color()
            for i in range(2, self.num_pixels):
                self.strip[i] = scene_color

        elif curr_mode == "home_assistant":
            mode_color = rgb_colors["blue"]  # Blue for HA
            self.strip[0] = mode_color
            self.strip[1] = mode_color

            if (
                scene_idx < len(self.ha_scene_colors)
                and self.ha_scene_colors[scene_idx]
            ):
                scene_color = get_color_from_name(self.ha_scene_colors[scene_idx])
            else:
                scene_color = colorwheel((160 + scene_idx * 20) % 255)

            for i in range(2, self.num_pixels):
                self.strip[i] = scene_color

    def show_connecting_animation(self):
        """Displays a cyclic 'cyan' animation on the ring during network initialization."""
        for _ in range(3):
            for p in range(self.num_pixels):
                self.strip[p] = rgb_colors["cyan"]
                time.sleep(0.01)
                self.strip[p] = rgb_colors["black"]

    def show_connection_status(self, success):
        """Displays a momentary success (green) or failure (red) color on the ring.

        Args:
            success (bool): Whether the connection was established.
        """
        if success:
            for _ in range(2):
                self.strip.fill(rgb_colors["green"])
                time.sleep(0.1)
                self.strip.fill(rgb_colors["black"])
                time.sleep(0.1)
            self.update_strip_color()
        else:
            self.strip.fill(rgb_colors["red"])
            time.sleep(1.0)
