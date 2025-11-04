import argparse
import asyncio
import os
import logging
import sys
import json
from cryptography.fernet import Fernet, InvalidToken
from meross_iot.controller.mixins.light import LightMixin
from meross_iot.http_api import MerossHttpClient
from meross_iot.manager import MerossManager
# Setup basic logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
async def discover_and_control_lights(email: str, password: str, action: str, light_name: str = None, serial_numbers: list = None, verbose: bool = False):
    if verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    # Setup Meross HTTP API client and manager
    http_client = await MerossHttpClient.async_from_user_password(email=email, password=password, api_base_url="https://iot.meross.com")
    manager = MerossManager(http_client=http_client)
    # Start Meross device discovery
    try:
        await manager.async_init()
        logging.info("MerossManager initialized successfully.")
    except Exception as e:
        logging.error(f"Failed to initialize MerossManager: {e}")
        await http_client.async_logout()
        return
    # Discover devices
    await manager.async_device_discovery()
    all_devices = manager.find_devices()
    if not all_devices:
        logging.warning("No Meross devices found on your account.")
        await http_client.async_logout()
        return
    
    controllable_lights = [dev for dev in all_devices if isinstance(dev, LightMixin)]
    
    if serial_numbers:
        controllable_lights = [light for light in controllable_lights if light.uuid in serial_numbers]
    if not controllable_lights:
        logging.warning("No controllable lights found with the specified serial numbers.")
        await http_client.async_logout()
        return
    print("Found the following controllable lights:")
    for i, light in enumerate(controllable_lights):
        print(f"  [{i+1}] {light.name} (UUID: {light.uuid})")
    if action == 'list':
        await http_client.async_logout()
        return
    target_light = None
    if light_name:
        target_light = next((light for light in controllable_lights if light.name.lower() == light_name.lower()), None)
        if not target_light:
            logging.error(f"Light '{light_name}' not found.")
            await http_client.async_logout()
            return
    elif len(controllable_lights) == 1:
        target_light = controllable_lights[0]
        logging.info(f"Automatically selected the only available light: {target_light.name}")
    else:
        logging.error("Multiple lights found. Please specify a light name using the --light-name argument.")
        await http_client.async_logout()
        return
    # Perform the action
    await target_light.async_update()
    if action == "on":
        if not target_light.is_on():
            logging.info(f"Turning ON {target_light.name}...")
            await target_light.async_turn_on()
            logging.info(f"{target_light.name} is now ON.")
        else:
            logging.info(f"{target_light.name} is already ON.")
    elif action == "off":
        if target_light.is_on():
            logging.info(f"Turning OFF {target_light.name}...")
            await target_light.async_turn_off()
            logging.info(f"{target_light.name} is now OFF.")
        else:
            logging.info(f"{target_light.name} is already OFF.")
    # Close the HTTP client session
    await http_client.async_logout()
def main():
    parser = argparse.ArgumentParser(description="Control Meross smart lights from the command line.")
    parser.add_argument("action", choices=["on", "off", "list"], help="The action to perform.")
    parser.add_argument("--light-name", help="The name of the light to control.")
    parser.add_argument("--serial-numbers", nargs='+', help="A list of device serial numbers to target.")
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

    # Validate arguments
    if args.action in ["on", "off"] and not args.light_name and not (args.serial_numbers and len(args.serial_numbers) == 1):
        parser.error("When action is 'on' or 'off', you must specify either --light-name or a single --serial-numbers.")
        
    asyncio.run(discover_and_control_lights(
        email=email,
        password=password,
        action=args.action,
        light_name=args.light_name,
        serial_numbers=args.serial_numbers,
        verbose=args.verbose
    ))
if __name__ == "__main__":
    main()