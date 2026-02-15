# Arduino hardware mouse (when game blocks software input)

If the game blocks ddxoft/win32/mouse_event, use an **Arduino as a second USB mouse**. The game sees real HID device input.

## 1. Hardware

- **Board:** Leonardo, Micro, or Pro Micro (must support `Mouse` library).
- Connect via USB.

## 2. Flash the sketch

1. Open `arduino_mouse.ino` in Arduino IDE.
2. Select your board (e.g. Arduino Leonardo) and the correct COM port.
3. Upload.

## 3. Config

1. Run `python lunar.py setup` if you haven’t (creates `lib/config/config.json`).
2. Edit `lib/config/config.json` and set:
   - `"mouse_method": "arduino"`
   - `"arduino_port": "COM3"` (use the COM port from Arduino IDE/Device Manager).

Example:

```json
{
  "xy_sens": 4,
  "targeting_sens": 4,
  "xy_scale": 2.5,
  "targeting_scale": 62.5,
  "aim_key": "0x02",
  "mouse_method": "arduino",
  "arduino_port": "COM3"
}
```

## 4. Python

```bash
pip install pyserial
```

Then run `start.bat` or `python lunar.py`. You should see:

`[OK] Mouse input: Arduino (hardware USB) — games usually don't block this`

## Protocol (for custom firmware)

- **Move:** `M,dx,dy\n` (relative, integers).
- **Left click:** `L\n`.
- Baud rate: **115200**.
