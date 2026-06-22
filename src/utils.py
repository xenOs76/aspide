import os
import time
import wifi
import socketpool
import ssl
import microcontroller
from colors import brightness_from_label, get_color_from_name, white_at_brightness
from ha_client import HomeAssistantClient

NVM_MAGIC_LEGACY = 0x42
NVM_MAGIC = 0x43
DEFAULT_LIGHT_EFFECTS = ["Warm White", "Daylight", "Sunset", "Focus"]
DEFAULT_LIGHT_EFFECT_COLORS = [
    "bright_yellow",
    "bright_white",
    "dim_orange",
    "dim_green",
]
DEFAULT_BRIGHTNESS_PRESETS = ["off", "low", "mid", "high", "max"]
DEFAULT_HA_PHONE_HOME_INTERVAL = 300  # seconds (5 min)


class ButtonPush:
    """Detects and categorizes button push events.

    This class monitors timing between press and release events to differentiate
    between single, double, and long pushes. It uses monotonic time (nanoseconds)
    for high-precision timing.

    Args:
        push_duration (int): Threshold in nanoseconds for a 'long' push.
        push_interval (int): Max time in nanoseconds between clicks for a 'double' push.
    """

    def __init__(self, push_duration=260_000_000, push_interval=300_000_000):
        self.__button_pressed_time = 0
        self.__button_released_time = 0
        self.__last_push_time = 0
        self.__push_duration = push_duration
        self.__push_interval = push_interval
        self.__single_push = False
        self.__double_push = False
        self.__long_push = False

    def add_pressed_time(self, time_ns):
        """Records the timestamp when the button is initially pressed.

        Args:
            time_ns (int): Current time in nanoseconds.
        """
        self.__button_pressed_time = time_ns

    def add_released_time(self, time_ns):
        """Records the timestamp when the button is released and triggers push logic.

        Args:
            time_ns (int): Current time in nanoseconds.
        """
        self.__button_released_time = time_ns
        self.__add_push()

    def reset_push(self):
        """Clears all pending push state flags."""
        self.__last_push_time = 0
        self.__single_push = False
        self.__double_push = False
        self.__long_push = False

    def status(self):
        """Provides a debug string of the current push states.

        Returns:
            str: Formatting containing status of single, double, and long push flags.
        """
        return f"single: {self.__single_push}, double: {self.__double_push}, long: {self.__long_push}"

    def __add_push(self):
        """Internal logic to categorize a push based on duration and sequence."""
        time_push_lasted = self.__button_released_time - self.__button_pressed_time

        if time_push_lasted < self.__push_duration:
            now = time.monotonic_ns()
            # detect double push
            if self.__single_push is True:
                self.__single_push = False
                self.__double_push = True
                self.__long_push = False
                self.__last_push_time = now
            # detect single push
            elif self.__single_push is False and self.__double_push is False:
                self.__single_push = True
                self.__double_push = False
                self.__long_push = False
                self.__last_push_time = now
        else:
            self.__single_push = False
            self.__double_push = False
            self.__long_push = True

        self.__button_pressed_time = 0
        self.__button_released_time = 0

    def __is_whithin_push(self):
        """Checks if the current time is still within the double-click interval."""
        now = time.monotonic_ns()
        if now - self.__last_push_time < self.__push_interval:
            return True
        return False

    def push_single(self):
        """Determines if a valid single push has been completed.

        Returns:
            bool: True if a single push occurred and the double-click window has closed.
        """
        if self.__single_push and not self.__is_whithin_push():
            self.reset_push()
            return True
        return False

    def push_double(self):
        """Determines if a double push occurred.

        Returns:
            bool: True if two clicks occurred within the allowed interval.
        """
        if self.__double_push and not self.__is_whithin_push():
            self.reset_push()
            return True
        return False

    def push_long(self):
        """Determines if a long push occurred.

        Returns:
            bool: True if the button was held longer than the push_duration threshold.
        """
        if self.__long_push and not self.__is_whithin_push():
            self.reset_push()
            return True
        return False


