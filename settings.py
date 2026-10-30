"""Settings you can change in the Settings tab. Saved as settings.json in the data folder."""
import copy
import json
import os
import re

import config

DEFAULTS = {
    "hotkey": {"ctrl": True, "alt": True, "shift": False, "key": "V"},
    "theme": "teal",                       # teal, dark, light or custom
    "custom_colors": {"bg": "#06141a", "text": "#e6fbfb", "accent": "#8ff3ff", "sel": "#0f3a45"},
    "visible_rows": 12,
    "preview_chars": 56,
    "max_clips": 1000,
    "font_size": 10,
    "extra_ignored_apps": [],              # e.g. ["myvault.exe"]
    "open_at": "mouse",                    # "mouse" = at the pointer, "last" = where you left it
    "window_pos": [],                      # [x, y] saved when you drag the window
    "window_size": [],                     # [width, height] of the list area, saved when you resize
    "hover_preview": True,                 # show the full text when you hover a clip
    "look": "raised",                      # flat, raised or glass: how rows, tabs and buttons are drawn
    "animations": True,                    # fade and glide the window in and out
    "paused": False,                       # True = copies are not saved until you turn recording back on
    "multi_separator": "newline",          # how several picked clips are joined: newline, comma or space
    "auto_tag_links": "Links",             # copied links go into this tag ("" = off)
    "auto_tag_code": "Code",               # copied code goes into this tag ("" = off)
}

LOOKS = [("flat", "Flat"), ("raised", "Raised"), ("glass", "Glass")]
SEPARATORS = {"newline": "\n", "comma": ", ", "space": " "}

LIMITS = {"visible_rows": (5, 2000), "preview_chars": (30, 120), "max_clips": (50, 5000), "font_size": (8, 14)}

_data = None


def _merge(base, saved):
    """Saved values win; anything missing or the wrong type falls back to the default."""
    result = copy.deepcopy(base)
    for key, default in base.items():
        if key not in saved:
            continue
        if isinstance(default, dict) and isinstance(saved[key], dict):
            result[key] = _merge(default, saved[key])
        elif isinstance(saved[key], type(default)):
            result[key] = saved[key]
    return result


def load():
    global _data
    try:
        saved = json.loads(config.SETTINGS_FILE.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        saved = {}
    _data = _merge(DEFAULTS, saved if isinstance(saved, dict) else {})
    for key, (low, high) in LIMITS.items():
        _data[key] = max(low, min(high, _data[key]))
    if _data["look"] not in dict(LOOKS):
        _data["look"] = DEFAULTS["look"]
    if _data["multi_separator"] not in SEPARATORS:
        _data["multi_separator"] = DEFAULTS["multi_separator"]
    try:
        hotkey_parts(_data["hotkey"])
    except (IndexError, ValueError, TypeError):  # a damaged hotkey must not stop the app from starting
        _data["hotkey"] = copy.deepcopy(DEFAULTS["hotkey"])
    return _data


def get(key):
    if _data is None:
        load()
    return _data[key]


def set(key, value):
    if _data is None:
        load()
    _data[key] = value
    save()


def save():
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    temp = config.SETTINGS_FILE.with_suffix(".tmp")
    temp.write_text(json.dumps(_data, indent=2), encoding="utf-8")
    os.replace(temp, config.SETTINGS_FILE)


def reset():
    global _data
    _data = copy.deepcopy(DEFAULTS)
    save()


# ---------- the hotkey as Windows wants it ----------

MOD_ALT, MOD_CONTROL, MOD_SHIFT = 0x0001, 0x0002, 0x0004

# Punctuation keys that can be used in a hotkey -> Windows virtual-key codes.
# (These codes follow your keyboard layout: ` is the key left of 1 on a US keyboard.)
PUNCTUATION_KEYS = {"`": 0xC0, "-": 0xBD, "=": 0xBB, "[": 0xDB, "]": 0xDD, "\\": 0xDC, ";": 0xBA,
                    "'": 0xDE, ",": 0xBC, ".": 0xBE, "/": 0xBF, "Space": 0x20}
# Tk's names for those keys -> the characters above.
KEYSYM_TO_KEY = {"grave": "`", "minus": "-", "equal": "=", "bracketleft": "[", "bracketright": "]",
                 "backslash": "\\", "semicolon": ";", "apostrophe": "'", "quoteright": "'",
                 "comma": ",", "period": ".", "slash": "/", "space": "Space"}


def hotkey_parts(hotkey):
    """Returns (modifier flags, virtual-key code, text like 'Ctrl+Alt+V')."""
    flags, names = 0, []
    if hotkey.get("ctrl"):
        flags |= MOD_CONTROL
        names.append("Ctrl")
    if hotkey.get("alt"):
        flags |= MOD_ALT
        names.append("Alt")
    if hotkey.get("shift"):
        flags |= MOD_SHIFT
        names.append("Shift")
    key = str(hotkey.get("key", "V"))
    if key in PUNCTUATION_KEYS:
        code = PUNCTUATION_KEYS[key]
    else:
        key = key.upper()
        match = re.fullmatch(r"F(\d{1,2})", key)
        if match and 1 <= int(match.group(1)) <= 24:
            code = 0x70 + int(match.group(1)) - 1
        else:
            code = ord(key[0])
    names.append(key)
    return flags, code, "+".join(names)


def ignored_apps():
    # A set literal on purpose: this module defines its own set(), which hides Python's built-in one.
    return {*config.IGNORED_APPS, *(app.lower() for app in get("extra_ignored_apps"))}
