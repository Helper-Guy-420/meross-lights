import argparse
import asyncio
import logging
import numpy as np
import sounddevice as sd
import json
from cryptography.fernet import Fernet, InvalidToken
from meross_iot.controller.mixins.light import LightMixin
from meross_iot.http_api import MerossHttpClient
from meross_iot.manager import MerossManager

# Setup basic logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

async def mic_to_light(email: str, password: str, light_names: list, sensitivity: float, verbose: bool = False):
    if verbose:
        logging.getLogger().setLevel(logging.DEBUG)

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

    # Update the state of all target lights
    tasks = [light.async_update() for light in target_lights]
    await asyncio.gather(*tasks)

    # Explicitly turn on the lights
    tasks = [light.async_turn_on() for light in target_lights]
    await asyncio.gather(*tasks)

    logging.info(f"Listening to microphone... Lights: {[light.name for light in target_lights]}. Press Ctrl+C to stop.")

    loop = asyncio.get_running_loop()

    async def set_lights_luminance(lights, luminance):
        tasks = [light.async_set_light_color(luminance=luminance) for light in lights]
        await asyncio.gather(*tasks)
        await asyncio.sleep(0.05) # Add a small delay to prevent overwhelming the devices

    def audio_callback(indata, frames, time, status):
        volume_norm = np.linalg.norm(indata) * 10
        luminance = min(100, int(volume_norm * sensitivity))
        print(f"Volume: {volume_norm:.2f}, Luminance: {luminance}")
        loop.call_soon_threadsafe(asyncio.create_task, set_lights_luminance(target_lights, luminance))

    try:
        with sd.InputStream(callback=audio_callback):
            await asyncio.Future()  # Run forever

    except asyncio.CancelledError:
        logging.info("Mic listening stopped.")
    finally:
        logging.info("Turning off all lights.")
        tasks = [light.async_turn_off() for light in target_lights]
        await asyncio.gather(*tasks)
        await http_client.async_logout()

def main():
    parser = argparse.ArgumentParser(description="Control Meross smart lights with your microphone.")
    parser.add_argument("--light-names", nargs='+', required=True, help="The name(s) of the light(s) to control.")
    parser.add_argument("--sensitivity", type=float, default=10.0, help="The sensitivity of the microphone (default: 10.0).")
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
            mic_to_light(
                email=email,
                password=password,
                light_names=args.light_names,
                sensitivity=args.sensitivity,
                verbose=args.verbose
            )
        )
    except KeyboardInterrupt:
        print("\nScript interrupted by user.")
    except Exception as e:
        logging.error(f"An error occurred: {e}")

if __name__ == "__main__":
    main()