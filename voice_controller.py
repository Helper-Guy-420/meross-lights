import argparse
import asyncio
import logging
import speech_recognition as sr
import sys
import json

from meross_iot.controller.mixins.light import LightMixin
from meross_iot.http_api import MerossHttpClient
from meross_iot.manager import MerossManager
from cryptography.fernet import Fernet, InvalidToken

# Setup basic logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

CONFIG_FILE = "meross_config.json"
KEY_FILE = "secret.key"

def load_key():
    """Load the encryption key from the key file."""
    try:
        with open(KEY_FILE, "rb") as key_file:
            return key_file.read()
    except FileNotFoundError:
        return None

async def voice_control_lights(email: str, password: str, light_names: list, verbose: bool = False):
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
        logging.error("No target lights found. Exiting.")
        await http_client.async_logout()
        return

    # It's good practice to update and turn on lights at the start if that's the desired initial state
    try:
        tasks = [light.async_update() for light in target_lights]
        await asyncio.gather(*tasks)
        # Optionally turn them on here, or leave off until voice command
        # tasks = [light.async_turn_on() for light in target_lights]
        # await asyncio.gather(*tasks)
    except Exception as e:
        logging.error(f"Failed to prepare lights: {e}")
        await http_client.async_logout()
        return

    recognizer = sr.Recognizer()
    microphone = sr.Microphone()

    logging.info(f"Voice control active for: {[light.name for light in target_lights]}. Say 'lights on' or 'lights off'. Press Ctrl+C to stop.")

    try:
        while True:
            with microphone as source:
                logging.info("Adjusting for ambient noise... Please wait.")
                recognizer.adjust_for_ambient_noise(source) 
                logging.info("Listening for commands...")
                audio = recognizer.listen(source, phrase_time_limit=5) # Listen for a phrase, up to 5 seconds

            try:
                command = recognizer.recognize_google(audio).lower()
                logging.info(f"Recognized command: {command}")

                if "lights on" in command:
                    logging.info("Voice command: Turning ON all selected lights.")
                    tasks = [light.async_turn_on() for light in target_lights if not light.is_on()]
                    if tasks: await asyncio.gather(*tasks)
                    else: logging.info("Lights are already on.")
                elif "lights off" in command:
                    logging.info("Voice command: Turning OFF all selected lights.")
                    tasks = [light.async_turn_off() for light in target_lights if light.is_on()]
                    if tasks: await asyncio.gather(*tasks)
                    else: logging.info("Lights are already off.")
                else:
                    logging.warning(f"Unrecognized voice command: {command}. Try 'lights on' or 'lights off'.")

            except sr.UnknownValueError:
                logging.warning("Speech Recognition could not understand audio")
            except sr.RequestError as e:
                logging.error(f"Could not request results from Google Speech Recognition service; {e}")
            await asyncio.sleep(0.5) # Small delay to prevent busy-looping in speech recognition

    except asyncio.CancelledError:
        logging.info("Voice control stopped.")
    finally:
        logging.info("Logging out from Meross.")
        if http_client:
            await http_client.async_logout()

def main():
    parser = argparse.ArgumentParser(description="Control Meross smart lights using simplified voice commands.")
    parser.add_argument("--light-names", nargs='+', required=True, help="The name(s) of the light(s) to control.")
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable verbose (DEBUG) logging.")
    args = parser.parse_args()

    key = load_key()
    if not key:
        print("Error: Encryption key not found. Please run the GUI app once to generate it.", file=sys.stderr)
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
        # Check for sounddevice and numpy installations first
        try:
            import sounddevice as sd
            import numpy as np
        except ImportError:
            print("Error: 'sounddevice' and/or 'numpy' not found.", file=sys.stderr)
            print("Please install them: pip install sounddevice numpy", file=sys.stderr)
            sys.exit(1)

        asyncio.run(voice_control_lights(
            email=email,
            password=password,
            light_names=args.light_names,
            verbose=args.verbose
        ))
    except KeyboardInterrupt:
        print("\nScript interrupted by user.")
    except Exception as e:
        logging.error(f"An error occurred: {e}")

if __name__ == "__main__":
    main()
