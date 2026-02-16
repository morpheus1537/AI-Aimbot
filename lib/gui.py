"""
Lunar LITE - Control panel GUI.
Shows key bindings, aim settings (ColorBot-style), and aimbot status.
"""
import json
import os
import tkinter as tk
from tkinter import font as tkfont
from tkinter import ttk
from tkinter import messagebox

# Use same path as aimbot (single source of truth so saves go to the right file)
try:
    from lib.config_path import CONFIG_PATH
except ImportError:
    CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config", "config.json")


def _load_config():
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_config(updates):
    """Save updates to config.json. Returns True on success, False and shows error on failure."""
    try:
        cfg = _load_config()
        cfg.update(updates)
        os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
        return True
    except Exception as e:
        messagebox.showerror("Config save failed", f"Could not save to:\n{CONFIG_PATH}\n\n{e}")
        return False


def _save_config_and_reload(updates):
    """Save config and ask aimbot to reload on next frame. Returns True on success, False on failure."""
    if not _save_config(updates):
        return False
    try:
        from lib.aimbot import Aimbot
        Aimbot.request_config_reload = True
    except Exception:
        pass
    return True


def _vk_hex_to_name(hex_str):
    """Convert virtual key hex (e.g. 0x02) to display name."""
    h = (hex_str or "0x02").strip().lower()
    if h == "none" or h == "0x00":
        return "None"
    if h.startswith("0x"):
        h = h[2:]
    try:
        vk = int(h, 16)
    except ValueError:
        return "Key ?"
    names = {
        0x01: "Left Mouse",
        0x02: "Right Mouse",
        0x04: "Middle Mouse",
        0x05: "X1",
        0x06: "X2",
        0x08: "Backspace",
        0x09: "Tab",
        0x0D: "Enter",
        0x10: "Shift",
        0x11: "Ctrl",
        0x12: "Alt",
        0x14: "Caps Lock",
        0x1B: "Escape",
        0x20: "Space",
        0x21: "Page Up",
        0x22: "Page Down",
        0x23: "End",
        0x24: "Home",
        0x25: "Left",
        0x26: "Up",
        0x27: "Right",
        0x28: "Down",
        0x2C: "Print Screen",
        0x2D: "Insert",
        0x2E: "Delete",
        0x30: "0", 0x31: "1", 0x32: "2", 0x33: "3", 0x34: "4",
        0x35: "5", 0x36: "6", 0x37: "7", 0x38: "8", 0x39: "9",
        0x41: "A", 0x42: "B", 0x43: "C", 0x44: "D", 0x45: "E",
        0x46: "F", 0x47: "G", 0x48: "H", 0x49: "I", 0x4A: "J",
        0x4B: "K", 0x4C: "L", 0x4D: "M", 0x4E: "N", 0x4F: "O",
        0x50: "P", 0x51: "Q", 0x52: "R", 0x53: "S", 0x54: "T",
        0x55: "U", 0x56: "V", 0x57: "W", 0x58: "X", 0x59: "Y", 0x5A: "Z",
        0x70: "F1", 0x71: "F2", 0x72: "F3", 0x73: "F4", 0x74: "F5",
        0x75: "F6", 0x76: "F7", 0x77: "F8", 0x78: "F9", 0x79: "F10",
        0x7A: "F11", 0x7B: "F12",
    }
    return names.get(vk, "Key 0x%02X" % vk)


