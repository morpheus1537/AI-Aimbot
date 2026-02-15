import json
import os
import sys
import threading
from pynput import keyboard
from termcolor import colored

def on_release(key):
    try:
        if key == keyboard.Key.f2:
            Aimbot.clean_up()
        # DEL toggles aimbot on/off (ColorBot-style)
        if hasattr(keyboard.Key, "delete") and key == keyboard.Key.delete:
            Aimbot.update_status_aimbot()
    except NameError:
        pass

def run_aimbot():
    global lunar
    lunar = Aimbot(collect_data="collect_data" in sys.argv)
    lunar.start()

def main():
    global Aimbot
    from lib.aimbot import Aimbot
    listener = keyboard.Listener(on_release=on_release)
    listener.start()
    aimbot_thread = threading.Thread(target=run_aimbot, daemon=True)
    aimbot_thread.start()
    from lib.gui import run_gui
    run_gui()

def setup():
    path = "lib/config"
    if not os.path.exists(path):
        os.makedirs(path)

    print("[INFO] In-game X and Y axis sensitivity should be the same")
    def prompt(str):
        valid_input = False
        while not valid_input:
            try:
                number = float(input(str))
                valid_input = True
            except ValueError:
                print("[!] Invalid Input. Make sure to enter only the number (e.g. 6.9)")
        return number

    xy_sens = prompt("X-Axis and Y-Axis Sensitivity (from in-game settings): ")
    targeting_sens = prompt("Targeting Sensitivity (from in-game settings): ")

    print("[INFO] Your in-game targeting sensitivity must be the same as your scoping sensitivity")
    sensitivity_settings = {
        "xy_sens": xy_sens,
        "targeting_sens": targeting_sens,
        "xy_scale": 10/xy_sens,
        "targeting_scale": 1000/(targeting_sens * xy_sens),
        "aim_key": "0x02",
        "aimkey1": "0x02",
        "aimkey2": "none",
        "aimkey3": "none",
        "aim_method": "normal",
        "hold_duration": 2.0,
        "fov_radius": 150,
        "lock_threshold": 18,
        "trigger_cooldown": 0.07,
        "max_move_per_frame": 35,
        "inference_size": 320,
        "capture_size": 256,
        "device": "cpu",
        "target_smoothing": 0.5,
        "stick_radius": 70,
        "movement_mode": "proportional",
        "aim_speed": 0.35,
        "proportional_max_step": 80,
        "target_mode": "closest_to_center",
        "humanize_smoothing": 0.25,
        "humanize_delay_min": 0,
        "humanize_delay_max": 0,
        "humanize_jitter": 0,
    }

    with open('lib/config/config.json', 'w') as outfile:
        json.dump(sensitivity_settings, outfile)
    print("[INFO] Sensitivity configuration complete")

if __name__ == "__main__":
    os.system('cls' if os.name == 'nt' else 'clear')
    os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = '1'

    print(colored('''

  _    _   _ _   _    _    ____     _     ___ _____ _____ 
 | |  | | | | \ | |  / \  |  _ \   | |   |_ _|_   _| ____|
 | |  | | | |  \| | / _ \ | |_) |  | |    | |  | | |  _|  
 | |__| |_| | |\  |/ ___ \|  _ <   | |___ | |  | | | |___ 
 |_____\___/|_| \_/_/   \_\_| \_\  |_____|___| |_| |_____|
                                                                         
(Neural Network Aimbot)''', "green"))
    
    print(colored('To get full version of Lunar V2, visit https://gannonr.com/lunar OR join the discord: discord.gg/aiaimbot', "red"))

    path_exists = os.path.exists("lib/config/config.json")
    if not path_exists or ("setup" in sys.argv):
        if not path_exists:
            print("[!] Sensitivity configuration is not set")
        setup()
    path_exists = os.path.exists("lib/data")
    if "collect_data" in sys.argv and not path_exists:
        os.makedirs("lib/data")
    main()
