import ctypes
import cv2
import json
import math
import mss
import os
import random
import re
import sys
import time
import torch
import numpy as np
import win32api
from termcolor import colored
from ultralytics import YOLO
import socket

try:
    import serial
except ImportError:
    serial = None

# If you're a skid and you know it clap your hands 👏👏

# Auto Screen Resolution
screensize = {'X': ctypes.windll.user32.GetSystemMetrics(0), 'Y': ctypes.windll.user32.GetSystemMetrics(1)}

# If you use stretched res, hardcode the X and Y. For example: screen_res_x = 1234
screen_res_x = screensize['X']
screen_res_y = screensize['Y']

# Divide screen_res by 2
# No need to change this
screen_x = int(screen_res_x / 2)
screen_y = int(screen_res_y / 2)

aim_height = 10 # Legacy default; overridden by config "aim_offset" (0.0=top of box, 0.5=center, 1.0=bottom)

fov = 350

confidence = 0.45 # How confident the AI needs to be for it to lock on to the player. Default is 45%

use_trigger_bot = True # Will shoot if crosshair is locked on the player

# Detailed trigger/aim debugging: set LUNAR_DEBUG=1 or run with --debug to enable
TRIGGER_DEBUG = os.environ.get("LUNAR_DEBUG", "").lower() in ("1", "true", "yes") or "--debug" in sys.argv
DEBUG_LOG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "debug_trigger.log")
DEBUG_STICK_LOG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "debug_stick.log")
_debug_last_log_time = 0.0
_debug_log_interval = 0.25  # min seconds between log lines when target visible
_debug_stick_log_interval = 0.12  # stick debug: log every ~0.12s when target visible (or every frame if not moving)
_debug_key_log_interval = 1.0  # log raw key state every N seconds
_debug_last_key_log_time = 0.0
_debug_log_header_written = False
_debug_stick_header_written = False
_debug_last_stick_log_time = 0.0


def _debug_trigger_log(has_target, locked, rmb_held, lmb_held, aimbot_on, did_move, did_trigger_click):
    """Write one line to debug log (throttled). All args are booleans/state for this frame."""
    global _debug_last_log_time, _debug_last_key_log_time, _debug_log_header_written
    now = time.perf_counter()
    if not TRIGGER_DEBUG:
        return
    # Throttle: when we have a target, log at most every _debug_log_interval
    if has_target and (now - _debug_last_log_time) < _debug_log_interval:
        return
    if has_target:
        _debug_last_log_time = now
    # Raw key state log (so user can verify LMB/RMB are seen) every N seconds
    log_key_state = (now - _debug_last_key_log_time) >= _debug_key_log_interval
    if log_key_state:
        _debug_last_key_log_time = now

    try:
        raw_lmb = win32api.GetAsyncKeyState(0x01)  # 0x01 = VK_LBUTTON
        raw_rmb = win32api.GetAsyncKeyState(0x02)  # 0x02 = VK_RBUTTON
        with open(DEBUG_LOG_PATH, "a", encoding="utf-8") as f:
            if not _debug_log_header_written:
                _debug_log_header_written = True
                f.write(
                    "# LUNAR TRIGGER DEBUG LOG\n"
                    "# rmb_held = Right Mouse (aim); lmb_held = Left Mouse (fire). "
                    "raw 0x8000 = key down. Aim only moves when rmb_held=1; trigger fires when locked and lmb_held=0.\n"
                    "# ---\n"
                )
            ts = time.strftime("%H:%M:%S", time.localtime()) + f".{int((now % 1) * 1000):03d}"
            if has_target:
                f.write(
                    f"[{ts}] target=1 locked={int(locked)} rmb={int(rmb_held)} lmb={int(lmb_held)} "
                    f"aimbot_on={int(aimbot_on)} move_crosshair={int(did_move)} trigger_click={int(did_trigger_click)} "
                    f"| raw_lmb=0x{raw_lmb & 0xFFFF:04X} raw_rmb=0x{raw_rmb & 0xFFFF:04X}\n"
                )
            if log_key_state:
                f.write(
                    f"[{ts}] [keys] LMB=0x{raw_lmb & 0xFFFF:04X} (bit15=down) RMB=0x{raw_rmb & 0xFFFF:04X} "
                    f"| rmb_held={rmb_held} lmb_held={lmb_held}\n"
                )
    except Exception:
        pass  # don't break aimbot if log fails


def _debug_stick_log(
    crosshair_x, crosshair_y, aim_x, aim_y, dist_to_aim, stick_radius,
    crosshair_in_hitbox, following_same_target, just_fired, aimbot_on, will_move,
    reason_no_move, box_left, box_right, box_top, box_bottom,
    cursor_pos=None, move_dx=None, move_dy=None, move_skipped_reason=None,
    switched_target=False, locked=False
):
    """Detailed stick debug: mouse vs target, why crosshair sticks or not, why it goes away."""
    global _debug_stick_header_written, _debug_last_stick_log_time
    if not TRIGGER_DEBUG:
        return
    now = time.perf_counter()
    throttle = _debug_stick_log_interval
    if will_move and (now - _debug_last_stick_log_time) < throttle:
        return
    _debug_last_stick_log_time = now
    try:
        with open(DEBUG_STICK_LOG_PATH, "a", encoding="utf-8") as f:
            if not _debug_stick_header_written:
                _debug_stick_header_written = True
                f.write(
                    "# LUNAR STICK DEBUG — mouse vs target, why crosshair sticks or not, why it goes away\n"
                    "# crosshair = screen center (where game aims). cursor = actual Windows cursor. aim = target head.\n"
                    "# will_move=1 we call move_crosshair. reason_no_move when will_move=0. move_skipped = inside move_crosshair we did not move (dead_zone/aim_key).\n"
                    "# switched_target=1 we locked a different target. When crosshair \"goes away\" check target_lost / switched_target / move_skipped.\n"
                    "# ---\n"
                )
            ts = time.strftime("%H:%M:%S", time.localtime()) + f".{int((now % 1) * 1000):03d}"
            f.write(
                f"[{ts}] crosshair=({crosshair_x},{crosshair_y}) aim=({aim_x:.0f},{aim_y:.0f}) "
                f"dist_to_aim={dist_to_aim:.0f} stick_r={stick_radius} "
                f"in_hitbox={int(crosshair_in_hitbox)} following={int(following_same_target)} "
                f"just_fired={int(just_fired)} aimbot_on={int(aimbot_on)} will_move={int(will_move)} locked={int(locked)}"
            )
            if cursor_pos is not None:
                f.write(f" cursor=({cursor_pos[0]},{cursor_pos[1]})")
            if move_dx is not None and move_dy is not None:
                f.write(f" sent_dx={move_dx:.1f} sent_dy={move_dy:.1f}")
            if move_skipped_reason:
                f.write(f" move_skipped={move_skipped_reason}")
            if switched_target:
                f.write(" switched_target=1")
            if reason_no_move:
                f.write(f" | reason_no_move={reason_no_move}")
            f.write(
                f" | hitbox=[{box_left},{box_top})-({box_right},{box_bottom})]\n"
            )
    except Exception:
        pass


def _debug_stick_log_target_lost(frames_without_target, last_aim_x, last_aim_y):
    """Log when we lose the target (crosshair 'goes away' because target disappeared)."""
    global _debug_stick_header_written, _debug_last_stick_log_time
    if not TRIGGER_DEBUG:
        return
    now = time.perf_counter()
    if (now - _debug_last_stick_log_time) < _debug_stick_log_interval:
        return
    _debug_last_stick_log_time = now
    try:
        with open(DEBUG_STICK_LOG_PATH, "a", encoding="utf-8") as f:
            if not _debug_stick_header_written:
                _debug_stick_header_written = True
                f.write(
                    "# LUNAR STICK DEBUG — mouse vs target, why crosshair sticks or not\n"
                    "# ---\n"
                )
            ts = time.strftime("%H:%M:%S", time.localtime()) + f".{int((now % 1) * 1000):03d}"
            ax = last_aim_x if last_aim_x is not None else 0
            ay = last_aim_y if last_aim_y is not None else 0
            f.write(
                f"[{ts}] target_lost frames_without={frames_without_target} "
                f"last_aim=({ax:.0f},{ay:.0f}) | crosshair goes away: no target to stick to\n"
            )
    except Exception:
        pass


