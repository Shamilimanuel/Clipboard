"""Fixed settings: file locations and rules that rarely change.

Everything you can change from the window (hotkey, theme, sizes, ignored apps) lives in the
Settings tab and is saved by settings.py. This file holds the defaults and the technical rules.
"""
import os
import re
from pathlib import Path

# ---------- where things are stored (never in this folder) ----------
DATA_DIR = Path(os.environ.get("CLIPBOARD_DATA_DIR")
                or Path(os.environ.get("APPDATA", Path.home())) / "Clipboard")
DB_FILE = DATA_DIR / "history.db"
SETTINGS_FILE = DATA_DIR / "settings.json"
IMAGE_DIR = DATA_DIR / "images"
LOG_FILE = DATA_DIR / "log.txt"   # errors only, never the contents of your clips

# ---------- behaviour ----------
MAX_CHARS = 200_000       # longer texts are ignored
POLL_SECONDS = 0.25       # how often we look for a new copy
LIST_LIMIT = 300          # how many clips the window can scroll through
THUMB_SIZE = (56, 36)     # image thumbnail size in a row

# Apps whose copies are never recorded (password managers). More can be added in Settings.
IGNORED_APPS = {"keepass.exe", "keepassxc.exe", "bitwarden.exe", "1password.exe",
                "lastpass.exe", "enpass.exe", "dashlane.exe", "nordpass.exe"}

# Texts that match any of these are never recorded.
SKIP_PATTERNS = [
    re.compile(r"\b(ltoken_v2|ltuid_v2|ltmid_v2|ltoken|ltuid|cookie_token)\b", re.I),  # HoYoLAB cookies
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
]

# Starter tags: (name, colour). Edit freely; new names are added next start.
DEFAULT_TAGS = [("Work", "#8ff3ff"), ("Code", "#4eb1b1"), ("Links", "#ffc857"),
                ("Personal", "#ff8fb1")]
