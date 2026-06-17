"""Color definitions and utility functions for NeoPixel control."""

# Standard RGB color definitions
rgb_colors = {
    "white": (255, 255, 255),
    "green": (0, 255, 0),
    "red": (255, 0, 0),
    "blue": (0, 0, 255),
    "purple": (128, 0, 128),
    "cyan": (0, 255, 255),
    "yellow": (255, 255, 0),
    "orange": (255, 165, 0),
    "pink": (255, 192, 203),
    "gold": (255, 215, 0),
    "black": (0, 0, 0),
}


def get_color_from_name(name):
    """Parses a color name string and applies intensity scaling.

    Supports prefixes:
    - bright_: 100% intensity
    - soft_: 40% intensity
    - dim_: 10% intensity

    Args:
        name (str): Color name (e.g., 'dim_blue', 'bright_red').

    Returns:
        tuple[int, int, int]: Scaled RGB color tuple.
    """
    name = name.lower().strip()
    scale = 1.0

    if name.startswith("bright_"):
        scale = 1.0
        name = name.replace("bright_", "")
    elif name.startswith("soft_"):
        scale = 0.4
        name = name.replace("soft_", "")
    elif name.startswith("dim_"):
        scale = 0.1
        name = name.replace("dim_", "")

    base = rgb_colors.get(name, rgb_colors["white"])
    return tuple(int(c * scale) for c in base)


# HA light brightness presets (0-255 scale)
BRIGHTNESS_PRESETS = {
    "off": 0,
    "low": 64,
    "mid": 128,
    "high": 191,
    "max": 255,
}


def white_at_brightness(brightness):
    """Returns a white RGB tuple scaled to an HA brightness value (0-255).

    Args:
        brightness (int): HA brightness level (0-255).

    Returns:
        tuple[int, int, int]: Scaled white RGB color tuple.
    """
    scale = max(0, min(255, brightness)) / 255
    return tuple(int(255 * scale) for _ in range(3))


def brightness_from_label(label):
    """Maps a brightness preset label to an HA brightness value (0-255).

    Args:
        label (str): Preset name (e.g. 'off', 'low', 'mid', 'high', 'max').

    Returns:
        int: Brightness value for light.turn_on.
    """
    return BRIGHTNESS_PRESETS.get(label.lower().strip(), 255)