mouse_methods = ['win32', 'ddxoft', 'makcu', 'colorbot', 'arduino']
mouse_method = mouse_methods[1]  # default; can override in config with "mouse_method"
second_pc_ip = '192.67.67.67'  # for makcu


def _get_config_path():
    """Path to config.json (shared with GUI)."""
    try:
        from lib.config_path import CONFIG_PATH
        return CONFIG_PATH
    except ImportError:
        return os.path.join(os.path.dirname(os.path.abspath(__file__)), "config", "config.json")

def _arduino_port_from_config():
    """Get COM port from config (e.g. COM3). Returns None if not set or invalid."""
    try:
        with open(_get_config_path(), "r", encoding="utf-8") as f:
            cfg = json.load(f)
        port = (cfg.get("arduino_port") or "").strip()
        if not port:
            return None
        m = re.match(r"(COM\d+)", port, re.IGNORECASE)
        return m.group(1).upper() if m else None
    except Exception:
        return None


class ArduinoMouse:
    """Send move/click over serial to Arduino (HID mouse). Games often don't block real USB input."""
    PROTOCOL_MOVE = "M,{dx},{dy}\n"  # relative move
    PROTOCOL_CLICK = "L\n"            # left click (Arduino does down+up)

    def __init__(self, port, baud=115200):
        self._serial = None
        self._port = port
        self._baud = baud

    def connect(self):
        if serial is None:
            return False, "pip install pyserial"
        if not self._port:
            return False, "Set arduino_port in lib/config/config.json (e.g. COM3)"
        try:
            self._serial = serial.Serial(port=self._port, baudrate=self._baud, timeout=0.05, write_timeout=0.5)
            return self._serial.is_open, None
        except Exception as e:
            return False, str(e)

    def move(self, dx, dy):
        if self._serial is None or not self._serial.is_open:
            return False
        try:
            self._serial.write(self.PROTOCOL_MOVE.format(dx=int(dx), dy=int(dy)).encode("ascii"))
            self._serial.flush()
            return True
        except Exception:
            self._serial = None
            return False

    def click(self):
        if self._serial is None or not self._serial.is_open:
            return False
        try:
            self._serial.write(self.PROTOCOL_CLICK.encode("ascii"))
            self._serial.flush()
            return True
        except Exception:
            self._serial = None
            return False

PUL = ctypes.POINTER(ctypes.c_ulong)
class KeyBdInput(ctypes.Structure):
    _fields_ = [("wVk", ctypes.c_ushort),
                ("wScan", ctypes.c_ushort),
                ("dwFlags", ctypes.c_ulong),
                ("time", ctypes.c_ulong),
                ("dwExtraInfo", PUL)]

class HardwareInput(ctypes.Structure):
    _fields_ = [("uMsg", ctypes.c_ulong),
                ("wParamL", ctypes.c_short),
                ("wParamH", ctypes.c_ushort)]

class MouseInput(ctypes.Structure):
    _fields_ = [("dx", ctypes.c_long),
                ("dy", ctypes.c_long),
                ("mouseData", ctypes.c_ulong),
                ("dwFlags", ctypes.c_ulong),
                ("time", ctypes.c_ulong),
                ("dwExtraInfo", PUL)]

class Input_I(ctypes.Union):
    _fields_ = [("ki", KeyBdInput),
                ("mi", MouseInput),
                ("hi", HardwareInput)]

class Input(ctypes.Structure):
    _fields_ = [("type", ctypes.c_ulong),
                ("ii", Input_I)]

class POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