def run_gui():
    root = tk.Tk()
    root.title("Lunar LITE - Controls")
    root.resizable(False, False)
    root.configure(bg="#1a1a2e")

    # Prevent closing from triggering full exit if we use protocol later
    def on_closing():
        try:
            os._exit(0)
        except Exception:
            root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_closing)

    main_font = tkfont.nametofont("TkDefaultFont")
    main_font.configure(size=10)
    title_font = tkfont.Font(family="Segoe UI", size=14, weight="bold")
    key_font = tkfont.Font(family="Consolas", size=11, weight="bold")
    desc_font = tkfont.Font(size=9)

    # Header
    header = tk.Label(
        root,
        text="Lunar LITE — Key Bindings",
        font=title_font,
        fg="#e94560",
        bg="#1a1a2e",
    )
    header.pack(pady=(14, 8))
    tk.Label(
        root,
        text="Preview: \"Screen Capture\" window (detection view) — keep it visible or check behind this window.",
        font=desc_font,
        fg="#888",
        bg="#1a1a2e",
    ).pack(pady=(0, 6))

    # Key bindings frame
    keys_frame = tk.Frame(root, bg="#1a1a2e", padx=20, pady=4)
    keys_frame.pack(fill="x")

    bindings = [
        ("DEL", "Toggle Aimbot on/off (ColorBot-style)"),
        ("F2", "Quit"),
        ("Right Mouse Button", "Hold to aim — aimbot moves crosshair while holding"),
        ("Left Mouse Button", "Fire — triggerbot auto-fires when crosshair is locked on target"),
    ]

    for key_name, description in bindings:
        row = tk.Frame(keys_frame, bg="#1a1a2e")
        row.pack(fill="x", pady=3)
        key_label = tk.Label(
            row,
            text=key_name + "  ",
            font=key_font,
            fg="#0f3460",
            bg="#e94560",
            padx=6,
            pady=2,
        )
        key_label.pack(side="left")
        desc_label = tk.Label(
            row,
            text=description,
            font=desc_font,
            fg="#eaeaea",
            bg="#1a1a2e",
            anchor="w",
        )
        desc_label.pack(side="left", fill="x", expand=True)

    # Save config button at top (always visible)
    def on_save_config_top():
        if not _save_config_and_reload(_reload_payload()):
            return
        save_btn_top.config(text="Saved!")
        root.after(1500, lambda: save_btn_top.config(text="Save config"))
    save_btn_top = ttk.Button(root, text="Save config", width=14, command=on_save_config_top)
    save_btn_top.pack(pady=(8, 12))

    # Aim settings (ColorBot-style)
    aim_frame = tk.LabelFrame(root, text=" Aim method ", font=title_font, fg="#e94560", bg="#1a1a2e")
    aim_frame.pack(fill="x", padx=20, pady=(12, 6))

    cfg = _load_config()
    aim_method_var = tk.StringVar(value=cfg.get("aim_method", "normal"))
    hold_duration_var = tk.StringVar(value=str(cfg.get("hold_duration", 2.0)))
    fov_mode_var = tk.StringVar(value=(cfg.get("fov_mode") or "hitbox").strip().lower())
    hitbox_margin_var = tk.StringVar(value=str(cfg.get("hitbox_margin", 0)))
    fov_radius_var = tk.StringVar(value=str(cfg.get("fov_radius", 150)))
    lock_threshold_var = tk.StringVar(value=str(cfg.get("lock_threshold", 18)))
    trigger_cooldown_var = tk.StringVar(value=str(cfg.get("trigger_cooldown", 0.07)))
    max_move_per_frame_var = tk.StringVar(value=str(cfg.get("max_move_per_frame", 35)))
    inference_size_var = tk.StringVar(value=str(cfg.get("inference_size", 320)))
    capture_size_var = tk.StringVar(value=str(cfg.get("capture_size", 256)))
    device_var = tk.StringVar(value=str(cfg.get("device", "cuda")).lower())
    detection_confidence_var = tk.StringVar(value=str(cfg.get("detection_confidence", 0.45)))
    target_smoothing_var = tk.StringVar(value=str(cfg.get("target_smoothing", 0.5)))
    stick_radius_var = tk.StringVar(value=str(cfg.get("stick_radius", 70)))
    coast_frames_var = tk.StringVar(value=str(cfg.get("coast_frames", 8)))
    prediction_factor_var = tk.StringVar(value=str(cfg.get("prediction_factor", 0.4)))
    detection_buffer_size_var = tk.StringVar(value=str(cfg.get("detection_buffer_size", 5)))
    movement_mode_var = tk.StringVar(value=str(cfg.get("movement_mode", "proportional")).lower())
    aim_speed_var = tk.StringVar(value=str(cfg.get("aim_speed", 0.35)))
    aim_speed_x_scale_var = tk.StringVar(value=str(cfg.get("aim_speed_x_scale", 1.0)))
    aim_speed_y_scale_var = tk.StringVar(value=str(cfg.get("aim_speed_y_scale", 1.0)))
    proportional_max_step_var = tk.StringVar(value=str(cfg.get("proportional_max_step", 80)))
    target_mode_var = tk.StringVar(value=str(cfg.get("target_mode", "closest_to_center")).lower())
    aim_offset_var = tk.StringVar(value=str(cfg.get("aim_offset", 0.08)))
    humanize_smoothing_var = tk.StringVar(value=str(cfg.get("humanize_smoothing", 0.25)))
    humanize_delay_min_var = tk.StringVar(value=str(cfg.get("humanize_delay_min", 0)))
    humanize_delay_max_var = tk.StringVar(value=str(cfg.get("humanize_delay_max", 0)))
    humanize_jitter_var = tk.StringVar(value=str(cfg.get("humanize_jitter", 0)))

    ttk.Style().configure("TFrame", background="#1a1a2e")
    row1 = tk.Frame(aim_frame, bg="#1a1a2e")
    row1.pack(fill="x", pady=4, padx=10)
    tk.Label(row1, text="Aim method:", font=desc_font, fg="#eaeaea", bg="#1a1a2e", width=14, anchor="w").pack(side="left")
    aim_combo = ttk.Combobox(row1, textvariable=aim_method_var, values=("normal", "hold_release", "target_hold"), state="readonly", width=14)
    aim_combo.pack(side="left", padx=(0, 12))

    row2 = tk.Frame(aim_frame, bg="#1a1a2e")
    row2.pack(fill="x", pady=4, padx=10)
    tk.Label(row2, text="Hold duration (s):", font=desc_font, fg="#eaeaea", bg="#1a1a2e", width=14, anchor="w").pack(side="left")
    hold_entry = ttk.Entry(row2, textvariable=hold_duration_var, width=8)
    hold_entry.pack(side="left", padx=(0, 8))
    tk.Label(row2, text="Hold Release only", font=desc_font, fg="#888", bg="#1a1a2e").pack(side="left")

    row_fov_mode = tk.Frame(aim_frame, bg="#1a1a2e")
    row_fov_mode.pack(fill="x", pady=4, padx=10)
    tk.Label(row_fov_mode, text="FOV mode:", font=desc_font, fg="#eaeaea", bg="#1a1a2e", width=14, anchor="w").pack(side="left")
    fov_mode_combo = ttk.Combobox(row_fov_mode, textvariable=fov_mode_var, values=("hitbox", "radius"), state="readonly", width=10)
    fov_mode_combo.pack(side="left", padx=(0, 12))
    tk.Label(row_fov_mode, text="Hitbox = target box is FOV; Radius = circle from crosshair", font=desc_font, fg="#888", bg="#1a1a2e").pack(side="left")

    row_hitbox_margin = tk.Frame(aim_frame, bg="#1a1a2e")
    row_hitbox_margin.pack(fill="x", pady=4, padx=10)
    tk.Label(row_hitbox_margin, text="Hitbox margin (px):", font=desc_font, fg="#eaeaea", bg="#1a1a2e", width=14, anchor="w").pack(side="left")
    hitbox_margin_entry = ttk.Entry(row_hitbox_margin, textvariable=hitbox_margin_var, width=8)
    hitbox_margin_entry.pack(side="left", padx=(0, 8))
    tk.Label(row_hitbox_margin, text="Expand target box for FOV (Hitbox mode); 0 = exact box", font=desc_font, fg="#888", bg="#1a1a2e").pack(side="left")

    row_fov = tk.Frame(aim_frame, bg="#1a1a2e")
    row_fov.pack(fill="x", pady=4, padx=10)
    tk.Label(row_fov, text="FOV radius (px):", font=desc_font, fg="#eaeaea", bg="#1a1a2e", width=14, anchor="w").pack(side="left")
    fov_entry = ttk.Entry(row_fov, textvariable=fov_radius_var, width=8)
    fov_entry.pack(side="left", padx=(0, 8))
    tk.Label(row_fov, text="Used when FOV = Radius; 0 = no limit", font=desc_font, fg="#888", bg="#1a1a2e").pack(side="left")

    row_lock = tk.Frame(aim_frame, bg="#1a1a2e")
    row_lock.pack(fill="x", pady=4, padx=10)
    tk.Label(row_lock, text="Lock threshold (px):", font=desc_font, fg="#eaeaea", bg="#1a1a2e", width=14, anchor="w").pack(side="left")
    lock_entry = ttk.Entry(row_lock, textvariable=lock_threshold_var, width=8)
    lock_entry.pack(side="left", padx=(0, 8))
    tk.Label(row_lock, text="Higher = fire sooner when near target (e.g. 18–25)", font=desc_font, fg="#888", bg="#1a1a2e").pack(side="left")

    row_trigger_cd = tk.Frame(aim_frame, bg="#1a1a2e")
    row_trigger_cd.pack(fill="x", pady=4, padx=10)
    tk.Label(row_trigger_cd, text="Trigger cooldown (s):", font=desc_font, fg="#eaeaea", bg="#1a1a2e", width=14, anchor="w").pack(side="left")
    trigger_cooldown_entry = ttk.Entry(row_trigger_cd, textvariable=trigger_cooldown_var, width=8)
    trigger_cooldown_entry.pack(side="left", padx=(0, 8))
    tk.Label(row_trigger_cd, text="Lower = faster response (e.g. 0.05–0.07)", font=desc_font, fg="#888", bg="#1a1a2e").pack(side="left")

    row_max_move = tk.Frame(aim_frame, bg="#1a1a2e")
    row_max_move.pack(fill="x", pady=4, padx=10)
    tk.Label(row_max_move, text="Max move/frame:", font=desc_font, fg="#eaeaea", bg="#1a1a2e", width=14, anchor="w").pack(side="left")
    max_move_entry = ttk.Entry(row_max_move, textvariable=max_move_per_frame_var, width=8)
    max_move_entry.pack(side="left", padx=(0, 8))
    tk.Label(row_max_move, text="Lower = smoother stick; higher = faster snap (default 35)", font=desc_font, fg="#888", bg="#1a1a2e").pack(side="left")

    row_inference = tk.Frame(aim_frame, bg="#1a1a2e")
    row_inference.pack(fill="x", pady=4, padx=10)
    tk.Label(row_inference, text="Inference size:", font=desc_font, fg="#eaeaea", bg="#1a1a2e", width=14, anchor="w").pack(side="left")
    inference_entry = ttk.Entry(row_inference, textvariable=inference_size_var, width=8)
    inference_entry.pack(side="left", padx=(0, 8))
    tk.Label(row_inference, text="Lower = higher FPS when game is running (e.g. 320); 224–640", font=desc_font, fg="#888", bg="#1a1a2e").pack(side="left")

    row_capture = tk.Frame(aim_frame, bg="#1a1a2e")
    row_capture.pack(fill="x", pady=4, padx=10)
    tk.Label(row_capture, text="Capture size (px):", font=desc_font, fg="#eaeaea", bg="#1a1a2e", width=14, anchor="w").pack(side="left")
    capture_entry = ttk.Entry(row_capture, textvariable=capture_size_var, width=8)
    capture_entry.pack(side="left", padx=(0, 8))
    tk.Label(row_capture, text="Smaller = faster in-game (e.g. 256); 192–480", font=desc_font, fg="#888", bg="#1a1a2e").pack(side="left")

    row_device = tk.Frame(aim_frame, bg="#1a1a2e")
    row_device.pack(fill="x", pady=4, padx=10)
    tk.Label(row_device, text="Device:", font=desc_font, fg="#eaeaea", bg="#1a1a2e", width=14, anchor="w").pack(side="left")
    device_combo = ttk.Combobox(row_device, textvariable=device_var, values=("cuda", "cpu"), state="readonly", width=8)
    device_combo.pack(side="left", padx=(0, 8))
    tk.Label(row_device, text="Use CPU if FPS is 1 in-game (avoids GPU conflict)", font=desc_font, fg="#888", bg="#1a1a2e").pack(side="left")

    row_det_conf = tk.Frame(aim_frame, bg="#1a1a2e")
    row_det_conf.pack(fill="x", pady=4, padx=10)
    tk.Label(row_det_conf, text="Detection confidence:", font=desc_font, fg="#eaeaea", bg="#1a1a2e", width=14, anchor="w").pack(side="left")
    detection_confidence_entry = ttk.Entry(row_det_conf, textvariable=detection_confidence_var, width=8)
    detection_confidence_entry.pack(side="left", padx=(0, 8))
    tk.Label(row_det_conf, text="0.1–1.0; lower = less strict, more detections (e.g. 0.35)", font=desc_font, fg="#888", bg="#1a1a2e").pack(side="left")

    row_smoothing = tk.Frame(aim_frame, bg="#1a1a2e")
    row_smoothing.pack(fill="x", pady=4, padx=10)
    tk.Label(row_smoothing, text="Target smoothing:", font=desc_font, fg="#eaeaea", bg="#1a1a2e", width=14, anchor="w").pack(side="left")
    smoothing_entry = ttk.Entry(row_smoothing, textvariable=target_smoothing_var, width=8)
    smoothing_entry.pack(side="left", padx=(0, 8))
    tk.Label(row_smoothing, text="0=raw, 0.5=balanced, 1=max (smoother tracking)", font=desc_font, fg="#888", bg="#1a1a2e").pack(side="left")

    row_stick = tk.Frame(aim_frame, bg="#1a1a2e")
    row_stick.pack(fill="x", pady=4, padx=10)
    tk.Label(row_stick, text="Stick radius (px):", font=desc_font, fg="#eaeaea", bg="#1a1a2e", width=14, anchor="w").pack(side="left")
    stick_entry = ttk.Entry(row_stick, textvariable=stick_radius_var, width=8)
    stick_entry.pack(side="left", padx=(0, 8))
    tk.Label(row_stick, text="Stick to one target; higher = less switching (e.g. 70)", font=desc_font, fg="#888", bg="#1a1a2e").pack(side="left")

    row_coast = tk.Frame(aim_frame, bg="#1a1a2e")
    row_coast.pack(fill="x", pady=4, padx=10)
    tk.Label(row_coast, text="Coast frames:", font=desc_font, fg="#eaeaea", bg="#1a1a2e", width=14, anchor="w").pack(side="left")
    coast_entry = ttk.Entry(row_coast, textvariable=coast_frames_var, width=8)
    coast_entry.pack(side="left", padx=(0, 8))
    tk.Label(row_coast, text="Keep aiming N frames after detection drops (bridges gaps; 0=off, 5-12 good)", font=desc_font, fg="#888", bg="#1a1a2e").pack(side="left")

    row_pred = tk.Frame(aim_frame, bg="#1a1a2e")
    row_pred.pack(fill="x", pady=4, padx=10)
    tk.Label(row_pred, text="Prediction factor:", font=desc_font, fg="#eaeaea", bg="#1a1a2e", width=14, anchor="w").pack(side="left")
    prediction_entry = ttk.Entry(row_pred, textvariable=prediction_factor_var, width=8)
    prediction_entry.pack(side="left", padx=(0, 8))
    tk.Label(row_pred, text="Velocity prediction during coast (0=none, 0.3-0.5=good, 1=full)", font=desc_font, fg="#888", bg="#1a1a2e").pack(side="left")

    row_detbuf = tk.Frame(aim_frame, bg="#1a1a2e")
    row_detbuf.pack(fill="x", pady=4, padx=10)
    tk.Label(row_detbuf, text="Detection buffer:", font=desc_font, fg="#eaeaea", bg="#1a1a2e", width=14, anchor="w").pack(side="left")
    detbuf_entry = ttk.Entry(row_detbuf, textvariable=detection_buffer_size_var, width=8)
    detbuf_entry.pack(side="left", padx=(0, 8))
    tk.Label(row_detbuf, text="Median filter over N detections (kills jitter; 3-7 good)", font=desc_font, fg="#888", bg="#1a1a2e").pack(side="left")

    # ColorBot-style movement
    move_frame = tk.LabelFrame(root, text=" Movement (ColorBot-style) ", font=title_font, fg="#e94560", bg="#1a1a2e")
    move_frame.pack(fill="x", padx=20, pady=(12, 6))
    row_mmode = tk.Frame(move_frame, bg="#1a1a2e")
    row_mmode.pack(fill="x", pady=4, padx=10)
    tk.Label(row_mmode, text="Movement mode:", font=desc_font, fg="#eaeaea", bg="#1a1a2e", width=14, anchor="w").pack(side="left")
    movement_combo = ttk.Combobox(row_mmode, textvariable=movement_mode_var, values=("proportional", "interpolate"), state="readonly", width=14)
    movement_combo.pack(side="left", padx=(0, 8))
    tk.Label(row_mmode, text="proportional = ColorBot-style (speed × error)", font=desc_font, fg="#888", bg="#1a1a2e").pack(side="left")
    row_aspeed = tk.Frame(move_frame, bg="#1a1a2e")
    row_aspeed.pack(fill="x", pady=4, padx=10)
    tk.Label(row_aspeed, text="Aim speed:", font=desc_font, fg="#eaeaea", bg="#1a1a2e", width=14, anchor="w").pack(side="left")
    ttk.Entry(row_aspeed, textvariable=aim_speed_var, width=8).pack(side="left", padx=(0, 8))
    tk.Label(row_aspeed, text="Proportional: 0.2–0.5 typical", font=desc_font, fg="#888", bg="#1a1a2e").pack(side="left")
    row_xy_scale = tk.Frame(move_frame, bg="#1a1a2e")
    row_xy_scale.pack(fill="x", pady=4, padx=10)
    tk.Label(row_xy_scale, text="X / Y scale:", font=desc_font, fg="#eaeaea", bg="#1a1a2e", width=14, anchor="w").pack(side="left")
    aim_speed_x_scale_entry = ttk.Entry(row_xy_scale, textvariable=aim_speed_x_scale_var, width=6)
    aim_speed_x_scale_entry.pack(side="left", padx=(0, 4))
    aim_speed_y_scale_entry = ttk.Entry(row_xy_scale, textvariable=aim_speed_y_scale_var, width=6)
    aim_speed_y_scale_entry.pack(side="left", padx=(0, 8))
    tk.Label(row_xy_scale, text="1.0 = same both axes; if only vertical tracks, try X=2 or 3", font=desc_font, fg="#888", bg="#1a1a2e").pack(side="left")
    row_pstep = tk.Frame(move_frame, bg="#1a1a2e")
    row_pstep.pack(fill="x", pady=4, padx=10)
    tk.Label(row_pstep, text="Max step (px):", font=desc_font, fg="#eaeaea", bg="#1a1a2e", width=14, anchor="w").pack(side="left")
    ttk.Entry(row_pstep, textvariable=proportional_max_step_var, width=8).pack(side="left", padx=(0, 8))
    tk.Label(row_pstep, text="Cap per frame (proportional)", font=desc_font, fg="#888", bg="#1a1a2e").pack(side="left")
    row_tmode = tk.Frame(move_frame, bg="#1a1a2e")
    row_tmode.pack(fill="x", pady=4, padx=10)
    tk.Label(row_tmode, text="Target mode:", font=desc_font, fg="#eaeaea", bg="#1a1a2e", width=14, anchor="w").pack(side="left")
    target_mode_combo = ttk.Combobox(row_tmode, textvariable=target_mode_var, values=("closest_to_center", "topmost"), state="readonly", width=18)
    target_mode_combo.pack(side="left", padx=(0, 8))
    tk.Label(row_tmode, text="topmost = highest on screen (ColorBot)", font=desc_font, fg="#888", bg="#1a1a2e").pack(side="left")
    row_aim_off = tk.Frame(move_frame, bg="#1a1a2e")
    row_aim_off.pack(fill="x", pady=4, padx=10)
    tk.Label(row_aim_off, text="Aim offset:", font=desc_font, fg="#eaeaea", bg="#1a1a2e", width=14, anchor="w").pack(side="left")
    aim_offset_entry = ttk.Entry(row_aim_off, textvariable=aim_offset_var, width=8)
    aim_offset_entry.pack(side="left", padx=(0, 8))
    tk.Label(row_aim_off, text="0.08=head, 0.0=top of box, 0.5=center, 1.0=feet", font=desc_font, fg="#888", bg="#1a1a2e").pack(side="left")
    row_hu = tk.Frame(move_frame, bg="#1a1a2e")
    row_hu.pack(fill="x", pady=4, padx=10)
    tk.Label(row_hu, text="Humanize:", font=desc_font, fg="#eaeaea", bg="#1a1a2e", width=14, anchor="w").pack(side="left")
    tk.Label(row_hu, text="smooth", font=desc_font, fg="#888", bg="#1a1a2e").pack(side="left")
    ttk.Entry(row_hu, textvariable=humanize_smoothing_var, width=5).pack(side="left", padx=2)
    tk.Label(row_hu, text="delay min-max (ms)", font=desc_font, fg="#888", bg="#1a1a2e").pack(side="left")
    ttk.Entry(row_hu, textvariable=humanize_delay_min_var, width=4).pack(side="left", padx=2)
    ttk.Entry(row_hu, textvariable=humanize_delay_max_var, width=4).pack(side="left", padx=2)
    tk.Label(row_hu, text="jitter", font=desc_font, fg="#888", bg="#1a1a2e").pack(side="left")
    ttk.Entry(row_hu, textvariable=humanize_jitter_var, width=5).pack(side="left", padx=2)

    # Aim keys 1–3: display + Pick (press key to set) + Clear (keys 2 & 3 only)
    MOUSE_NUM_TO_VK = {1: 0x01, 2: 0x04, 3: 0x02, 4: 0x05, 5: 0x06}  # tk Button-1=Left, 2=Middle, 3=Right, 4=X1, 5=X2

    aim_key_btns = []
    aim_key_labels = []

    def set_aim_key(key_index, hex_str):
        key_name = "aimkey%d" % key_index
        _save_config_and_reload({key_name: hex_str})
        lbl = aim_key_labels[key_index - 1]
        lbl.config(text=_vk_hex_to_name(hex_str))

    def on_pick_aim_key(key_index):
        dlg = tk.Toplevel(root)
        dlg.title("Aim key %d" % key_index)
        dlg.geometry("380x100")
        dlg.configure(bg="#1a1a2e")
        tk.Label(
            dlg,
            text="Press any key or click a mouse button for Aim key %d..." % key_index,
            font=desc_font,
            fg="#eaeaea",
            bg="#1a1a2e",
        ).pack(padx=16, pady=16)

        def set_key_and_close(vk_code):
            hex_str = "0x%02X" % (vk_code & 0xFF)
            set_aim_key(key_index, hex_str)
            dlg.destroy()

        def on_key(event):
            set_key_and_close(event.keycode)

        def on_mouse(event):
            vk = MOUSE_NUM_TO_VK.get(event.num)
            if vk is not None:
                set_key_and_close(vk)

        dlg.bind("<Key>", on_key)
        dlg.bind("<Button-1>", on_mouse)
        dlg.bind("<Button-2>", on_mouse)
        dlg.bind("<Button-3>", on_mouse)
        dlg.bind("<Button-4>", on_mouse)
        dlg.bind("<Button-5>", on_mouse)
        dlg.focus_set()
        dlg.grab_set()
        dlg.transient(root)

    def on_clear_aim_key(key_index):
        set_aim_key(key_index, "none")

    for i in range(1, 4):
        row = tk.Frame(aim_frame, bg="#1a1a2e")
        row.pack(fill="x", pady=4, padx=10)
        tk.Label(row, text="Aim key %d:" % i, font=desc_font, fg="#eaeaea", bg="#1a1a2e", width=10, anchor="w").pack(side="left")
        val = cfg.get("aimkey%d" % i, "0x02" if i == 1 else "none")
        lbl = tk.Label(row, text=_vk_hex_to_name(val), font=desc_font, fg="#16c79a", bg="#1a1a2e", width=14, anchor="w")
        lbl.pack(side="left", padx=(0, 8))
        aim_key_labels.append(lbl)
        pick_btn = ttk.Button(row, text="Pick key", width=10, command=lambda idx=i: on_pick_aim_key(idx))
        pick_btn.pack(side="left", padx=(0, 4))
        if i >= 2:
            clear_btn = ttk.Button(row, text="Clear", width=6, command=lambda idx=i: on_clear_aim_key(idx))
            clear_btn.pack(side="left")
        aim_key_btns.append(pick_btn)

    def _fov_mode_str():
        m = (fov_mode_var.get() or "hitbox").strip().lower()
        return m if m in ("hitbox", "radius") else "hitbox"

    def _hitbox_margin_int():
        try:
            return max(0, int(hitbox_margin_var.get().strip() or "0"))
        except ValueError:
            return 0

    def _fov_int():
        try:
            return max(0, int(fov_radius_var.get().strip() or "150"))
        except ValueError:
            return 150

    def _lock_threshold_int():
        try:
            return max(1, int(lock_threshold_var.get().strip() or "18"))
        except ValueError:
            return 18

    def _trigger_cooldown_float():
        try:
            return max(0.04, float(trigger_cooldown_var.get().strip() or "0.07"))
        except ValueError:
            return 0.07

    def _max_move_per_frame_int():
        try:
            return max(5, int(max_move_per_frame_var.get().strip() or "35"))
        except ValueError:
            return 35

    def _inference_size_int():
        try:
            return max(224, min(640, int(inference_size_var.get().strip() or "320")))
        except ValueError:
            return 320

    def _capture_size_int():
        try:
            return max(192, min(480, int(capture_size_var.get().strip() or "256")))
        except ValueError:
            return 256

    def _device_str():
        d = (device_var.get() or "cuda").strip().lower()
        return d if d in ("cuda", "cpu") else "cuda"

    def _detection_confidence_float():
        try:
            return max(0.1, min(1.0, float(detection_confidence_var.get().strip() or "0.45")))
        except ValueError:
            return 0.45

    def _target_smoothing_float():
        try:
            return max(0.0, min(1.0, float(target_smoothing_var.get().strip() or "0.5")))
        except ValueError:
            return 0.5

    def _stick_radius_int():
        try:
            return max(20, int(stick_radius_var.get().strip() or "70"))
        except ValueError:
            return 70

    def _coast_frames_int():
        try:
            return max(0, int(coast_frames_var.get().strip() or "8"))
        except ValueError:
            return 8

    def _prediction_factor_float():
        try:
            return max(0.0, min(1.0, float(prediction_factor_var.get().strip() or "0.4")))
        except ValueError:
            return 0.4

    def _detection_buffer_size_int():
        try:
            return max(1, min(15, int(detection_buffer_size_var.get().strip() or "5")))
        except ValueError:
            return 5

    def _movement_mode_str():
        d = (movement_mode_var.get() or "proportional").strip().lower()
        return d if d in ("interpolate", "proportional") else "proportional"

    def _aim_speed_float():
        try:
            return max(0.05, min(1.0, float(aim_speed_var.get().strip() or "0.35")))
        except ValueError:
            return 0.35

    def _aim_speed_scale_float(var, default=1.0):
        try:
            return max(0.2, min(3.0, float(var.get().strip() or str(default))))
        except ValueError:
            return default

    def _proportional_max_step_int():
        try:
            return max(10, int(proportional_max_step_var.get().strip() or "80"))
        except ValueError:
            return 80

    def _target_mode_str():
        d = (target_mode_var.get() or "closest_to_center").strip().lower()
        return d if d in ("closest_to_center", "topmost") else "closest_to_center"

    def _aim_offset_float():
        try:
            return max(0.0, min(1.0, float(aim_offset_var.get().strip() or "0.08")))
        except ValueError:
            return 0.08

    def _humanize_floats():
        try:
            s = max(0.0, min(1.0, float(humanize_smoothing_var.get().strip() or "0.25")))
        except ValueError:
            s = 0.25
        try:
            dmin = max(0, int(humanize_delay_min_var.get().strip() or "0"))
            dmax = max(0, int(humanize_delay_max_var.get().strip() or "0"))
        except ValueError:
            dmin, dmax = 0, 0
        try:
            j = max(0.0, float(humanize_jitter_var.get().strip() or "0"))
        except ValueError:
            j = 0.0
        return s, dmin, dmax, j

    def _reload_payload():
        s, dmin, dmax, j = _humanize_floats()
        try:
            h = float(hold_duration_var.get().strip() or "2.0")
        except ValueError:
            h = 2.0
        m = (aim_method_var.get() or "normal").strip().lower()
        if m not in ("normal", "hold_release", "target_hold"):
            m = "normal"
        return {
            "aim_method": m,
            "hold_duration": h,
            "fov_mode": _fov_mode_str(),
            "hitbox_margin": _hitbox_margin_int(),
            "fov_radius": _fov_int(),
            "lock_threshold": _lock_threshold_int(), "trigger_cooldown": _trigger_cooldown_float(),
            "max_move_per_frame": _max_move_per_frame_int(), "inference_size": _inference_size_int(),
            "capture_size": _capture_size_int(), "device": _device_str(),
            "detection_confidence": _detection_confidence_float(),
            "target_smoothing": _target_smoothing_float(), "stick_radius": _stick_radius_int(),
            "coast_frames": _coast_frames_int(), "prediction_factor": _prediction_factor_float(),
            "detection_buffer_size": _detection_buffer_size_int(),
            "movement_mode": _movement_mode_str(), "aim_speed": _aim_speed_float(),
            "aim_speed_x_scale": _aim_speed_scale_float(aim_speed_x_scale_var),
            "aim_speed_y_scale": _aim_speed_scale_float(aim_speed_y_scale_var),
            "proportional_max_step": _proportional_max_step_int(), "target_mode": _target_mode_str(),
            "aim_offset": _aim_offset_float(),
            "humanize_smoothing": s, "humanize_delay_min": dmin, "humanize_delay_max": dmax, "humanize_jitter": j,
        }

    def on_aim_change():
        _save_config_and_reload(_reload_payload())

    aim_combo.bind("<<ComboboxSelected>>", lambda e: on_aim_change())
    hold_entry.bind("<FocusOut>", lambda e: on_aim_change())
    fov_mode_combo.bind("<<ComboboxSelected>>", lambda e: on_aim_change())
    hitbox_margin_entry.bind("<FocusOut>", lambda e: on_aim_change())
    fov_entry.bind("<FocusOut>", lambda e: on_aim_change())
    lock_entry.bind("<FocusOut>", lambda e: on_aim_change())
    trigger_cooldown_entry.bind("<FocusOut>", lambda e: on_aim_change())
    max_move_entry.bind("<FocusOut>", lambda e: on_aim_change())
    inference_entry.bind("<FocusOut>", lambda e: on_aim_change())
    capture_entry.bind("<FocusOut>", lambda e: on_aim_change())
    device_combo.bind("<<ComboboxSelected>>", lambda e: on_aim_change())
    detection_confidence_entry.bind("<FocusOut>", lambda e: on_aim_change())
    smoothing_entry.bind("<FocusOut>", lambda e: on_aim_change())
    stick_entry.bind("<FocusOut>", lambda e: on_aim_change())
    coast_entry.bind("<FocusOut>", lambda e: on_aim_change())
    prediction_entry.bind("<FocusOut>", lambda e: on_aim_change())
    detbuf_entry.bind("<FocusOut>", lambda e: on_aim_change())
    movement_combo.bind("<<ComboboxSelected>>", lambda e: on_aim_change())
    aim_speed_x_scale_entry.bind("<FocusOut>", lambda e: on_aim_change())
    aim_speed_y_scale_entry.bind("<FocusOut>", lambda e: on_aim_change())
    target_mode_combo.bind("<<ComboboxSelected>>", lambda e: on_aim_change())
    aim_offset_entry.bind("<FocusOut>", lambda e: on_aim_change())

    # Target hold hint
    hint_row = tk.Frame(aim_frame, bg="#1a1a2e")
    hint_row.pack(fill="x", pady=(2, 6), padx=10)
    tk.Label(
        hint_row,
        text="Target hold: holds aim key automatically while target is detected.",
        font=desc_font,
        fg="#888",
        bg="#1a1a2e",
    ).pack(side="left")

    # Status section + Start/Stop buttons
    status_frame = tk.Frame(root, bg="#1a1a2e", pady=14)
    status_frame.pack(fill="x")

    status_label = tk.Label(
        status_frame,
        text="Aimbot: —",
        font=title_font,
        fg="#eaeaea",
        bg="#1a1a2e",
    )
    status_label.pack(pady=(0, 8))

    btn_frame = tk.Frame(status_frame, bg="#1a1a2e")
    btn_frame.pack()

    def on_start_aimbot():
        try:
            from lib.aimbot import Aimbot
            Aimbot.set_aimbot_enabled(True)
        except Exception:
            pass

    def on_stop_aimbot():
        try:
            from lib.aimbot import Aimbot
            Aimbot.set_aimbot_enabled(False)
        except Exception:
            pass

    start_btn = ttk.Button(btn_frame, text="Start Aimbot", width=14, command=on_start_aimbot)
    start_btn.pack(side="left", padx=(0, 8))
    stop_btn = ttk.Button(btn_frame, text="Stop Aimbot", width=14, command=on_stop_aimbot)
    stop_btn.pack(side="left")

    def update_status():
        try:
            from lib.aimbot import Aimbot
            if getattr(Aimbot, "aimbot_enabled", True):
                status_label.config(text="Aimbot: ENABLED", fg="#16c79a")
            else:
                status_label.config(text="Aimbot: DISABLED", fg="#e94560")
        except Exception:
            status_label.config(text="Aimbot: —", fg="#eaeaea")
        root.after(400, update_status)

    root.after(400, update_status)

    # Padding at bottom
    tk.Frame(root, bg="#1a1a2e", height=12).pack(fill="x")

    root.mainloop()
