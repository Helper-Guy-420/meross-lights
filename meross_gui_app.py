import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import asyncio
import threading
import logging
import json
import os
import requests
import subprocess
import sys

from meross_iot.controller.mixins.light import LightMixin
from meross_iot.http_api import MerossHttpClient
from meross_iot.manager import MerossManager
from cryptography.fernet import Fernet, InvalidToken

# Custom handler to redirect logs to the GUI text widget
class TextWidgetHandler(logging.Handler):
    def __init__(self, text_widget):
        super().__init__()
        self.text_widget = text_widget
        self.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))

    def emit(self, record):
        msg = self.format(record)
        # Use root.after to safely update the Text widget from a different thread
        self.text_widget.after(0, self._insert_text, msg)

    def _insert_text(self, msg):
        self.text_widget.config(state='normal')
        self.text_widget.insert(tk.END, msg + '\n')
        self.text_widget.see(tk.END) # Auto-scroll to the end
        self.text_widget.config(state='disabled')

CONFIG_FILE = "meross_config.json"
KEY_FILE = "secret.key"

def load_key():
    """Load the encryption key from the key file."""
    try:
        with open(KEY_FILE, "rb") as key_file:
            return key_file.read()
    except FileNotFoundError:
        # Handle case where key doesn't exist
        return None

class MerossApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Meross Light Controller (Simplified)")
        self.root.geometry("500x600")

        self.meross_email = tk.StringVar()
        self.meross_password = tk.StringVar()
        self.remember_me = tk.BooleanVar(value=True)

        self.http_client = None
        self.manager = None
        self.controllable_lights = []

        self.asyncio_loop = None
        self.asyncio_thread = None

        self._create_widgets()
        self._setup_logging()

        # Generate a key if one doesn't exist
        if not os.path.exists(KEY_FILE):
            self._generate_key()

        self._load_credentials() # Load credentials on startup

        # Bind an event to gracefully stop the asyncio loop when the window is closed
        self.root.protocol("WM_DELETE_WINDOW", self._on_closing)

    def _generate_key(self):
        """Generate a new encryption key and save it to the key file."""
        try:
            key = Fernet.generate_key()
            with open(KEY_FILE, "wb") as key_file:
                key_file.write(key)
            logging.info("New encryption key generated.")
        except Exception as e:
            logging.error(f"Could not generate or save encryption key: {e}")
            messagebox.showerror("Error", "Could not generate or save encryption key. Credentials will not be saved.")

    def _on_closing(self):
        if self.asyncio_loop and self.asyncio_loop.is_running():
            self.asyncio_loop.call_soon_threadsafe(self.asyncio_loop.stop)
        self.root.destroy()

    def _create_widgets(self):
        # Credentials Frame
        cred_frame = ttk.LabelFrame(self.root, text="Meross Credentials", padding="10")
        cred_frame.pack(pady=10, padx=10, fill="x")

        ttk.Label(cred_frame, text="Email:").grid(row=0, column=0, padx=5, pady=5, sticky="w")
        ttk.Entry(cred_frame, textvariable=self.meross_email, width=40).grid(row=0, column=1, padx=5, pady=5, sticky="ew")

        ttk.Label(cred_frame, text="Password:").grid(row=1, column=0, padx=5, pady=5, sticky="w")
        ttk.Entry(cred_frame, textvariable=self.meross_password, show='*', width=40).grid(row=1, column=1, padx=5, pady=5, sticky="ew")

        ttk.Checkbutton(cred_frame, text="Remember Me", variable=self.remember_me).grid(row=2, column=0, padx=5, pady=5, sticky="w")
        self.login_button = ttk.Button(cred_frame, text="Login & Discover Devices", command=self.start_asyncio_and_discover)
        self.login_button.grid(row=2, column=1, pady=10)

        # Lights Frame
        lights_frame = ttk.LabelFrame(self.root, text="Discovered Lights", padding="10")
        lights_frame.pack(pady=10, padx=10, fill="both", expand=True)

        self.lights_listbox = tk.Listbox(lights_frame, selectmode=tk.SINGLE, height=8) # Single select for simplicity
        self.lights_listbox.pack(fill="both", expand=True)

        # Controls Frame
        controls_frame = ttk.LabelFrame(self.root, text="Controls", padding="10")
        controls_frame.pack(pady=10, padx=10, fill="x")

        self.on_button = ttk.Button(controls_frame, text="On", command=lambda: self.start_asyncio_and_run(self.turn_on_selected_light))
        self.on_button.pack(side="left", padx=5)

        self.off_button = ttk.Button(controls_frame, text="Off", command=lambda: self.start_asyncio_and_run(self.turn_off_selected_light))
        self.off_button.pack(side="left", padx=5)

        self.color_var = tk.StringVar()
        self.color_dropdown = ttk.Combobox(controls_frame, textvariable=self.color_var)
        self.color_dropdown['values'] = ["Red", "Green", "Blue", "Yellow", "Cyan", "Magenta", "White"]
        self.color_dropdown.pack(side="left", padx=5)

        self.set_color_button = ttk.Button(controls_frame, text="Set Color", command=lambda: self.start_asyncio_and_run(self.set_color_selected_light))
        self.set_color_button.pack(side="left", padx=5)

        self.update_button = ttk.Button(controls_frame, text="Check for Updates", command=self.check_for_updates)
        self.update_button.pack(side="right", padx=5)

        # Log Frame
        log_frame = ttk.LabelFrame(self.root, text="Logs", padding="10")
        log_frame.pack(pady=10, padx=10, fill="both", expand=True)

        self.log_text = scrolledtext.ScrolledText(log_frame, width=70, height=10, state='disabled')
        self.log_text.pack(fill="both", expand=True)

    def check_for_updates(self):
        # Replace with the raw URL to your version.json file on GitHub
        version_url = "https://raw.githubusercontent.com/YOUR_USERNAME/YOUR_REPOSITORY/main/version.json"
        try:
            response = requests.get(version_url)
            response.raise_for_status() # Raise an exception for bad status codes
            remote_version = response.json()["version"]

            with open("version.json", "r") as f:
                local_version = json.load(f)["version"]

            if remote_version > local_version:
                if messagebox.askyesno("Update Available", f"A new version ({remote_version}) is available. Do you want to update?"):
                    self.apply_update(remote_version)
            else:
                messagebox.showinfo("No Updates", "You are already running the latest version.")

        except requests.exceptions.RequestException as e:
            messagebox.showerror("Update Error", f"Failed to check for updates: {e}")
        except (IOError, json.JSONDecodeError) as e:
            messagebox.showerror("Update Error", f"Failed to read version files: {e}")

    def apply_update(self, remote_version):
        # Replace with the raw URL to your meross_gui_app.py file on GitHub
        update_url = "https://raw.githubusercontent.com/YOUR_USERNAME/YOUR_REPOSITORY/main/meross_gui_app.py"
        try:
            response = requests.get(update_url)
            response.raise_for_status()

            with open("meross_gui_app.py", "w") as f:
                f.write(response.text)

            with open("version.json", "w") as f:
                json.dump({"version": remote_version}, f)

            messagebox.showinfo("Update Complete", "The application has been updated. It will now restart.")
            self.restart_app()

        except requests.exceptions.RequestException as e:
            messagebox.showerror("Update Error", f"Failed to download the update: {e}")
        except IOError as e:
            messagebox.showerror("Update Error", f"Failed to write the update: {e}")

    def restart_app(self):
        python = sys.executable
        os.execl(python, python, *sys.argv)


    def _setup_logging(self):
        # Remove default handlers
        for handler in logging.root.handlers[:]:
            logging.root.removeHandler(handler)
        
        # Setup logging to GUI
        self.log_text.config(state='normal')
        text_handler = TextWidgetHandler(self.log_text)
        logging.getLogger().setLevel(logging.INFO)
        logging.getLogger().addHandler(text_handler)
        self.log_text.config(state='disabled')

    def _load_credentials(self):
        key = load_key()
        if not key:
            logging.warning("Encryption key not found. Cannot load credentials.")
            return

        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, 'r') as f:
                    config = json.load(f)
                    self.meross_email.set(config.get("email", ""))
                    encrypted_password = config.get("password", "")
                    if encrypted_password:
                        try:
                            f = Fernet(key)
                            decrypted_password = f.decrypt(encrypted_password.encode()).decode()
                            self.meross_password.set(decrypted_password)
                        except InvalidToken:
                            logging.error("Failed to decrypt password. The encryption key may have changed.")
                            self.meross_password.set("") # Clear password field
                    self.remember_me.set(config.get("remember_me", True))
            except Exception as e:
                logging.warning(f"Could not load config file: {e}")

    def _save_credentials(self):
        key = load_key()
        if not key:
            logging.error("Encryption key not found. Cannot save credentials.")
            return

        if self.remember_me.get():
            try:
                f = Fernet(key)
                encrypted_password = f.encrypt(self.meross_password.get().encode()).decode()
                config = {
                    "email": self.meross_email.get(),
                    "password": encrypted_password,
                    "remember_me": self.remember_me.get()
                }
                with open(CONFIG_FILE, 'w') as f:
                    json.dump(config, f)
            except Exception as e:
                logging.error(f"Could not save config file: {e}")
        elif os.path.exists(CONFIG_FILE):
            os.remove(CONFIG_FILE) # Remove credentials if remember me is unchecked

    def start_asyncio_and_discover(self):
        if self.asyncio_thread and self.asyncio_thread.is_alive():
            logging.info("Asyncio loop already running.")
            return

        self.asyncio_loop = asyncio.new_event_loop()
        self.asyncio_thread = threading.Thread(target=self._run_asyncio_loop, daemon=True)
        self.asyncio_thread.start()
        self.asyncio_loop.call_soon_threadsafe(asyncio.create_task, self._discover_devices_async())

    def start_asyncio_and_run(self, coro):
        if not self.asyncio_loop or not self.asyncio_loop.is_running():
            logging.error("Asyncio loop not running.")
            return
        self.asyncio_loop.call_soon_threadsafe(asyncio.create_task, coro())

    def get_selected_light(self):
        selected_indices = self.lights_listbox.curselection()
        if not selected_indices:
            messagebox.showwarning("Warning", "Please select a light first.")
            return None
        
        light_index = selected_indices[0]
        return self.controllable_lights[light_index]

    async def turn_on_selected_light(self):
        light = self.get_selected_light()
        if light:
            try:
                await light.async_turn_on()
                logging.info(f"{light.name} turned on.")
            except Exception as e:
                logging.error(f"Failed to turn on {light.name}: {e}")

    async def turn_off_selected_light(self):
        light = self.get_selected_light()
        if light:
            try:
                await light.async_turn_off()
                logging.info(f"{light.name} turned off.")
            except Exception as e:
                logging.error(f"Failed to turn off {light.name}: {e}")

    async def set_color_selected_light(self):
        light = self.get_selected_light()
        if not light:
            return

        color_name = self.color_var.get()
        if not color_name:
            messagebox.showwarning("Warning", "Please select a color first.")
            return

        COLORS = {
            "Red": (255, 0, 0),
            "Green": (0, 255, 0),
            "Blue": (0, 0, 255),
            "Yellow": (255, 255, 0),
            "Cyan": (0, 255, 255),
            "Magenta": (255, 0, 255),
            "White": (255, 255, 255),
        }
        rgb = COLORS.get(color_name)

        if rgb:
            try:
                await light.async_set_light_color(rgb=rgb)
                logging.info(f"Set color of {light.name} to {color_name}.")
            except Exception as e:
                logging.error(f"Failed to set color of {light.name}: {e}")

    def _run_asyncio_loop(self):
        asyncio.set_event_loop(self.asyncio_loop)
        self.asyncio_loop.run_forever()

    async def _discover_devices_async(self):
        email = self.meross_email.get()
        password = self.meross_password.get()

        if not email or not password:
            messagebox.showerror("Error", "Please enter both email and password.")
            return

        self.root.after(0, lambda: self.login_button.config(state=tk.DISABLED, text="Logging in..."))
        self.root.after(0, lambda: self.lights_listbox.delete(0, tk.END))
        self.controllable_lights = []

        try:
            self.http_client = await MerossHttpClient.async_from_user_password(email=email, password=password, api_base_url="https://iot.meross.com")
            self.manager = MerossManager(http_client=self.http_client)
            await self.manager.async_init()
            await self.manager.async_device_discovery()
            all_devices = self.manager.find_devices()
            self.controllable_lights = [dev for dev in all_devices if isinstance(dev, LightMixin)]

            if not self.controllable_lights:
                logging.warning("No Meross lights found on your account.")
                self.root.after(0, lambda: messagebox.showinfo("Info", "No Meross lights found."))
            else:
                for light in self.controllable_lights:
                    self.root.after(0, lambda l=light: self.lights_listbox.insert(tk.END, f"{l.name} (UUID: {l.uuid})"))
                logging.info(f"Discovered {len(self.controllable_lights)} controllable light(s).")
            self._save_credentials() # Save credentials after successful login

        except Exception as e:
            logging.error(f"Failed to discover devices: {e}")
            self.root.after(0, lambda: messagebox.showerror("Error", f"Failed to discover devices: {e}"))
            if self.http_client:
                await self.http_client.async_logout()
            self.http_client = None
            self.manager = None
        finally:
            self.root.after(0, lambda: self.login_button.config(state=tk.NORMAL, text="Login & Discover Devices"))

def run_app():
    root = tk.Tk()
    app = MerossApp(root)
    root.mainloop()

if __name__ == "__main__":
    run_app()