class MAKCU_UDP:
    def __init__(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    def send(self, msg):
        self.sock.sendto(msg.encode("utf-8"), (second_pc_ip, 5005))
    
    def move(self, x, y):
        msg = f"MOVE:{int(x)},{int(y)}"
        self.send(msg)

    def click(self):
        self.send("CLICK:LEFT")

class Aimbot:
    extra = ctypes.c_ulong(0)
    ii_ = Input_I()
    screen = None  # set in start() so mss runs in the capture thread (mss uses thread-local handles)

    pixel_increment = 1 # controls how many pixels the mouse moves for each relative movement

    _config_path = _get_config_path()
    try:
        with open(_config_path, "r", encoding="utf-8") as f:
            sens_config = json.load(f)
    except Exception:
        sens_config = {}
    aimbot_status = colored("ENABLED", 'green')
    aimbot_enabled = True  # simple flag for GUI / external readers
    last_trigger_time = 0.0  # cooldown between triggerbot clicks so game registers each shot
    trigger_cooldown = 0.07  # seconds between auto-fire clicks (lower = faster response, min ~0.04)
    post_trigger_freeze = 0.015  # seconds to skip mouse movement after firing (must be < trigger_cooldown so aim adjusts between shots)

    mouse_dll = None
    makcu = None
    arduino_mouse = None  # ArduinoMouse if method is arduino
    aim_key_vk = 0x02  # kept for single-key fallback
    aim_keys = [0x02]  # list of VK codes (aimkey1, aimkey2, aimkey3); set in __init__
    aim_method = "normal"  # normal | hold_release | target_hold
    hold_duration = 2.0  # seconds; only for hold_release
    hold_start_time = None  # for hold_release
    _target_hold_keys_pressed = False  # for target_hold
    _tracking_locked = False  # True once crosshair reaches target; enables full-speed tracking
    request_config_reload = False  # set by GUI when config saved → reload next frame

    if mouse_method.lower() == "makcu":
        makcu = MAKCU_UDP()

    def __init__(self, box_constant = fov, collect_data = False, mouse_delay = 0.0009):
        #controls the initial centered box width and height of the "Lunar Vision" window
        self.box_constant = box_constant #controls the size of the detection box (equaling the width and height)

        print("[INFO] Loading the neural network model")
        self.model = YOLO('lib/best.pt')
        if torch.cuda.is_available():
            print(colored("CUDA ACCELERATION [ENABLED]", "green"))
        else:
            print(colored("[!] CUDA ACCELERATION IS UNAVAILABLE", "red"))
            print(colored("[!] Check your PyTorch installation, else performance will be poor", "red"))

        try:
            Aimbot.conf = max(0.1, min(1.0, float(Aimbot.sens_config.get("detection_confidence", 0.45))))
        except Exception:
            Aimbot.conf = 0.45
        self.conf = getattr(Aimbot, "conf", confidence)  # instance fallback; predict uses Aimbot.conf so config reload applies
        self.iou = 0.45  # NMS IoU (0-1)
        self.collect_data = collect_data
        self.mouse_delay = mouse_delay
        # Allow config to override mouse method (e.g. "arduino" when game blocks software input)
        try:
            cfg_method = (Aimbot.sens_config.get("mouse_method") or "").strip().lower()
            if cfg_method in [m.lower() for m in mouse_methods]:
                self.mouse_method = cfg_method
            else:
                self.mouse_method = mouse_method
        except Exception:
            self.mouse_method = mouse_method

        if self.mouse_method.lower() == 'arduino':
            port = _arduino_port_from_config()
            Aimbot.arduino_mouse = ArduinoMouse(port) if port else None
            ok, err = Aimbot.arduino_mouse.connect() if Aimbot.arduino_mouse else (False, "No port")
            if not ok:
                Aimbot.arduino_mouse = None
                self.mouse_method = 'colorbot'
                print(colored('[!] Arduino failed: ' + (err or "not connected"), 'yellow'))
                print(colored('[!] Using ColorBot-style. Set arduino_port in config + flash Arduino for hardware mouse.', 'yellow'))
        elif self.mouse_method.lower() == 'ddxoft':
            dll_path = os.path.abspath("lib/mouse/dd40605x64.dll")
            try:
                if not os.path.exists(dll_path):
                    raise FileNotFoundError(f"ddxoft DLL not found at {dll_path}")
                Aimbot.mouse_dll = ctypes.WinDLL(dll_path)
                time.sleep(1)
                Aimbot.mouse_dll.DD_btn.argtypes = [ctypes.c_int]
                Aimbot.mouse_dll.DD_btn.restype = ctypes.c_int
                Aimbot.mouse_dll.DD_movR.argtypes = [ctypes.c_long, ctypes.c_long]
                Aimbot.mouse_dll.DD_movR.restype = None  # void in many DD builds
                init = Aimbot.mouse_dll.DD_btn(0)
                if not init == 1:
                    raise RuntimeError("DD_btn(0) init failed")
                print(colored('Loaded ddxoft successfully!', 'green'))
            except (OSError, FileNotFoundError, RuntimeError) as e:
                Aimbot.mouse_dll = None
                self.mouse_method = 'colorbot'
                print(colored('[!] ddxoft failed (often needs "Run as administrator"): ' + str(e), 'yellow'))
                print(colored('[!] Using ColorBot-style input (mouse_event). Run as Admin for ddxoft.', 'yellow'))

        # Aim keys and aim method (ColorBot-style)
        aim_keys = []
        for i in range(1, 4):
            key_val = str(Aimbot.sens_config.get(f"aimkey{i}", Aimbot.sens_config.get("aim_key", "0x02") if i == 1 else "none")).strip().lower()
            if key_val and key_val != "none":
                try:
                    aim_keys.append(int(key_val, 16))
                except ValueError:
                    pass
        Aimbot.aim_keys = aim_keys if aim_keys else [int(str(Aimbot.sens_config.get("aim_key", "0x02")).strip(), 16)]
        Aimbot.aim_key_vk = Aimbot.aim_keys[0] if Aimbot.aim_keys else 0x02
        try:
            Aimbot.aim_method = (Aimbot.sens_config.get("aim_method") or "normal").strip().lower()
            if Aimbot.aim_method not in ("normal", "hold_release", "target_hold"):
                Aimbot.aim_method = "normal"
        except Exception:
            Aimbot.aim_method = "normal"
        try:
            Aimbot.hold_duration = float(Aimbot.sens_config.get("hold_duration", 2.0))
        except Exception:
            Aimbot.hold_duration = 2.0
        # FOV: "hitbox" = only consider targets when crosshair is inside their detection box; "radius" = within fov_radius px of crosshair
        try:
            Aimbot.fov_mode = (Aimbot.sens_config.get("fov_mode") or "hitbox").strip().lower()
            if Aimbot.fov_mode not in ("hitbox", "radius"):
                Aimbot.fov_mode = "hitbox"
        except Exception:
            Aimbot.fov_mode = "hitbox"
        try:
            Aimbot.hitbox_margin = max(0, int(Aimbot.sens_config.get("hitbox_margin", 0)))
        except Exception:
            Aimbot.hitbox_margin = 0
        try:
            Aimbot.fov_radius = int(Aimbot.sens_config.get("fov_radius", 150))
            if Aimbot.fov_radius < 0:
                Aimbot.fov_radius = 0
        except Exception:
            Aimbot.fov_radius = 150
        # Lock threshold: crosshair within this many pixels of target head = "locked" for autotrigger (higher = fire sooner when near target)
        try:
            Aimbot.lock_threshold = max(1, int(Aimbot.sens_config.get("lock_threshold", 18)))
        except Exception:
            Aimbot.lock_threshold = 18
        # Trigger cooldown: min seconds between shots (lower = snappier, but too low can miss in-game)
        try:
            Aimbot.trigger_cooldown = max(0.04, float(Aimbot.sens_config.get("trigger_cooldown", 0.07)))
        except Exception:
            Aimbot.trigger_cooldown = 0.07
        # Max movement steps per frame: prevents aim from shooting to screen edge (smooth stick to target)
        try:
            Aimbot.max_move_per_frame = max(5, int(Aimbot.sens_config.get("max_move_per_frame", 35)))
        except Exception:
            Aimbot.max_move_per_frame = 35
        # Inference size: smaller = higher FPS when game uses GPU (less GPU load). Ultralytics scales boxes back to capture size.
        try:
            Aimbot.inference_size = max(224, min(640, int(Aimbot.sens_config.get("inference_size", 320))))
        except Exception:
            Aimbot.inference_size = 320
        # Capture size: smaller = faster grab + inference when game is running (default 256 for in-game FPS).
        try:
            Aimbot.capture_size = max(192, min(480, int(Aimbot.sens_config.get("capture_size", 256))))
        except Exception:
            Aimbot.capture_size = 256
        # Device: "cpu" avoids GPU contention with game (often 5–15 FPS vs 1 FPS when game uses GPU).
        try:
            Aimbot.device = (Aimbot.sens_config.get("device") or "cuda").strip().lower()
            if Aimbot.device not in ("cuda", "cpu"):
                Aimbot.device = "cuda" if torch.cuda.is_available() else "cpu"
        except Exception:
            Aimbot.device = "cuda" if torch.cuda.is_available() else "cpu"
        # Target smoothing: 0 = raw position, 1 = max smoothing (reduces jitter, more consistent tracking)
        try:
            Aimbot.target_smoothing = max(0.0, min(1.0, float(Aimbot.sens_config.get("target_smoothing", 0.5))))
        except Exception:
            Aimbot.target_smoothing = 0.5
        # Stick radius: prefer same target if a detection is within this many px of last target (stops flipping between enemies)
        try:
            Aimbot.stick_radius = max(20, int(Aimbot.sens_config.get("stick_radius", 70)))
        except Exception:
            Aimbot.stick_radius = 70
        # Coast frames: continue aiming toward predicted position for N frames after detection drops
        try:
            Aimbot.coast_frames = max(0, int(Aimbot.sens_config.get("coast_frames", 8)))
        except Exception:
            Aimbot.coast_frames = 8
        # Prediction factor: how much velocity prediction to apply during coast (0=none, 1=full linear)
        try:
            Aimbot.prediction_factor = max(0.0, min(1.0, float(Aimbot.sens_config.get("prediction_factor", 0.4))))
        except Exception:
            Aimbot.prediction_factor = 0.4
        # Detection buffer size: median filter over last N detections to kill jitter
        try:
            Aimbot.detection_buffer_size = max(1, min(15, int(Aimbot.sens_config.get("detection_buffer_size", 5))))
        except Exception:
            Aimbot.detection_buffer_size = 5
        # ColorBot-style: movement mode and aim speed (proportional = speed * error per frame)
        try:
            Aimbot.movement_mode = (Aimbot.sens_config.get("movement_mode") or "proportional").strip().lower()
            if Aimbot.movement_mode not in ("interpolate", "proportional"):
                Aimbot.movement_mode = "proportional"
        except Exception:
            Aimbot.movement_mode = "proportional"
        try:
            Aimbot.aim_speed = max(0.05, min(1.0, float(Aimbot.sens_config.get("aim_speed", 0.35))))
        except Exception:
            Aimbot.aim_speed = 0.35
        try:
            Aimbot.aim_speed_x_scale = max(0.2, min(3.0, float(Aimbot.sens_config.get("aim_speed_x_scale", 1.0))))
        except Exception:
            Aimbot.aim_speed_x_scale = 1.0
        try:
            Aimbot.aim_speed_y_scale = max(0.2, min(3.0, float(Aimbot.sens_config.get("aim_speed_y_scale", 1.0))))
        except Exception:
            Aimbot.aim_speed_y_scale = 1.0
        try:
            Aimbot.proportional_max_step = max(10, int(Aimbot.sens_config.get("proportional_max_step", 80)))
        except Exception:
            Aimbot.proportional_max_step = 80
        try:
            Aimbot.post_trigger_freeze = max(0.0, min(0.2, float(Aimbot.sens_config.get("post_trigger_freeze", 0.015))))
        except Exception:
            Aimbot.post_trigger_freeze = 0.015
        # Humanize (ColorBot-style): smoothing, delay range (ms), jitter
        try:
            Aimbot.humanize_smoothing = max(0.0, min(1.0, float(Aimbot.sens_config.get("humanize_smoothing", 0.25))))
        except Exception:
            Aimbot.humanize_smoothing = 0.25
        try:
            Aimbot.humanize_delay_min = max(0, int(Aimbot.sens_config.get("humanize_delay_min", 0)))
        except Exception:
            Aimbot.humanize_delay_min = 0
        try:
            Aimbot.humanize_delay_max = max(0, int(Aimbot.sens_config.get("humanize_delay_max", 0)))
        except Exception:
            Aimbot.humanize_delay_max = 0
        try:
            Aimbot.humanize_jitter = max(0.0, float(Aimbot.sens_config.get("humanize_jitter", 0.0)))
        except Exception:
            Aimbot.humanize_jitter = 0.0
        # Target mode: closest_to_center (default) or topmost (highest on screen, like ColorBot)
        try:
            Aimbot.target_mode = (Aimbot.sens_config.get("target_mode") or "closest_to_center").strip().lower()
            if Aimbot.target_mode not in ("closest_to_center", "topmost"):
                Aimbot.target_mode = "closest_to_center"
        except Exception:
            Aimbot.target_mode = "closest_to_center"
        try:
            Aimbot.aim_offset = max(0.0, min(1.0, float(Aimbot.sens_config.get("aim_offset", 0.08))))
        except Exception:
            Aimbot.aim_offset = 0.08

        # Always show which mouse method is active
        if self.mouse_method.lower() == 'ddxoft':
            print(colored("[OK] Mouse input: ddxoft (driver) — aim and trigger should work in-game", "green"))
        elif self.mouse_method.lower() == 'makcu':
            print(colored("[OK] Mouse input: makcu (second PC over UDP)", "green"))
        elif self.mouse_method.lower() == 'arduino':
            print(colored("[OK] Mouse input: Arduino (hardware USB) — games usually don't block this", "green"))
        elif self.mouse_method.lower() == 'colorbot':
            keys_str = ",".join("0x%02X" % k for k in Aimbot.aim_keys[:3])
            print(colored("[OK] Mouse input: ColorBot-style (mouse_event + aim keys %s)" % keys_str, "green"))
        else:
            print(colored("[!] Mouse input: Win32 — many games IGNORE this. Use colorbot/arduino or run as Admin for ddxoft.", "red"))

        print("\n[INFO] DEL = toggle aimbot | F2 = quit (or use GUI Start/Stop)")
        print(colored("[OK] Detection: inference_size=%d, capture_size=%d, device=%s (use CPU in GUI if FPS is 1 in-game)" % (getattr(Aimbot, "inference_size", 320), getattr(Aimbot, "capture_size", 256), getattr(Aimbot, "device", "cuda")), "green"))
        if TRIGGER_DEBUG:
            print(f"[DEBUG] Trigger/aim logging -> {DEBUG_LOG_PATH}")
            print(f"[DEBUG] Stick debug (target, crosshair, why no move) -> {DEBUG_STICK_LOG_PATH}")

    def set_aimbot_enabled(enabled):
        """Enable or disable the aimbot (used by GUI Start/Stop buttons)."""
        if enabled:
            Aimbot.aimbot_status = colored("ENABLED", 'green')
            Aimbot.aimbot_enabled = True
        else:
            Aimbot.aimbot_status = colored("DISABLED", 'red')
            Aimbot.aimbot_enabled = False
        sys.stdout.write("\033[K")
        print(f"[!] AIMBOT IS [{Aimbot.aimbot_status}]", end="\r")

    def update_status_aimbot():
        """Toggle aimbot on/off (kept for compatibility)."""
        Aimbot.set_aimbot_enabled(not Aimbot.is_aimbot_enabled())

    def _keybd_aim_keys_down():
        for vk in Aimbot.aim_keys:
            ctypes.windll.user32.keybd_event(vk, 0, 0, 0)

    def _keybd_aim_keys_up():
        for vk in Aimbot.aim_keys:
            ctypes.windll.user32.keybd_event(vk, 0, 2, 0)  # KEYEVENTF_KEYUP = 2

    def _any_aim_key_held():
        return any((win32api.GetAsyncKeyState(vk) & 0x8000) != 0 for vk in Aimbot.aim_keys)

    def left_click(self):
        match self.mouse_method.lower():
            case 'ddxoft':
                Aimbot.mouse_dll.DD_btn(1)   # LButton down
                Aimbot.sleep(0.025)          # 25ms hold so game registers (was 1ms)
                Aimbot.mouse_dll.DD_btn(2)   # LButton up
            case 'win32':
                ctypes.windll.user32.mouse_event(0x0002, 0, 0, 0, 0)
                Aimbot.sleep(0.0001)
                ctypes.windll.user32.mouse_event(0x0004, 0, 0, 0, 0)
            case 'colorbot':
                ctypes.windll.user32.mouse_event(0x0002, 0, 0, 0, 0)
                Aimbot.sleep(0.025)
                ctypes.windll.user32.mouse_event(0x0004, 0, 0, 0, 0)
            case 'arduino':
                if Aimbot.arduino_mouse and Aimbot.arduino_mouse.click():
                    Aimbot.sleep(0.02)
                else:
                    # fallback if serial dropped
                    ctypes.windll.user32.mouse_event(0x0002, 0, 0, 0, 0)
                    Aimbot.sleep(0.025)
                    ctypes.windll.user32.mouse_event(0x0004, 0, 0, 0, 0)
            case 'makcu':
                if Aimbot.makcu:
                    Aimbot.makcu.click()

    def sleep(duration, get_now = time.perf_counter):
        if duration == 0: return
        now = get_now()
        end = now + duration
        while now < end:
            now = get_now()

    def is_aimbot_enabled():
        return Aimbot.aimbot_status == colored("ENABLED", 'green')

    def is_shooting():
        # GetAsyncKeyState: works from any thread; GetKeyState only sees keys in this thread's queue
        return (win32api.GetAsyncKeyState(0x01) & 0x8000) != 0

    def is_targeted():
        return Aimbot._any_aim_key_held()

    def is_target_locked(x, y):
        th = getattr(Aimbot, "lock_threshold", 18)
        return screen_x - th <= x <= screen_x + th and screen_y - th <= y <= screen_y + th

    def _do_move(self, rel_x, rel_y):
        """Single relative move (used by both interpolate and proportional)."""
        match self.mouse_method.lower():
            case 'ddxoft':
                Aimbot.mouse_dll.DD_movR(int(rel_x), int(rel_y))
            case 'win32':
                Aimbot.ii_.mi = MouseInput(int(rel_x), int(rel_y), 0, 0x0001, 0, ctypes.pointer(Aimbot.extra))
                input_obj = Input(ctypes.c_ulong(0), Aimbot.ii_)
                ctypes.windll.user32.SendInput(1, ctypes.byref(input_obj), ctypes.sizeof(input_obj))
            case 'colorbot':
                ctypes.windll.user32.mouse_event(0x0001, int(rel_x), int(rel_y), 0, 0)
            case 'arduino':
                if Aimbot.arduino_mouse and not Aimbot.arduino_mouse.move(int(rel_x), int(rel_y)):
                    ctypes.windll.user32.mouse_event(0x0001, int(rel_x), int(rel_y), 0, 0)
            case 'makcu':
                if Aimbot.makcu:
                    Aimbot.makcu.move(int(rel_x), int(rel_y))

    def _apply_humanize(self, dx, dy):
        """Apply humanize: optional delay, jitter, then optionally split into smoothed steps. Returns (dx, dy) possibly modified."""
        delay_min = getattr(Aimbot, "humanize_delay_min", 0)
        delay_max = getattr(Aimbot, "humanize_delay_max", 0)
        if delay_max > 0 or delay_min > 0:
            ms = random.randint(max(0, delay_min), max(delay_min, delay_max))
            Aimbot.sleep(ms / 1000.0)
        jitter = getattr(Aimbot, "humanize_jitter", 0)
        if jitter > 0:
            dx += random.uniform(-jitter, jitter)
            dy += random.uniform(-jitter, jitter)
        smoothing = getattr(Aimbot, "humanize_smoothing", 0)
        if smoothing > 0 and (abs(dx) > 0.5 or abs(dy) > 0.5):
            steps = max(2, int(4 / (1.0 - smoothing + 0.01)))
            step_x, step_y = dx / steps, dy / steps
            for _ in range(steps):
                self._do_move(step_x, step_y)
                Aimbot.sleep(0.005)
            return
        self._do_move(dx, dy)

    def move_crosshair(self, x, y):
        # Debug: reset move result; move_crosshair will set _debug_move_dx/_dy or _debug_move_skipped
        setattr(Aimbot, "_debug_move_dx", None)
        setattr(Aimbot, "_debug_move_dy", None)
        setattr(Aimbot, "_debug_move_skipped", None)
        # normal: only move when user holds an aim key; target_hold/hold_release: we simulate the hold
        if Aimbot.aim_method == "normal" and not Aimbot._any_aim_key_held():
            Aimbot._debug_move_skipped = "aim_key_not_held"
            return
        mode = getattr(Aimbot, "movement_mode", "proportional")
        if mode == "proportional":
            base_speed = getattr(Aimbot, "aim_speed", 0.35)
            error = math.dist((x, y), (screen_x, screen_y))
            lock_th = getattr(Aimbot, "lock_threshold", 18)
            # Unified speed curve: no hitbox dependency. Fastest at mid-range,
            # gentle close (precision) and capped far (prevent overshoot on flickery detection).
            if error <= lock_th:
                # Very close: half speed for precision (prevents jitter around aim point)
                effective_speed = base_speed * 0.5
            elif error <= lock_th * 3:
                # Mid range: ramp from 70% to full — this is the "tracking" zone
                t = (error - lock_th) / (lock_th * 2)
                effective_speed = base_speed * (0.70 + 0.30 * t)
            else:
                # Far range: cap at 65% — cautious approach, detection is unreliable at distance
                # Coast + prediction will carry through gaps, no need to rush
                effective_speed = base_speed * 0.65
            Aimbot._tracking_locked = error <= lock_th
            x_scale = getattr(Aimbot, "aim_speed_x_scale", 1.0)
            y_scale = getattr(Aimbot, "aim_speed_y_scale", 1.0)
            dx = (x - screen_x) * effective_speed * x_scale
            dy = (y - screen_y) * effective_speed * y_scale
            max_step = getattr(Aimbot, "proportional_max_step", 80)
            dx = max(-max_step, min(max_step, dx))
            dy = max(-max_step, min(max_step, dy))
            if abs(dx) < 0.5 and abs(dy) < 0.5:
                Aimbot._debug_move_skipped = "dead_zone"
                return
            Aimbot._debug_move_dx = dx
            Aimbot._debug_move_dy = dy
            self._apply_humanize(dx, dy)
            return
        # Interpolate mode (original)
        scale = Aimbot.sens_config["targeting_scale"]
        max_steps = getattr(Aimbot, "max_move_per_frame", 35)
        for step, (rel_x, rel_y) in enumerate(Aimbot.interpolate_coordinates_from_center((x, y), scale)):
            if step >= max_steps:
                break
            self._do_move(rel_x, rel_y)
            Aimbot.sleep(self.mouse_delay)

    #generator yields pixel tuples for relative movement
    def interpolate_coordinates_from_center(absolute_coordinates, scale):
        diff_x = (absolute_coordinates[0] - screen_x) * scale/Aimbot.pixel_increment
        diff_y = (absolute_coordinates[1] - screen_y) * scale/Aimbot.pixel_increment
        length = int(math.dist((0,0), (diff_x, diff_y)))
        if length == 0: return
        unit_x = (diff_x/length) * Aimbot.pixel_increment
        unit_y = (diff_y/length) * Aimbot.pixel_increment
        x = y = sum_x = sum_y = 0
        for k in range(0, length):
            sum_x += x
            sum_y += y
            x, y = round(unit_x * k - sum_x), round(unit_y * k - sum_y)
            yield x, y
            

    def start(self):
        print("[INFO] Beginning screen capture")
        Aimbot.screen = mss.mss()  # create in this thread so grab() works (mss uses thread-local handles)
        # Don't call update_status_aimbot() here — it toggles state and would start with aimbot DISABLED
        sys.stdout.write("\033[K")
        print(f"[!] AIMBOT IS [{Aimbot.aimbot_status}]", end="\r")
        half_screen_width = ctypes.windll.user32.GetSystemMetrics(0) / 2
        half_screen_height = ctypes.windll.user32.GetSystemMetrics(1) / 2
        frame_count = 0

        def _reload_aim_config():
            try:
                with open(_get_config_path(), "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                aim_keys_new = []
                for j in range(1, 4):
                    v = str(cfg.get(f"aimkey{j}", "0x02" if j == 1 else "none")).strip().lower()
                    if v and v != "none":
                        try:
                            aim_keys_new.append(int(v, 16))
                        except ValueError:
                            pass
                Aimbot.aim_keys = aim_keys_new  # always update (even if empty)
                m = (cfg.get("aim_method") or "normal").strip().lower()
                if m in ("normal", "hold_release", "target_hold"):
                    Aimbot.aim_method = m
                Aimbot.hold_duration = float(cfg.get("hold_duration", 2.0))
                try:
                    Aimbot.fov_mode = (cfg.get("fov_mode") or "hitbox").strip().lower()
                    if Aimbot.fov_mode not in ("hitbox", "radius"):
                        Aimbot.fov_mode = "hitbox"
                except Exception:
                    Aimbot.fov_mode = "hitbox"
                try:
                    Aimbot.hitbox_margin = max(0, int(cfg.get("hitbox_margin", 0)))
                except Exception:
                    Aimbot.hitbox_margin = 0
                try:
                    r = int(cfg.get("fov_radius", 150))
                    Aimbot.fov_radius = max(0, r)
                except Exception:
                    Aimbot.fov_radius = 150
                try:
                    Aimbot.lock_threshold = max(1, int(cfg.get("lock_threshold", 18)))
                except Exception:
                    Aimbot.lock_threshold = 18
                try:
                    Aimbot.trigger_cooldown = max(0.04, float(cfg.get("trigger_cooldown", 0.07)))
                except Exception:
                    Aimbot.trigger_cooldown = 0.07
                try:
                    Aimbot.max_move_per_frame = max(5, int(cfg.get("max_move_per_frame", 35)))
                except Exception:
                    Aimbot.max_move_per_frame = 35
                try:
                    Aimbot.inference_size = max(224, min(640, int(cfg.get("inference_size", 320))))
                except Exception:
                    Aimbot.inference_size = 320
                try:
                    Aimbot.capture_size = max(192, min(480, int(cfg.get("capture_size", 256))))
                except Exception:
                    Aimbot.capture_size = 256
                try:
                    Aimbot.device = (cfg.get("device") or "cuda").strip().lower()
                    if Aimbot.device not in ("cuda", "cpu"):
                        Aimbot.device = "cuda" if torch.cuda.is_available() else "cpu"
                except Exception:
                    Aimbot.device = "cuda" if torch.cuda.is_available() else "cpu"
                try:
                    Aimbot.target_smoothing = max(0.0, min(1.0, float(cfg.get("target_smoothing", 0.5))))
                except Exception:
                    Aimbot.target_smoothing = 0.5
                try:
                    Aimbot.stick_radius = max(20, int(cfg.get("stick_radius", 70)))
                except Exception:
                    Aimbot.stick_radius = 70
                try:
                    Aimbot.coast_frames = max(0, int(cfg.get("coast_frames", 8)))
                except Exception:
                    Aimbot.coast_frames = 8
                try:
                    Aimbot.prediction_factor = max(0.0, min(1.0, float(cfg.get("prediction_factor", 0.4))))
                except Exception:
                    Aimbot.prediction_factor = 0.4
                try:
                    Aimbot.detection_buffer_size = max(1, min(15, int(cfg.get("detection_buffer_size", 5))))
                except Exception:
                    Aimbot.detection_buffer_size = 5
                try:
                    Aimbot.movement_mode = (cfg.get("movement_mode") or "proportional").strip().lower()
                    if Aimbot.movement_mode not in ("interpolate", "proportional"):
                        Aimbot.movement_mode = "proportional"
                except Exception:
                    Aimbot.movement_mode = "proportional"
                try:
                    Aimbot.aim_speed = max(0.05, min(1.0, float(cfg.get("aim_speed", 0.35))))
                except Exception:
                    Aimbot.aim_speed = 0.35
                try:
                    Aimbot.aim_speed_x_scale = max(0.2, min(3.0, float(cfg.get("aim_speed_x_scale", 1.0))))
                except Exception:
                    Aimbot.aim_speed_x_scale = 1.0
                try:
                    Aimbot.aim_speed_y_scale = max(0.2, min(3.0, float(cfg.get("aim_speed_y_scale", 1.0))))
                except Exception:
                    Aimbot.aim_speed_y_scale = 1.0
                try:
                    Aimbot.proportional_max_step = max(10, int(cfg.get("proportional_max_step", 80)))
                except Exception:
                    Aimbot.proportional_max_step = 80
                try:
                    Aimbot.post_trigger_freeze = max(0.0, min(0.2, float(cfg.get("post_trigger_freeze", 0.015))))
                except Exception:
                    Aimbot.post_trigger_freeze = 0.015
                try:
                    Aimbot.humanize_smoothing = max(0.0, min(1.0, float(cfg.get("humanize_smoothing", 0.25))))
                except Exception:
                    Aimbot.humanize_smoothing = 0.25
                try:
                    Aimbot.humanize_delay_min = max(0, int(cfg.get("humanize_delay_min", 0)))
                    Aimbot.humanize_delay_max = max(0, int(cfg.get("humanize_delay_max", 0)))
                    Aimbot.humanize_jitter = max(0.0, float(cfg.get("humanize_jitter", 0.0)))
                except Exception:
                    Aimbot.humanize_delay_min = Aimbot.humanize_delay_max = 0
                    Aimbot.humanize_jitter = 0.0
                try:
                    Aimbot.target_mode = (cfg.get("target_mode") or "closest_to_center").strip().lower()
                    if Aimbot.target_mode not in ("closest_to_center", "topmost"):
                        Aimbot.target_mode = "closest_to_center"
                except Exception:
                    Aimbot.target_mode = "closest_to_center"
                try:
                    Aimbot.aim_offset = max(0.0, min(1.0, float(cfg.get("aim_offset", 0.08))))
                except Exception:
                    Aimbot.aim_offset = 0.08
                try:
                    Aimbot.conf = max(0.1, min(1.0, float(cfg.get("detection_confidence", 0.45))))
                except Exception:
                    Aimbot.conf = 0.45
            except Exception:
                pass

        # Tracking state: smoothed position and stick-to-one-target
        smoothed_abs_x = smoothed_abs_y = None
        last_target_abs_x = last_target_abs_y = None
        frames_without_target = 0
        last_aim_log_x = last_aim_log_y = None  # for stick debug when target is lost
        # Velocity prediction state
        prev_raw_x = prev_raw_y = None  # previous frame raw detection (for velocity calc)
        vel_x = vel_y = 0.0  # smoothed velocity (px/frame)
        vel_alpha = 0.3  # EMA factor for velocity updates
        # Median buffer for raw detection (kills jitter outliers)
        detection_buffer_x = []
        detection_buffer_y = []
        # Coast state: predicted aim when detection drops
        coast_aim_x = coast_aim_y = None
        coast_started = False

        while True:
            start_time = time.perf_counter()
            has_target_this_frame = False
            frame_count += 1
            if getattr(Aimbot, "request_config_reload", False):
                Aimbot.request_config_reload = False
                _reload_aim_config()
            elif frame_count % 60 == 0:
                _reload_aim_config()
            # Use capture_size (default 256) for faster grab + inference when game is running
            box_size = getattr(Aimbot, "capture_size", 256)
            detection_box = {
                "left": int(half_screen_width - box_size // 2),
                "top": int(half_screen_height - box_size // 2),
                "width": box_size,
                "height": box_size,
            }
            initial_frame = Aimbot.screen.grab(detection_box)
            frame = np.array(initial_frame, dtype=np.uint8)
            if frame is None or frame.size == 0:
                continue
            frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
            imgsz = getattr(Aimbot, "inference_size", 320)
            device = getattr(Aimbot, "device", "cuda")
            half = device != "cpu"  # CPU doesn't support FP16
            conf = getattr(Aimbot, "conf", 0.45)  # detection confidence (lower = less strict, more detections)
            boxes = self.model.predict(source=frame, verbose=False, conf=conf, iou=self.iou, half=half, imgsz=imgsz, device=device)
            result = boxes[0]
            if len(result.boxes.xyxy) != 0:  # player detected
                stick_r = getattr(Aimbot, "stick_radius", 70)
                crosshair_cx, crosshair_cy = box_size / 2, box_size / 2
                candidates = []
                for box in result.boxes.xyxy:
                    x1, y1, x2, y2 = map(int, box)
                    x1y1, x2y2 = (x1, y1), (x2, y2)
                    height = y2 - y1
                    relative_head_X = int((x1 + x2) / 2)
                    aim_off = getattr(Aimbot, "aim_offset", 0.08)
                    relative_head_Y = int(y1 + height * aim_off)
                    own_player = x1 < 15 or (x1 < box_size / 5 and y2 > box_size / 1.2)
                    if own_player:
                        continue
                    crosshair_dist = math.dist((relative_head_X, relative_head_Y), (crosshair_cx, crosshair_cy))
                    abs_x = relative_head_X + detection_box["left"]
                    abs_y = relative_head_Y + detection_box["top"]
                    candidates.append({
                        "x1y1": x1y1, "x2y2": x2y2,
                        "relative_head_X": relative_head_X, "relative_head_Y": relative_head_Y,
                        "absolute_head_X": abs_x, "absolute_head_Y": abs_y,
                        "crosshair_dist": crosshair_dist,
                    })

                # Hard-lock to one target: only consider detections near the last target, refuse to switch until truly lost
                closest_detection = None
                switched_target = False
                if candidates:
                    if last_target_abs_x is not None and frames_without_target < 15:
                        nearby = [c for c in candidates if math.dist(
                            (c["absolute_head_X"], c["absolute_head_Y"]),
                            (last_target_abs_x, last_target_abs_y)
                        ) <= stick_r]
                        if nearby:
                            closest_detection = min(nearby, key=lambda c: math.dist(
                                (c["absolute_head_X"], c["absolute_head_Y"]),
                                (last_target_abs_x, last_target_abs_y)
                            ))
                    if closest_detection is None:
                        if last_target_abs_x is not None and frames_without_target < 3:
                            pass
                        else:
                            switched_target = True
                            target_mode = getattr(Aimbot, "target_mode", "closest_to_center")
                            if target_mode == "topmost":
                                closest_detection = min(candidates, key=lambda c: c["relative_head_Y"])
                            else:
                                closest_detection = min(candidates, key=lambda c: c["crosshair_dist"])

                if closest_detection:
                    has_target_this_frame = True
                    frames_without_target = 0
                    coast_started = False
                    # Target hitbox in screen coords (compute first so we can clamp aim and state inside it)
                    bx1, by1 = closest_detection["x1y1"]
                    bx2, by2 = closest_detection["x2y2"]
                    box_left = detection_box["left"] + bx1
                    box_right = detection_box["left"] + bx2
                    box_top = detection_box["top"] + by1
                    box_bottom = detection_box["top"] + by2
                    # Draw hitbox (target's detection bounding box)
                    pt1, pt2 = closest_detection["x1y1"], closest_detection["x2y2"]
                    cv2.rectangle(frame, pt1, pt2, (115, 244, 113), 2)
                    cv2.circle(frame, (closest_detection["relative_head_X"], closest_detection["relative_head_Y"]), 5, (115, 244, 113), -1)
                    cv2.line(frame, (closest_detection["relative_head_X"], closest_detection["relative_head_Y"]), (box_size // 2, box_size // 2), (244, 242, 113), 2)

                    absolute_head_X = closest_detection["absolute_head_X"]
                    absolute_head_Y = closest_detection["absolute_head_Y"]
                    # Keep aim and smoothed state inside hitbox so crosshair never drifts outside
                    absolute_head_X = max(box_left, min(box_right, absolute_head_X))
                    absolute_head_Y = max(box_top, min(box_bottom, absolute_head_Y))

                    # --- Median buffer: feed raw detection into buffer, use median to kill jitter ---
                    buf_size = getattr(Aimbot, "detection_buffer_size", 5)
                    if switched_target:
                        detection_buffer_x.clear()
                        detection_buffer_y.clear()
                    detection_buffer_x.append(absolute_head_X)
                    detection_buffer_y.append(absolute_head_Y)
                    if len(detection_buffer_x) > buf_size:
                        detection_buffer_x.pop(0)
                        detection_buffer_y.pop(0)
                    if len(detection_buffer_x) >= 3:
                        filtered_x = float(sorted(detection_buffer_x)[len(detection_buffer_x) // 2])
                        filtered_y = float(sorted(detection_buffer_y)[len(detection_buffer_y) // 2])
                    else:
                        filtered_x, filtered_y = float(absolute_head_X), float(absolute_head_Y)

                    # --- Velocity tracking: compute movement per frame for prediction ---
                    if prev_raw_x is not None and not switched_target:
                        inst_vx = filtered_x - prev_raw_x
                        inst_vy = filtered_y - prev_raw_y
                        vel_x = vel_alpha * inst_vx + (1.0 - vel_alpha) * vel_x
                        vel_y = vel_alpha * inst_vy + (1.0 - vel_alpha) * vel_y
                    else:
                        vel_x = vel_y = 0.0
                    prev_raw_x, prev_raw_y = filtered_x, filtered_y

                    # Smooth position to reduce jitter (smoothing=1 would freeze tracking; treat as 0 = instant follow)
                    smoothing = getattr(Aimbot, "target_smoothing", 0.5)
                    smoothing = min(0.99, max(0.0, float(smoothing)))
                    # Distance-based smoothing: less smoothing when close (responsive tracking),
                    # more smoothing when far (filters jitter during approach)
                    error_from_center = math.dist((filtered_x, filtered_y), (screen_x, screen_y))
                    lock_th_sm = getattr(Aimbot, "lock_threshold", 18)
                    if error_from_center <= lock_th_sm:
                        smoothing *= 0.50  # Close to target: responsive
                    elif error_from_center <= lock_th_sm * 4:
                        t = (error_from_center - lock_th_sm) / (lock_th_sm * 3)
                        smoothing *= (0.50 + 0.50 * t)  # Ramp from 50% to 100% of base smoothing
                    # else: full smoothing for far targets (jitter filtering)
                    alpha = 1.0 - smoothing
                    if switched_target or smoothed_abs_x is None:
                        smoothed_abs_x, smoothed_abs_y = filtered_x, filtered_y
                        Aimbot._tracking_locked = False
                    else:
                        smoothed_abs_x = alpha * filtered_x + (1.0 - alpha) * smoothed_abs_x
                        smoothed_abs_y = alpha * filtered_y + (1.0 - alpha) * smoothed_abs_y
                    # Store RAW detection position for stick comparison (smoothed lags and breaks stick radius)
                    last_target_abs_x, last_target_abs_y = absolute_head_X, absolute_head_Y
                    aim_x = smoothed_abs_x
                    aim_y = smoothed_abs_y
                    # Save coast prediction: current aim + velocity for when detection drops
                    coast_aim_x = aim_x
                    coast_aim_y = aim_y
                    last_aim_log_x, last_aim_log_y = aim_x, aim_y
                    x1, y1 = closest_detection["x1y1"]
                    # Crosshair inside green hitbox? Only then allow tracking (and trigger / aim key)
                    crosshair_in_hitbox = box_left <= screen_x <= box_right and box_top <= screen_y <= box_bottom
                    Aimbot._crosshair_in_hitbox = crosshair_in_hitbox
                    # Lock: crosshair must be within lock_threshold of aim point before trigger fires
                    lock_th = getattr(Aimbot, "lock_threshold", 18)
                    aim_dist = math.dist((aim_x, aim_y), (screen_x, screen_y))
                    locked = crosshair_in_hitbox and aim_dist <= lock_th
                    # Draw trigger radius circle at crosshair: green=locked (will fire), red=still aiming
                    trigger_color = (115, 244, 113) if locked else (113, 113, 244)
                    cv2.circle(frame, (box_size // 2, box_size // 2), lock_th, trigger_color, 1)
                    rmb_held = Aimbot.is_targeted()
                    lmb_held = Aimbot.is_shooting()
                    aimbot_on = Aimbot.is_aimbot_enabled()

                    # Aim method: target_hold = simulate aim keys only when crosshair is inside the hitbox
                    if aimbot_on and Aimbot.aim_keys:
                        if Aimbot.aim_method == "target_hold":
                            if crosshair_in_hitbox:
                                if not Aimbot._target_hold_keys_pressed:
                                    Aimbot._keybd_aim_keys_down()
                                    Aimbot._target_hold_keys_pressed = True
                            else:
                                if Aimbot._target_hold_keys_pressed:
                                    Aimbot._keybd_aim_keys_up()
                                    Aimbot._target_hold_keys_pressed = False
                        elif Aimbot.aim_method == "hold_release":
                            now_t = time.perf_counter()
                            if Aimbot.hold_start_time is None and Aimbot._any_aim_key_held():
                                Aimbot.hold_start_time = now_t
                                Aimbot._keybd_aim_keys_down()
                            if Aimbot.hold_start_time is not None:
                                if now_t - Aimbot.hold_start_time >= Aimbot.hold_duration:
                                    Aimbot._keybd_aim_keys_up()
                                    time.sleep(0.05)
                                    Aimbot._keybd_aim_keys_down()
                                    Aimbot.hold_start_time = now_t

                    if locked:
                        now = time.perf_counter()
                        # Don't block trigger when we're simulating LMB for aim (target_hold/hold_release with aimkey=LMB)
                        block_trigger = lmb_held
                        if Aimbot.aim_method in ("target_hold", "hold_release") and 0x01 in Aimbot.aim_keys:
                            block_trigger = False
                        if use_trigger_bot and not block_trigger and (now - Aimbot.last_trigger_time) >= Aimbot.trigger_cooldown:
                            self.left_click()
                            Aimbot.last_trigger_time = now
                            did_trigger_click = True
                        else:
                            did_trigger_click = False
                        cv2.putText(frame, "LOCKED", (x1 + 40, y1), cv2.FONT_HERSHEY_DUPLEX, 0.5, (115, 244, 113), 2) #draw the confidence labels on the bounding boxes
                    else:
                        did_trigger_click = False
                        cv2.putText(frame, "TARGETING", (x1 + 40, y1), cv2.FONT_HERSHEY_DUPLEX, 0.5, (115, 113, 244), 2) #draw the confidence labels on the bounding boxes

                    # Move crosshair toward target whenever we have one (so we can acquire from distance and follow when close)
                    # Skip movement briefly after firing so we don't fight recoil or chase muzzle-flash jitter
                    freeze = getattr(Aimbot, "post_trigger_freeze", 0.015)
                    just_fired = (time.perf_counter() - Aimbot.last_trigger_time) < freeze
                    dist_to_aim = math.dist((screen_x, screen_y), (aim_x, aim_y))
                    stick_r = getattr(Aimbot, "stick_radius", 70)
                    following_same_target = dist_to_aim <= stick_r
                    # Allow move whenever target locked and not just_fired (fix: was only when in_hitbox or following, so we never moved when dist>stick_r)
                    will_move = aimbot_on and not just_fired
                    if will_move:
                        Aimbot.move_crosshair(self, aim_x, aim_y)
                    did_move = aimbot_on and (rmb_held or (Aimbot.aim_method != "normal" and has_target_this_frame))

                    # Detailed stick debug: mouse vs target, why crosshair sticks or not, why it goes away
                    if TRIGGER_DEBUG:
                        if not will_move:
                            if not aimbot_on:
                                reason_no_move = "aimbot_off"
                            elif just_fired:
                                reason_no_move = "just_fired(post_trigger_freeze)"
                            else:
                                reason_no_move = "unknown"
                        else:
                            reason_no_move = ""
                        cursor_pos = None
                        try:
                            cursor_pos = win32api.GetCursorPos()
                        except Exception:
                            pass
                        move_dx = getattr(Aimbot, "_debug_move_dx", None)
                        move_dy = getattr(Aimbot, "_debug_move_dy", None)
                        move_skipped_reason = getattr(Aimbot, "_debug_move_skipped", None)
                        _debug_stick_log(
                            screen_x, screen_y, aim_x, aim_y, dist_to_aim, stick_r,
                            crosshair_in_hitbox, following_same_target, just_fired, aimbot_on, will_move,
                            reason_no_move, box_left, box_right, box_top, box_bottom,
                            cursor_pos=cursor_pos, move_dx=move_dx, move_dy=move_dy,
                            move_skipped_reason=move_skipped_reason, switched_target=switched_target, locked=locked,
                        )
                        # On-screen stick debug overlay
                        y_line = 58
                        line_h = 16
                        cv2.putText(frame, "STICK DEBUG", (5, y_line), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 0), 1)
                        y_line += line_h
                        cv2.putText(frame, f"crosshair=({screen_x},{screen_y}) aim=({aim_x:.0f},{aim_y:.0f})", (5, y_line), cv2.FONT_HERSHEY_SIMPLEX, 0.35, (200, 200, 200), 1)
                        y_line += line_h
                        cv2.putText(frame, f"dist={dist_to_aim:.0f} stick_r={stick_r} in_box={int(crosshair_in_hitbox)} follow={int(following_same_target)}", (5, y_line), cv2.FONT_HERSHEY_SIMPLEX, 0.35, (200, 200, 200), 1)
                        y_line += line_h
                        cv2.putText(frame, f"just_fired={int(just_fired)} aimbot_on={int(aimbot_on)} WILL_MOVE={int(will_move)}", (5, y_line), cv2.FONT_HERSHEY_SIMPLEX, 0.35, (0, 255, 0) if will_move else (0, 0, 255), 1)
                        y_line += line_h
                        if reason_no_move:
                            cv2.putText(frame, f"REASON: {reason_no_move}", (5, y_line), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 165, 255), 1)
                        if cursor_pos is not None:
                            y_line += line_h
                            cv2.putText(frame, f"cursor=({cursor_pos[0]},{cursor_pos[1]}) vs aim=({aim_x:.0f},{aim_y:.0f})", (5, y_line), cv2.FONT_HERSHEY_SIMPLEX, 0.35, (200, 200, 200), 1)
                        if move_skipped_reason:
                            y_line += line_h
                            cv2.putText(frame, f"move_skipped={move_skipped_reason}", (5, y_line), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 165, 255), 1)

                    _debug_trigger_log(has_target=True, locked=locked, rmb_held=rmb_held, lmb_held=lmb_held, aimbot_on=aimbot_on, did_move=did_move, did_trigger_click=did_trigger_click)

            if not has_target_this_frame:
                Aimbot._crosshair_in_hitbox = False
                frames_without_target += 1

                # --- Coast mode: continue aiming toward predicted position during brief detection gaps ---
                max_coast = getattr(Aimbot, "coast_frames", 8)
                pred_factor = getattr(Aimbot, "prediction_factor", 0.4)
                if frames_without_target <= max_coast and coast_aim_x is not None and Aimbot.is_aimbot_enabled():
                    # Predict position using velocity
                    coast_aim_x += vel_x * pred_factor
                    coast_aim_y += vel_y * pred_factor
                    # Decay velocity during coast so we slow down prediction
                    vel_x *= 0.85
                    vel_y *= 0.85
                    # Move toward predicted position (with reduced speed for safety)
                    freeze = getattr(Aimbot, "post_trigger_freeze", 0.015)
                    just_fired_coast = (time.perf_counter() - Aimbot.last_trigger_time) < freeze
                    if not just_fired_coast:
                        Aimbot.move_crosshair(self, coast_aim_x, coast_aim_y)
                    # Update smoothed state so when detection resumes, there's no jump
                    smoothed_abs_x, smoothed_abs_y = coast_aim_x, coast_aim_y
                    last_aim_log_x, last_aim_log_y = coast_aim_x, coast_aim_y
                    if not coast_started:
                        coast_started = True
                    if TRIGGER_DEBUG:
                        _debug_stick_log_target_lost(frames_without_target, last_aim_log_x, last_aim_log_y)
                else:
                    if TRIGGER_DEBUG:
                        _debug_stick_log_target_lost(frames_without_target, last_aim_log_x, last_aim_log_y)
                    # Coast expired: reset everything
                    if frames_without_target >= max(15, max_coast + 5):
                        last_target_abs_x, last_target_abs_y = None, None
                        smoothed_abs_x, smoothed_abs_y = None, None
                        coast_aim_x, coast_aim_y = None, None
                        prev_raw_x, prev_raw_y = None, None
                        vel_x = vel_y = 0.0
                        detection_buffer_x.clear()
                        detection_buffer_y.clear()
                        Aimbot._tracking_locked = False
                        coast_started = False
                if Aimbot.aim_method == "target_hold" and Aimbot._target_hold_keys_pressed:
                    # Only release aim keys if coast is also done
                    if frames_without_target > max_coast:
                        Aimbot._keybd_aim_keys_up()
                        Aimbot._target_hold_keys_pressed = False
                if Aimbot.aim_method == "hold_release" and Aimbot.hold_start_time is not None and not Aimbot._any_aim_key_held():
                    Aimbot._keybd_aim_keys_up()
                    Aimbot.hold_start_time = None

            # Periodic key-state log when no target (so you can verify LMB/RMB are seen)
            if TRIGGER_DEBUG:
                _debug_trigger_log(has_target=False, locked=False, rmb_held=Aimbot.is_targeted(), lmb_held=Aimbot.is_shooting(), aimbot_on=Aimbot.is_aimbot_enabled(), did_move=False, did_trigger_click=False)

            # Draw crosshair at center and lock_threshold circle so user always sees trigger zone
            cx, cy = box_size // 2, box_size // 2
            cv2.line(frame, (cx - 8, cy), (cx + 8, cy), (255, 255, 255), 1)
            cv2.line(frame, (cx, cy - 8), (cx, cy + 8), (255, 255, 255), 1)
            lock_th_draw = getattr(Aimbot, "lock_threshold", 18)
            cv2.circle(frame, (cx, cy), lock_th_draw, (180, 180, 180), 1)
            cv2.putText(frame, f"FPS: {int(1/(time.perf_counter() - start_time))}", (5, 30), cv2.FONT_HERSHEY_DUPLEX, 1, (113, 116, 244), 2)
            cv2.imshow("Screen Capture", frame)
            # Keep preview on top so it's not hidden behind the GUI (Lunar LITE controls)
            try:
                cv2.setWindowProperty("Screen Capture", cv2.WND_PROP_TOPMOST, 1)
            except Exception:
                pass
            if cv2.waitKey(1) & 0xFF == ord('0'):
                break

    def clean_up():
        print("\n[INFO] F2 WAS PRESSED. QUITTING...")
        try:
            Aimbot.screen.close()
        except (AttributeError, Exception):
            pass  # mss uses thread-local handles; close() from listener thread can fail
        os._exit(0)

if __name__ == "__main__": print("You are in the wrong directory and are running the wrong file; you must run lunar.py")
