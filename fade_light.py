import argparse
import asyncio
import logging
import json
from cryptography.fernet import Fernet, InvalidToken
from meross_iot.controller.mixins.light import LightMixin
from meross_iot.http_api import MerossHttpClient
from meross_iot.manager import MerossManager

# Setup basic logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

async def fade_lights(email: str, password: str, light_names: list, bpm: int, color: str = None, verbose: bool = False):
    if verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    COLORS = {
        "red": (255, 0, 0),
        "green": (0, 255, 0),
        "blue": (0, 0, 255),
        "yellow": (255, 255, 0),
        "cyan": (0, 255, 255),
        "magenta": (255, 0, 255),
        "white": (255, 255, 255),
    }

    # Setup Meross HTTP API client and manager
    http_client = await MerossHttpClient.async_from_user_password(email=email, password=password, api_base_url="https://iot.meross.com")
    manager = MerossManager(http_client=http_client)

    # Discover devices
    try:
        await manager.async_init()
        await manager.async_device_discovery()
        logging.info("MerossManager initialized and devices discovered.")
    except Exception as e:
        logging.error(f"Failed to initialize MerossManager: {e}")
        await http_client.async_logout()
        return

    all_devices = manager.find_devices()
    controllable_lights = [dev for dev in all_devices if isinstance(dev, LightMixin)]

    target_lights = []
    if light_names:
        for light_name in light_names:
            light = next((l for l in controllable_lights if l.name.lower() == light_name.lower()), None)
            if light:
                target_lights.append(light)
            else:
                logging.warning(f"Light '{light_name}' not found.")
    else:
        target_lights.extend(controllable_lights)

    if not target_lights:
        logging.error("No target lights found.")
        await http_client.async_logout()
        return

    rgb = COLORS.get(color.lower(), COLORS["white"]) if color else COLORS["white"]

    logging.info(f"Fading lights: {[light.name for light in target_lights]} at {bpm} BPM. Press Ctrl+C to stop.")

    beat_interval = 60.0 / bpm
    fade_steps = 10
    step_interval = beat_interval / (2 * fade_steps)  # Fade in and out in one beat

    # Update the state of all target lights
    tasks = [light.async_update() for light in target_lights]
    await asyncio.gather(*tasks)

    try:
        # First, turn the lights on
        tasks = [light.async_turn_on() for light in target_lights]
        await asyncio.gather(*tasks)

        while True:
            # Fade in
            for i in range(fade_steps + 1):
                luminance = i * (100 // fade_steps)
                tasks = [light.async_set_light_color(rgb=rgb, luminance=luminance) for light in target_lights]
                await asyncio.gather(*tasks)
                await asyncio.sleep(step_interval)

            # Fade out
            for i in range(fade_steps, -1, -1):
                luminance = i * (100 // fade_steps)
                tasks = [light.async_set_light_color(rgb=rgb, luminance=luminance) for light in target_lights]
                await asyncio.gather(*tasks)
                await asyncio.sleep(step_interval)

    except asyncio.CancelledError:
        logging.info("Light fading stopped.")
    finally:
        logging.info("Turning off all lights.")
        tasks = [light.async_turn_off() for light in target_lights]
        await asyncio.gather(*tasks)
        await http_client.async_logout()

def main():
    parser = argparse.ArgumentParser(description="Fade Meross smart lights to a beat.")
    parser.add_argument("--light-names", nargs='+', required=True, help="The name(s) of the light(s) to fade.")
    parser.add_argument("--bpm", type=int, default=60, help="The beats per minute to fade the lights to (default: 60).")
    parser.add_argument("--color", help="The color to fade the lights in.")
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable verbose (DEBUG) logging.")
    args = parser.parse_args()

    KEY_FILE = "secret.key"
    CONFIG_FILE = "meross_config.json"

    def load_key():
        """Load the encryption key from the key file."""
        try:
            with open(KEY_FILE, "rb") as key_file:
                return key_file.read()
        except FileNotFoundError:
            return None

    key = load_key()
    if not key:
        print(f"Error: Encryption key '{KEY_FILE}' not found. Please run the GUI app once to generate it.", file=sys.stderr)
        sys.exit(1)

    try:
        with open(CONFIG_FILE, 'r') as f:
            config = json.load(f)
        email = config.get('email')
        encrypted_password = config.get('password')
        if not email or not encrypted_password:
            print(f"Error: Could not find 'email' or 'password' in {CONFIG_FILE}.", file=sys.stderr)
            sys.exit(1)
        
        f = Fernet(key)
        password = f.decrypt(encrypted_password.encode()).decode()

    except FileNotFoundError:
        print(f"Error: Configuration file '{CONFIG_FILE}' not found.", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError:
        print(f"Error: Could not decode '{CONFIG_FILE}'. Please ensure it is valid JSON.", file=sys.stderr)
        sys.exit(1)
    except InvalidToken:
        print("Error: Failed to decrypt password. The encryption key may have changed.", file=sys.stderr)
        sys.exit(1)

    try:
        asyncio.run(
            fade_lights(
                email=email,
                password=password,
                light_names=args.light_names,
                bpm=args.bpm,
                color=args.color,
                verbose=args.verbose
            )
        )
    except KeyboardInterrupt:
        print("\nScript interrupted by user.")

if __name__ == "__main__":
    main()
