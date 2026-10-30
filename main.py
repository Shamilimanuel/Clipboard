"""Clipboard: a clipboard history widget with themes and settings.

Run with:  pythonw main.py      (no console window)   or   python main.py   (to see errors)
Open the window with the hotkey (default Ctrl+Alt+V; change it in the Settings tab).

How the pieces fit:
  watcher.py   watches the clipboard and saves copies      -> store.py (SQLite history)
  winclip.py   talks to Windows (clipboard, hotkey, paste)
  ui.py        the window, including the Settings tab
  settings.py  your saved choices (settings.json)          themes.py  the colour themes
  config.py    fixed rules and file locations

History and settings are stored in %APPDATA%\\Clipboard, never in this folder.
"""
import ctypes
import queue
import threading
import traceback

import settings
import store
import watcher
import winclip


_instance_lock = None  # keeps the lock alive for as long as the app runs


def another_copy_is_running():
    """Windows lets only one program own a named mutex, so a second copy finds it taken."""
    global _instance_lock
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateMutexW.restype = ctypes.c_void_p
    _instance_lock = kernel32.CreateMutexW(None, False, "Local\\ClipboardTealApp")
    return ctypes.get_last_error() == 183  # ERROR_ALREADY_EXISTS


def main():
    if another_copy_is_running():
        return  # already running (for example it started with Windows): quit quietly
    ctypes.windll.shcore.SetProcessDpiAwareness(1)  # sharp text on scaled displays
    store.init()
    events = queue.Queue()  # threads talk to the window through this, never directly
    threading.Thread(target=watcher.run, args=(lambda: events.put("changed"),), daemon=True).start()

    hotkey = winclip.Hotkey(lambda: events.put("toggle"))
    modifiers, key, text = settings.hotkey_parts(settings.get("hotkey"))
    error = hotkey.start(modifiers, key)
    notice = ""
    if error:
        notice = f"{text} is not available: {error} Pick another one here."
        watcher.log_error(f"hotkey {text}: {error}")

    import ui  # imported late so a Tk problem is reported clearly
    app = ui.App(events, hotkey, notice)
    if error:
        events.put("toggle")  # open once so the problem is visible instead of silent
    app.run()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        watcher.log_error(traceback.format_exc(limit=5))
        raise
