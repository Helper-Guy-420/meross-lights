# meross-lights

- controll you meross lights will keep adding as i go                     │
│     1 + # Meross Light Controller GUI App                                       │
│     2                                                                           │
│     4 - you do need a meross account for this                                   │
│     3 + ## Introduction                                                         │
│     4                                                                           │
│     5 + This is a Python-based Graphical User Interface (GUI) application for   │
│       controlling Meross smart lights. It allows users to log in to their       │
│       Meross account, discover lights, and control them with a user-friendly    │
│       interface.                                                                │
│     6                                                                           │
│     7 -  you will have to nano into file and add your account info then save    │
│       and run.                                                                  │
│     7 + ## Features                                                             │
│     8                                                                           │
│     9 -  get into you environment.                                              │
│     9 + - Secure credential storage using encryption.                           │
│    10 + - Real-time logging displayed within the GUI.                           │
│    11 + - Discovery of Meross smart lights associated with your account.        │
│    12 + - Multi-light selection using checkboxes.                               │
│    13 + - Turn lights On/Off.                                                   │
│    14 + - Set light color from a predefined list.                               │
│    15                                                                           │
│    11 -  this is where my env is yours might be different.                      │
│    16 + ## Installation                                                         │
│    17                                                                           │
│    18 + To set up and run this application, follow these steps:                 │
│    19 +                                                                         │
│    20 + 1.  **Clone the repository:**                                           │
│    21 +                                                                         │
│    22 +     ```bash                                                             │
│    23 +     git clone https://github.com/Helper-Guy-420/meross-lights.git       │
│    24 +     cd meross-lights                                                    │
│    25 +     ```                                                                 │
│    26 +                                                                         │
│    27 + 2.  **Create a virtual environment (recommended):**                     │
│    28 +                                                                         │
│    29 +     ```bash                                                             │
│    30 +     python3 -m venv meross_env                                          │
│    31       source meross_env/bin/activate                                      │
│    32 +     ```                                                                 │
│    33                                                                           │
│    15 - then you can run your app                                               │
│    ════════════════════════════════════════════════════════════════════════════ │
│    34 + 3.  **Install dependencies:**                                           │
│    35                                                                           │
│    36 +     ```bash                                                             │
│    37 +     pip install meross_iot cryptography tkinter                         │
│    38 +     ```                                                                 │
│    39 +                                                                         │
│    40 +     *Note: `tkinter` is usually included with Python installations. If  │
│       you encounter issues, you might need to install it via your system's      │
│       package manager (e.g., `sudo apt-get install python3-tk` on               │
│       Debian/Ubuntu).*                                                          │
│    41 +                                                                         │
│    42 + ## Setup & Usage                                                        │
│    43 +                                                                         │
│    44 + 1.  **Run the application:**                                            │
│    45 +                                                                         │
│    46 +     ```bash                                                             │
│    47       python meross_gui_app.py                                            │
│    48 +     ```                                                                 │
│    49                                                                           │
│    50 + 2.  **Login:** Enter your Meross account email and password in the      │
│       respective fields. You can choose to have your credentials remembered     │
│       securely.                                                                 │
│    51 +                                                                         │
│    52 + 3.  **Discover Devices:** Click the "Login & Discover Devices" button.  │
│       The application will connect to your Meross account and list all          │
│       discovered lights.                                                        │
│    53 +                                                                         │
│    54 + 4.  **Control Lights:**                                                 │
│    55 +     *   Select one or more lights using the checkboxes.                 │
│    56 +     *   Use the "On" and "Off" buttons to toggle the selected lights.   │
│    57 +     *   Choose a color from the dropdown and click "Set Color" to       │
│       change the color of the selected lights.            
