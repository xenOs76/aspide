import os
import time
import wifi
import socketpool
import ssl
import microcontroller
from ha_client import HomeAssistantClient


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
    mode switching (HA Scenes vs Wiz Effects), and state tracking
    for selected scenes and lights. State is persisted in NVM.
    """

    def __init__(self):
        self.__debug = True
        self.online = False
        self.__modes = ["home_assistant", "wiz"]
        self.__mode_id = 0
        self.__wifi_ssid = os.getenv("CIRCUITPY_WIFI_SSID")
        self.__wifi_password = os.getenv("CIRCUITPY_WIFI_PASSWORD")

        self.__wiz_light_entity_id = os.getenv("HA_WIZ_LIGHT_ENTITY_ID")
        if self.__wiz_light_entity_id:
            self.__wiz_light_entity_id = self.__wiz_light_entity_id.strip()

        # Wiz Effects available through HA with approximate colors
        self.__wiz_light_scene_colors = {
            "Ocean": (0, 0, 255),
            "Romance": (255, 0, 127),
            "Sunset": (255, 69, 0),
            "Party": (128, 0, 128),
            "Candlelight": (255, 147, 41),
            "Golden white": (255, 215, 0),
            "Pulse": (255, 255, 255),
            "Steampunk": (205, 127, 50),
            "Diwali": (255, 255, 0),
            "Fall": (139, 69, 19),
            "Cyberpunk": (0, 255, 255),
            "Christmas": (255, 0, 0),
            "Halloween": (255, 165, 0),
            "TV": (200, 200, 255),
            "Yoga": (0, 255, 0),
        }
        self.__wiz_light_scenes_avail = list(self.__wiz_light_scene_colors.keys())
        self.__wiz_light_scene_name_curr = self.__wiz_light_scenes_avail[0]
        self.__wiz_light_scene_idx = 0

        self.__pool = socketpool.SocketPool(wifi.radio)
        self.__ha_client = None
        self.__ha_scenes_avail = []
        self.__ha_scene_curr = None
        self.__ha_scene_idx = 0

        # Load persisted state from NVM
        self.__load_state()

    def save_state(self):
        """Persists the current mode and scene indices to NVM.

        NVM Map:
        - [0]: Magic Byte (0x42)
        - [1]: Mode ID
        - [2]: HA Scene Index
        - [3]: Wiz Scene Index
        """
        if microcontroller.nvm is not None:
            try:
                # Use slice assignment for more 'atomic' write operation
                microcontroller.nvm[0:4] = bytes(
                    [
                        0x42,
                        self.__mode_id,
                        self.__ha_scene_idx,
                        self.__wiz_light_scene_idx,
                    ]
                )
                if self.__debug:
                    print(
                        f"DEBUG: State saved to NVM (Mode: {self.__mode_id}, HA: {self.__ha_scene_idx}, Wiz: {self.__wiz_light_scene_idx})"
                    )
            except Exception as e:
                print(f"Error saving state to NVM: {e}")

    def __load_state(self):
        """Loads state from NVM if a valid magic byte is found."""
        if microcontroller.nvm is not None and microcontroller.nvm[0] == 0x42:
            try:
                self.__mode_id = microcontroller.nvm[1] % len(self.__modes)
                self.__ha_scene_idx = microcontroller.nvm[2]
                self.__wiz_light_scene_idx = microcontroller.nvm[3] % len(
                    self.__wiz_light_scenes_avail
                )

                # Restore the actual names from the indices
                self.__wiz_light_scene_name_curr = self.__wiz_light_scenes_avail[
                    self.__wiz_light_scene_idx
                ]

                if self.__debug:
                    print(
                        f"DEBUG: State loaded from NVM (Mode: {self.__mode_id}, HA Index: {self.__ha_scene_idx}, Wiz Index: {self.__wiz_light_scene_idx})"
                    )
            except Exception as e:
                print(f"Error loading state from NVM: {e}")

    def mode_current(self):
        """Returns the identifier of the active operational mode.

        Returns:
            str: Either 'home_assistant' or 'wiz'.
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
                self.__ha_scene_idx = idx  # Normalize
            return True
        except Exception as e:
            print(f"Error initializing HA: {e}")
            return False

    def wiz_light_state(self, state=False):
        """Directly toggles the power state of the targeted Wiz light entity.

        Args:
            state (bool): True to turn on, False to turn off.
        """
        if not self.__wiz_light_entity_id or not self.__ha_client:
            return

        if state:
            print(f"Turning on Wiz light via HA: {self.__wiz_light_entity_id}")
            self.__ha_client.light_turn_on(self.__wiz_light_entity_id)
        else:
            print(f"Turning off Wiz light via HA: {self.__wiz_light_entity_id}")
            self.__ha_client.light_turn_off(self.__wiz_light_entity_id)

    def wiz_light_scene_name(self, scene_name=None):
        """Sends a command to HA to set the Wiz light to a specific effect.

        Args:
            scene_name (str, optional): The effect name. If None, uses the current browsing selection.
        """
        if not self.__wiz_light_entity_id or not self.__ha_client:
            return

        name = scene_name or self.__wiz_light_scene_name_curr
        print(f"Setting Wiz light effect via HA: {name}")
        self.__ha_client.light_turn_on(self.__wiz_light_entity_id, effect=name)
        self.__wiz_light_scene_name_curr = name
        self.__wiz_light_scene_idx = self.__wiz_light_scenes_avail.index(name)
        self.save_state()

    def wiz_light_scene_color(self):
        """Returns the RGB color mapping for the currently selected Wiz effect.

        Returns:
            tuple[int, int, int]: RGB color tuple.
        """
        return self.__wiz_light_scene_colors.get(
            self.__wiz_light_scene_name_curr, (255, 255, 255)
        )

    def wiz_light_select_next(self):
        """Increments the internal selection of the Wiz effect (Browsing mode)."""
        self.__wiz_light_scene_idx = (self.__wiz_light_scene_idx + 1) % len(
            self.__wiz_light_scenes_avail
        )
        self.__wiz_light_scene_name_curr = self.__wiz_light_scenes_avail[
            self.__wiz_light_scene_idx
        ]
        print(f"DEBUG: Wiz internal select next -> {self.__wiz_light_scene_name_curr}")
        self.save_state()

    def wiz_light_select_prev(self):
        """Decrements the internal selection of the Wiz effect (Browsing mode)."""
        self.__wiz_light_scene_idx = (self.__wiz_light_scene_idx - 1) % len(
            self.__wiz_light_scenes_avail
        )
        self.__wiz_light_scene_name_curr = self.__wiz_light_scenes_avail[
            self.__wiz_light_scene_idx
        ]
        print(f"DEBUG: Wiz internal select prev -> {self.__wiz_light_scene_name_curr}")
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
        if mode == "wiz":
            return self.__wiz_light_scene_idx
        elif mode == "home_assistant":
            return self.__ha_scene_idx
        return 0
