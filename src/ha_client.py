import adafruit_requests
import json


class HomeAssistantClient:
    """Client for interacting with the Home Assistant REST API.

    This client provides high-level methods to trigger scenes, toggle lights,
    and call generic services through the Home Assistant API.

    Args:
        pool (socketpool.SocketPool): A socket pool for network communication.
        ssl_context (ssl.SSLContext): SSL context for secure HTTPS requests.
    """

    def __init__(self, pool, ssl_context):
        import os

        self._url = os.getenv("HA_URL")
        self._token = os.getenv("HA_TOKEN")
        self._scenes = os.getenv("HA_SCENES", "").split(",")
        self._requests = adafruit_requests.Session(pool, ssl_context)
        self._headers = {
            "Authorization": f"Bearer {self._token}",
            "Content-Type": "application/json",
        }

    def fetch_scenes(self):
        """Retrieves the list of scenes configured in the settings.

        Returns:
            list[str]: A list of scene entity IDs (e.g., ['scene.daytime', 'scene.night']).
        """
        return [s.strip() for s in self._scenes if s.strip()]

    def activate_scene(self, scene_id):
        """Activates a specific Home Assistant scene.

        Args:
            scene_id (str): The entity ID of the scene to activate (e.g., 'scene.nightlights').

        Returns:
            bool: True if the scene was activated successfully, False otherwise.
        """
        if not self._url or not self._token:
            return False

        url = f"{self._url}/api/services/scene/turn_on"
        data = {"entity_id": scene_id}
        try:
            response = self._requests.post(
                url, headers=self._headers, data=json.dumps(data)
            )
            if response.status_code == 200:
                print(f"Scene {scene_id} activated successfully.")
                return True
            else:
                print(f"Failed to activate scene. Status code: {response.status_code}")
                return False
        except Exception as e:
            print(f"Error activating scene: {e}")
            return False

    def call_service(self, domain, service, service_data):
        """Calls a generic Home Assistant service.

        Args:
            domain (str): The integration domain (e.g., 'light', 'switch').
            service (str): The service name (e.g., 'turn_on', 'toggle').
            service_data (dict): The payload for the service call.

        Returns:
            bool: True if the service call was successful, False otherwise.
        """
        if not self._url or not self._token:
            return False

        url = f"{self._url}/api/services/{domain}/{service}"
        try:
            response = self._requests.post(
                url, headers=self._headers, data=json.dumps(service_data)
            )
            if response.status_code == 200:
                print(f"Service {domain}.{service} called successfully.")
                return True
            else:
                print(f"Failed to call service. Status code: {response.status_code}")
                return False
        except Exception as e:
            print(f"Error calling service: {e}")
            return False

    def light_turn_on(self, entity_id, brightness=None, effect=None):
        """Turns on a light entity with optional parameters.

        Args:
            entity_id (str): The entity ID of the light.
            brightness (int, optional): Brightness level (0-255).
            effect (str, optional): The name of the effect to apply (e.g., 'Pulse', 'Ocean').

        Returns:
            bool: True if the command was successful.
        """
        data = {"entity_id": entity_id}
        if brightness is not None:
            data["brightness"] = brightness
        if effect is not None:
            data["effect"] = effect
        return self.call_service("light", "turn_on", data)

    def light_turn_off(self, entity_id):
        """Turns off a light entity.

        Args:
            entity_id (str): The entity ID of the light.

        Returns:
            bool: True if the command was successful.
        """
        data = {"entity_id": entity_id}
        return self.call_service("light", "turn_off", data)

    def ping(self, timeout=10):
        """Checks whether the Home Assistant API is reachable.

        Args:
            timeout (float): Request timeout in seconds.

        Returns:
            bool: True if the API responded with HTTP 200.
        """
        if not self._url or not self._token:
            return False

        url = f"{self._url}/api/"
        try:
            response = self._requests.get(url, headers=self._headers, timeout=timeout)
            if response.status_code == 200:
                return True
            print(f"HA ping failed. Status code: {response.status_code}")
            return False
        except Exception as e:
            print(f"HA ping error: {e}")
            return False

    def fetch_light_effects(self, entity_id):
        """Retrieves the effect_list from a light entity state.

        Args:
            entity_id (str): The entity ID of the light.

        Returns:
            list[str]: Effect names from HA, or empty list on error.
        """
        if not self._url or not self._token or not entity_id:
            return []

        url = f"{self._url}/api/states/{entity_id}"
        try:
            response = self._requests.get(url, headers=self._headers)
            if response.status_code != 200:
                print(
                    f"Failed to fetch light state. Status code: {response.status_code}"
                )
                return []
            state = response.json()
            effects = state.get("attributes", {}).get("effect_list", [])
            if effects:
                print(f"Fetched {len(effects)} effects from {entity_id}")
            return list(effects)
        except Exception as e:
            print(f"Error fetching light effects: {e}")
            return []
