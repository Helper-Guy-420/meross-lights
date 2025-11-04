import argparse
import asyncio
import os
import logging
import sys
import json
from meross_iot.controller.mixins.light import LightMixin
from meross_iot.http_api import MerossHttpClient
from meross_iot.manager import MerossManager
# Setup basic logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
async def discover_and_control_lights(email: str, password: str, action: str, light_names: list = None, color: str = None, cycle_speed: float = 1.0, serial_numbers: list = None, verbose: bool = False):
    if verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Color mapping
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

    target_lights = []
    if light_names:
        for light_name in light_names:
            light = next((light for light in controllable_lights if light.name.lower() == light_name.lower()), None)
            if light:
                target_lights.append(light)
            else:
                logging.warning(f"Light '{light_name}' not found.")
    elif len(controllable_lights) > 0:
        target_lights.extend(controllable_lights)
        logging.info("No light name specified, targeting all controllable lights.")

    if not target_lights:
        logging.error("No target lights found.")
        await http_client.async_logout()
        return

    # Perform the action on all target lights
    for target_light in target_lights:
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
        elif action == "color":
            if color:
                rgb = COLORS.get(color.lower())
                if rgb:
                    logging.info(f"Setting color of {target_light.name} to {color}...")
                    await target_light.async_set_light_color(rgb=rgb)
                    logging.info(f"{target_light.name} color is now {color}.")
                else:
                    logging.error(f"Invalid color: {color}. Supported colors are: {list(COLORS.keys())}")
            else:
                logging.error("You must specify a color with the --color argument.")
        elif action == "cycle-colors":
            logging.info(f"Starting color cycle for {target_light.name}. Press Ctrl+C to stop.")
            try:
                while True:
                    for color_name, rgb in COLORS.items():
                        logging.info(f"Setting color to {color_name}...")
                        await target_light.async_set_light_color(rgb=rgb)
                        await asyncio.sleep(cycle_speed)
            except asyncio.CancelledError:
                logging.info("Color cycle stopped.")
            finally:
                logging.info(f"Turning off {target_light.name}.")
                await target_light.async_turn_off()

    # Close the HTTP client session
    await http_client.async_logout()
def main():
    parser = argparse.ArgumentParser(description="Control Meross smart lights from the command line.")
    
    # Load configuration from JSON file
    try:
        with open('meross_config.json', 'r') as f:
            config = json.load(f)
        email = config.get('email')
        password = config.get('password')
    except FileNotFoundError:
        print("Error: 'meross_config.json' not found. Please create it with your Meross credentials.")
        sys.exit(1)
    except json.JSONDecodeError:
        print("Error: Could not decode 'meross_config.json'. Please ensure it is valid JSON.")
        sys.exit(1)

    if not email or not password:
        print("Error: 'email' and 'password' must be set in 'meross_config.json'.")
        sys.exit(1)

    parser.add_argument("action", choices=["on", "off", "list", "color", "cycle-colors"], help="The action to perform.")
    parser.add_argument("--light-name", nargs='+', help="The name(s) of the light(s) to control.")
    parser.add_argument("--color", help="The color to set the light to (e.g., red, blue, green).")
    parser.add_argument("--cycle-speed", type=float, default=1.0, help="The speed of the color cycle in seconds (default: 1.0).")
    parser.add_argument("--serial-numbers", nargs='+', help="A list of device serial numbers to target.")
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable verbose (DEBUG) logging.")
    args = parser.parse_args()
    # Validate arguments
    if args.action in ["on", "off", "color", "cycle-colors"] and not args.light_name and not args.serial_numbers:
        parser.error("When action is 'on', 'off', 'color', or 'cycle-colors', you must specify either --light-name or --serial-numbers.")
    if args.action == "color" and not args.color:
        parser.error("When action is 'color', you must specify the --color argument.")
        
    try:
        asyncio.run(discover_and_control_lights(
            email=email,
            password=password,
            action=args.action,
            light_names=args.light_name,
            color=args.color,
            cycle_speed=args.cycle_speed,
            serial_numbers=args.serial_numbers,
            verbose=args.verbose
        ))
    except KeyboardInterrupt:
        print("\nScript interrupted by user.")

if __name__ == "__main__":
    main()