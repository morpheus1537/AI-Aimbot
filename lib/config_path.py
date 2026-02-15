"""
Single source of truth for config file path so GUI and aimbot always use the same file.
"""
import os

# Path to lib/config/config.json (next to this package)
_CONFIG_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(_CONFIG_DIR, "config", "config.json")