class RotaryDial:
    """Orchestrator for the Rotary Knob device.

    Manages WiFi connectivity, Home Assistant client initialization,
    mode switching (HA Scenes, HA Light effects, HA Brightness), and state
    tracking for selected scenes and lights. State is persisted in NVM.
    """

    def __init__(self):
        self.__debug = True
        self.online = False
        self.__modes = ["home_assistant", "ha_light", "ha_brightness"]
        self.__mode_id = 0
        self.__wifi_ssid = os.getenv("CIRCUITPY_WIFI_SSID")
        self.__wifi_password = os.getenv("CIRCUITPY_WIFI_PASSWORD")

        self.__ha_light_entity_id = os.getenv("HA_LIGHT_ENTITY_ID")
        if not self.__ha_light_entity_id:
            legacy_id = os.getenv("HA_WIZ_LIGHT_ENTITY_ID")
            if legacy_id:
                print(
                    "WARNING: HA_WIZ_LIGHT_ENTITY_ID is deprecated; use HA_LIGHT_ENTITY_ID"
                )
                self.__ha_light_entity_id = legacy_id
        if self.__ha_light_entity_id:
            self.__ha_light_entity_id = self.__ha_light_entity_id.strip()

        self.__ha_light_effects_avail = []
        self.__ha_light_effect_name_curr = None
        self.__ha_light_effect_idx = 0
        self.__ha_light_effect_colors = self.__parse_env_list("HA_LIGHT_EFFECT_COLORS")

        brightness_str = os.getenv("HA_LIGHT_BRIGHTNESS", "off,low,mid,high,max")
        self.__ha_brightness_presets = [
            p.strip() for p in brightness_str.split(",") if p.strip()
        ]
        if not self.__ha_brightness_presets:
            self.__ha_brightness_presets = list(DEFAULT_BRIGHTNESS_PRESETS)
        self.__ha_brightness_colors = self.__parse_env_list(
            "HA_LIGHT_BRIGHTNESS_COLORS"
        )
        self.__ha_brightness_idx = 0
        self.__ha_brightness_curr = self.__ha_brightness_presets[0]

        self.__pool = socketpool.SocketPool(wifi.radio)
        self.__ha_client = None
        self.__ha_scenes_avail = []
        self.__ha_scene_curr = None
        self.__ha_scene_idx = 0

        # Load persisted state from NVM
        self.__load_state()

    def __parse_env_list(self, env_key):
        """Parses a comma-separated settings value into a stripped list."""
        value = os.getenv(env_key, "")
        if not value:
            return []
        return [item.strip() for item in value.split(",") if item.strip()]

    def __load_ha_light_effects(self):
        """Loads effect list from settings or built-in defaults."""
        configured = self.__parse_env_list("HA_LIGHT_EFFECTS")
        if configured:
            self.__ha_light_effects_avail = configured
            print(f"Loaded {len(configured)} effects from HA_LIGHT_EFFECTS")
            return

        self.__ha_light_effects_avail = list(DEFAULT_LIGHT_EFFECTS)
        print(f"Loaded {len(self.__ha_light_effects_avail)} default light effects")

    def __normalize_ha_light_effect_selection(self):
        """Ensures effect index and name are valid after loading effects."""
        if not self.__ha_light_effects_avail:
            self.__ha_light_effect_idx = 0
            self.__ha_light_effect_name_curr = None
            return

        idx = self.__ha_light_effect_idx % len(self.__ha_light_effects_avail)
        self.__ha_light_effect_idx = idx
        self.__ha_light_effect_name_curr = self.__ha_light_effects_avail[idx]

    def __normalize_ha_brightness_selection(self):
        """Ensures brightness preset index and label are valid."""
        if not self.__ha_brightness_presets:
            self.__ha_brightness_idx = 0
            self.__ha_brightness_curr = None
            return

        idx = self.__ha_brightness_idx % len(self.__ha_brightness_presets)
        self.__ha_brightness_idx = idx
        self.__ha_brightness_curr = self.__ha_brightness_presets[idx]

    def save_state(self):
        """Persists the current mode and scene indices to NVM.

        NVM Map:
        - [0]: Magic Byte (0x43)
        - [1]: Mode ID
        - [2]: HA Scene Index
        - [3]: HA Light Effect Index
        - [4]: HA Brightness Preset Index
        """
        if microcontroller.nvm is not None:
            try:
                microcontroller.nvm[0:5] = bytes(
                    [
                        NVM_MAGIC,
                        self.__mode_id,
                        self.__ha_scene_idx,
                        self.__ha_light_effect_idx,
                        self.__ha_brightness_idx,
                    ]
                )
                if self.__debug:
                    print(
                        "DEBUG: State saved to NVM "
                        f"(Mode: {self.__mode_id}, HA: {self.__ha_scene_idx}, "
                        f"Light: {self.__ha_light_effect_idx}, "
                        f"Brightness: {self.__ha_brightness_idx})"
                    )
            except Exception as e:
                print(f"Error saving state to NVM: {e}")

    def __load_state(self):
        """Loads state from NVM if a valid magic byte is found."""
        if microcontroller.nvm is None:
            return

        magic = microcontroller.nvm[0]
        if magic not in (NVM_MAGIC_LEGACY, NVM_MAGIC):
            return

        try:
            self.__mode_id = microcontroller.nvm[1] % len(self.__modes)
            self.__ha_scene_idx = microcontroller.nvm[2]
            self.__ha_light_effect_idx = microcontroller.nvm[3]
            if magic == NVM_MAGIC:
                self.__ha_brightness_idx = microcontroller.nvm[4]
            else:
                # Legacy layout: wiz index in byte 3, no brightness index
                self.__ha_brightness_idx = 0
                if self.__mode_id == 1:
                    # Old wiz mode maps to ha_light
                    pass

            self.__normalize_ha_brightness_selection()

            if self.__debug:
                print(
                    "DEBUG: State loaded from NVM "
                    f"(Mode: {self.__mode_id}, HA Index: {self.__ha_scene_idx}, "
                    f"Light Index: {self.__ha_light_effect_idx}, "
                    f"Brightness Index: {self.__ha_brightness_idx})"
                )
        except Exception as e:
            print(f"Error loading state from NVM: {e}")

    def mode_current(self):
        """Returns the identifier of the active operational mode.

        Returns:
            str: 'home_assistant', 'ha_light', or 'ha_brightness'.
        """
        return self.__modes[self.__mode_id]

    def mode_next(self):
        """Cycles to the next available operational mode."""
        self.__mode_id = (self.__mode_id + 1) % len(self.__modes)
        self.save_state()

    def wifi_status(self):
        """Logs detailed information about the current WiFi connection state."""
        print("Wifi status:")
        print(f"\tEnabled: {wifi.radio.enabled}")
        print(f"\tConnected: {wifi.radio.connected}")
        if wifi.radio.connected:
            try:
                print(f"\tSSID: {wifi.radio.ap_info.ssid}")
                print(f"\tRSSI: {wifi.radio.ap_info.rssi}")
                print(f"\tIPv4 address: {wifi.radio.ipv4_address}")
            except Exception:
                print("\tUnable to fetch network data")

    def wifi_connect(self):
        """Attempts to connect to the configured WiFi network.

        Returns:
            bool: True if connected successfully (or already connected).
        """
        success = False
        if wifi.radio.connected:
            print("WiFi already connected.")
            success = True
        else:
            print("Connecting to WiFi...")
            wifi.radio.enabled = True
            try:
                wifi.radio.connect(self.__wifi_ssid, self.__wifi_password)
                print("WiFi connection successful.")
                success = True
            except Exception as e:
                print(f"WiFi connection failed: {e}")
                success = False

        if self.__debug:
            self.wifi_status()
        return success

    def wifi_disconnect(self):
        """Disables the WiFi radio and disconnects from the AP."""
        print("Disconnecting from WiFi... ")
        wifi.radio.enabled = False
        self.wifi_status()

    def initialize_ha(self):
        """Instantiates the Home Assistant client and populates scene lists.

        Returns:
            bool: True if initialization and initial fetch succeeded.
        """
        print("Initializing HA Client...")
        try:
            context = ssl.create_default_context()
            self.__ha_client = HomeAssistantClient(self.__pool, context)
            self.__ha_scenes_avail = self.__ha_client.fetch_scenes()
            if self.__ha_scenes_avail:
                idx = self.__ha_scene_idx % len(self.__ha_scenes_avail)
                self.__ha_scene_curr = self.__ha_scenes_avail[idx]
                self.__ha_scene_idx = idx

            self.__load_ha_light_effects()
            self.__normalize_ha_light_effect_selection()
            self.__normalize_ha_brightness_selection()
            return True
        except Exception as e:
            print(f"Error initializing HA: {e}")
            return False

    def phone_home_assistant(self, max_attempts=3, retry_delay=5):
        """Verify HA connectivity; retry with WiFi reconnect on failure.

        Args:
            max_attempts (int): Total ping attempts (initial plus retries).
            retry_delay (int): Seconds to wait between attempts.

        Returns:
            bool: True if HA responded; False after all attempts failed.
        """
        if not self.__ha_client:
            print("HA phone-home skipped: client not initialized")
            return False

        for attempt in range(1, max_attempts + 1):
            print(f"HA phone-home attempt {attempt}/{max_attempts}")
            if not wifi.radio.connected:
                print("WiFi disconnected, reconnecting...")
                if not self.wifi_connect():
                    print("WiFi reconnect failed")
                elif self.__ha_client.ping():
                    print("HA phone-home successful")
                    return True
            elif self.__ha_client.ping():
                print("HA phone-home successful")
                return True

            print(f"HA phone-home attempt {attempt} failed")
            if attempt < max_attempts:
                time.sleep(retry_delay)

        print("HA phone-home failed after all attempts")
        return False

    def ha_light_power(self, state=False):
        """Directly toggles the power state of the targeted HA light entity.

        Args:
            state (bool): True to turn on, False to turn off.
        """
        if not self.__ha_light_entity_id or not self.__ha_client:
            return

        if state:
            print(f"Turning on light via HA: {self.__ha_light_entity_id}")
            self.__ha_client.light_turn_on(self.__ha_light_entity_id)
        else:
            print(f"Turning off light via HA: {self.__ha_light_entity_id}")
            self.__ha_client.light_turn_off(self.__ha_light_entity_id)

    def ha_light_apply_effect(self, effect_name=None):
        """Sends a command to HA to set the light to a specific effect.

        Args:
            effect_name (str, optional): The effect name. If None, uses current selection.
        """
        if not self.__ha_light_entity_id or not self.__ha_client:
            return
        if not self.__ha_light_effects_avail:
            print("WARNING: No effects configured for ha_light mode")
            return

        name = effect_name or self.__ha_light_effect_name_curr
        print(f"Setting light effect via HA: {name}")
        self.__ha_client.light_turn_on(self.__ha_light_entity_id, effect=name)
        self.__ha_light_effect_name_curr = name
        self.__ha_light_effect_idx = self.__ha_light_effects_avail.index(name)
        self.save_state()

    def ha_light_effect_color(self):
        """Returns the RGB color for the currently selected effect preview.

        Returns:
            tuple[int, int, int]: RGB color tuple, or white if no color configured.
        """
        if self.__ha_light_effect_colors and self.__ha_light_effect_idx < len(
            self.__ha_light_effect_colors
        ):
            return get_color_from_name(
                self.__ha_light_effect_colors[self.__ha_light_effect_idx]
            )
        return (255, 255, 255)

    def ha_light_select_next(self):
        """Increments the internal selection of the light effect (browsing mode)."""
        if not self.__ha_light_effects_avail:
            return
        self.__ha_light_effect_idx = (self.__ha_light_effect_idx + 1) % len(
            self.__ha_light_effects_avail
        )
        self.__ha_light_effect_name_curr = self.__ha_light_effects_avail[
            self.__ha_light_effect_idx
        ]
        print(f"DEBUG: HA light select next -> {self.__ha_light_effect_name_curr}")
        self.save_state()

    def ha_light_select_prev(self):
        """Decrements the internal selection of the light effect (browsing mode)."""
        if not self.__ha_light_effects_avail:
            return
        self.__ha_light_effect_idx = (self.__ha_light_effect_idx - 1) % len(
            self.__ha_light_effects_avail
        )
        self.__ha_light_effect_name_curr = self.__ha_light_effects_avail[
            self.__ha_light_effect_idx
        ]
        print(f"DEBUG: HA light select prev -> {self.__ha_light_effect_name_curr}")
        self.save_state()

    def ha_brightness_apply(self, preset=None):
        """Sets the light brightness via HA for the current or given preset.

        Args:
            preset (str, optional): Preset label. If None, uses current selection.
        """
        if not self.__ha_light_entity_id or not self.__ha_client:
            return
        if not self.__ha_brightness_presets:
            print("WARNING: No brightness presets configured")
            return

        label = preset or self.__ha_brightness_curr
        brightness = brightness_from_label(label)
        print(f"Setting light brightness via HA: {label} ({brightness})")
        self.__ha_client.light_turn_on(self.__ha_light_entity_id, brightness=brightness)
        self.__ha_brightness_curr = label
        self.__ha_brightness_idx = self.__ha_brightness_presets.index(label)
        self.save_state()

    def ha_brightness_preview_color(self):
        """Returns the RGB color for the current brightness preset preview.

        Returns:
            tuple[int, int, int]: RGB color tuple.
        """
        if self.__ha_brightness_colors and self.__ha_brightness_idx < len(
            self.__ha_brightness_colors
        ):
            return get_color_from_name(
                self.__ha_brightness_colors[self.__ha_brightness_idx]
            )

        label = self.__ha_brightness_curr or "max"
        return white_at_brightness(brightness_from_label(label))

    def ha_brightness_select_next(self):
        """Increments the internal brightness preset selection."""
        if not self.__ha_brightness_presets:
            return
        self.__ha_brightness_idx = (self.__ha_brightness_idx + 1) % len(
            self.__ha_brightness_presets
        )
        self.__ha_brightness_curr = self.__ha_brightness_presets[
            self.__ha_brightness_idx
        ]
        print(f"DEBUG: HA brightness select next -> {self.__ha_brightness_curr}")
        self.save_state()

    def ha_brightness_select_prev(self):
        """Decrements the internal brightness preset selection."""
        if not self.__ha_brightness_presets:
            return
        self.__ha_brightness_idx = (self.__ha_brightness_idx - 1) % len(
            self.__ha_brightness_presets
        )
        self.__ha_brightness_curr = self.__ha_brightness_presets[
            self.__ha_brightness_idx
        ]
        print(f"DEBUG: HA brightness select prev -> {self.__ha_brightness_curr}")
        self.save_state()

    def ha_scene_next(self):
        """Increments the internal selection of the HA scene."""
        if not self.__ha_scenes_avail:
            return
        self.__ha_scene_idx = (self.__ha_scene_idx + 1) % len(self.__ha_scenes_avail)
        self.__ha_scene_curr = self.__ha_scenes_avail[self.__ha_scene_idx]
        print(f"HA Scene selected: {self.__ha_scene_curr}")
        self.save_state()

    def ha_scene_prev(self):
        """Decrements the internal selection of the HA scene."""
        if not self.__ha_scenes_avail:
            return
        self.__ha_scene_idx = (self.__ha_scene_idx - 1) % len(self.__ha_scenes_avail)
        self.__ha_scene_curr = self.__ha_scenes_avail[self.__ha_scene_idx]
        print(f"HA Scene selected: {self.__ha_scene_curr}")
        self.save_state()

    def ha_scene_activate(self):
        """Sends an activation command to HA for the currently selected scene."""
        if self.__ha_client and self.__ha_scene_curr:
            self.__ha_client.activate_scene(self.__ha_scene_curr)
            self.save_state()

    def scene_current_index(self):
        """Calculates the list index of the currently selected scene or effect.

        Used primarily for NeoPixel color calculations.

        Returns:
            int: The list index of the active selection.
        """
        mode = self.mode_current()
        if mode == "ha_light":
            return self.__ha_light_effect_idx
        elif mode == "ha_brightness":
            return self.__ha_brightness_idx
        elif mode == "home_assistant":
            return self.__ha_scene_idx
        return 0
