"""Watches the clipboard and saves new copies into the history."""
import hashlib
import io
import time
import traceback

import autotag
import config
import settings
import store
import winclip


def log_error(message):
    """Writes errors to log.txt. Never writes the contents of a clip."""
    try:
        config.DATA_DIR.mkdir(parents=True, exist_ok=True)
        with open(config.LOG_FILE, "a", encoding="utf-8") as file:
            file.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {message}\n")
    except OSError:
        pass


def should_skip_text(text):
    if not text.strip() or len(text) > config.MAX_CHARS:
        return True
    return any(pattern.search(text) for pattern in config.SKIP_PATTERNS)


def save_image(image, source=""):
    """Saves a PIL image as PNG in the images folder and records it. Returns True if saved."""
    if image.width * image.height > 40_000_000:
        return False
    digest = hashlib.sha1(image.tobytes() + str(image.size).encode()).hexdigest()
    filename = digest + ".png"
    path = config.IMAGE_DIR / filename
    if not path.exists():
        image.convert("RGBA").save(path, "PNG")
    store.add_clip("image", filename, digest, source)
    return True


def handle_change():
    """Reads the clipboard once and saves it. Returns True if the history changed,
    False if nothing was saved, or None if the clipboard could not be read (try again)."""
    snapshot = winclip.read_snapshot()
    if snapshot is None:
        return None
    if settings.get("paused") or snapshot["excluded"] or snapshot["owner"] in settings.ignored_apps():
        return False
    source = snapshot["owner"]

    text = snapshot["text"]
    if text is not None:
        if should_skip_text(text):
            return False
        store.add_text(text, source, autotag.tag_name(text))
        return True

    if snapshot["image"]:
        from PIL import BmpImagePlugin
        try:
            image = BmpImagePlugin.DibImageFile(io.BytesIO(snapshot["image"]))
            image.load()
        except (OSError, ValueError, SyntaxError):
            return False   # a picture Pillow cannot read: skip it rather than stop watching
        return save_image(image, source)
    if snapshot["files"]:  # copied files: keep their paths as text
        paths = "\n".join(snapshot["files"])
        if not should_skip_text(paths):
            store.add_text(paths, source)
            return True
    return False


def run(on_change):
    """Loop forever (run in a thread). Calls on_change() whenever the history changed."""
    last_seen = None
    while True:
        number = winclip.sequence_number()
        if number != last_seen:
            try:
                result = handle_change()
            except Exception:
                log_error(traceback.format_exc(limit=3))
                result = False
            if result is not None:  # None means "busy, try again on the next round"
                last_seen = number
            if result:
                on_change()
        time.sleep(config.POLL_SECONDS)
