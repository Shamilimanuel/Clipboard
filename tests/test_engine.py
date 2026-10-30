"""Tests for everything without a window: settings, the history database, text tools, auto-sorting, the watcher.

Run with:  python tests\\run_all.py        (it uses a throwaway data folder)
"""
import io
import os
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
assert "clipboardtest" in os.environ.get("CLIPBOARD_DATA_DIR", ""), "run through tests\\run_all.py"

import autotag, config, settings, store, texttools, watcher, winclip

# ---- settings ----
settings.load()
assert settings.get("look") == "raised" and settings.get("animations") is True and settings.get("paused") is False
assert settings.hotkey_parts(settings.get("hotkey"))[2] == "Ctrl+Alt+V"
config.DATA_DIR.mkdir(parents=True, exist_ok=True)
config.SETTINGS_FILE.write_text('{"look": "nonsense", "multi_separator": "x", "hotkey": {"key": ""}, "max_clips": 1}',
                                encoding="utf-8")
settings.load()
assert settings.get("look") == "raised" and settings.get("multi_separator") == "newline"
assert settings.get("max_clips") == 50, "numbers are held inside their limits"
assert settings.hotkey_parts(settings.get("hotkey"))[2] == "Ctrl+Alt+V", "a damaged hotkey falls back"
settings.set("max_clips", 1000)
print("settings OK")

# ---- an old history file (before 'source' existed) is upgraded, not lost ----
old = sqlite3.connect(config.DB_FILE)
old.executescript("""CREATE TABLE tags (id INTEGER PRIMARY KEY, name TEXT UNIQUE NOT NULL, color TEXT NOT NULL);
CREATE TABLE clips (id INTEGER PRIMARY KEY, kind TEXT NOT NULL DEFAULT 'text', content TEXT NOT NULL,
  hash TEXT NOT NULL UNIQUE, created REAL NOT NULL, pinned INTEGER NOT NULL DEFAULT 0,
  tag_id INTEGER REFERENCES tags(id) ON DELETE SET NULL, uses INTEGER NOT NULL DEFAULT 0);
INSERT INTO clips (content, hash, created) VALUES ('from before', 'abc', 1.0);""")
old.commit()
old.close()
store.init()
assert [c["content"] for c in store.list_clips()] == ["from before"] and store.list_clips()[0]["source"] == ""
print("upgrade OK")

# ---- the history ----
first = store.add_text("alpha one", "chrome.exe")
second = store.add_text("beta two", "code.exe")
assert store.add_text("alpha one") == first, "the same text is the same clip"
assert [c["content"] for c in store.list_clips()][:2] == ["alpha one", "beta two"], "a re-copy moves it to the top"
assert store.get_clip(first)["source"] == "chrome.exe", "a re-copy with no app keeps the old app"
store.add_text("alpha one", "notepad.exe")
assert store.get_clip(first)["source"] == "notepad.exe"
assert [c["content"] for c in store.list_clips("code.exe")] == ["beta two"], "you can search by app"
assert [c["content"] for c in store.list_clips("beta")] == ["beta two"]
assert store.list_clips("100%") == [] and store.list_clips("a_b") == [], "% and _ are not wildcards"
store.toggle_pin(second)
assert store.list_clips()[0]["id"] == second, "pinned clips come first"
assert second not in [c["id"] for c in store.list_clips(unpinned_only=True)], "the All tab leaves pinned clips out"
assert [c["id"] for c in store.list_clips(pinned_only=True)] == [second], "they live in the Pinned tab"
print("history OK")

# ---- tags: make, rename, recolour, delete ----
names = [t["name"] for t in store.list_tags()]
assert names == ["Work", "Code", "Links", "Personal"]
assert store.add_tag("Ideas", "#abcdef") and not store.add_tag("Ideas", "#000000") and not store.add_tag("  ", "#000000")
ideas = [t for t in store.list_tags() if t["name"] == "Ideas"][0]["id"]
assert not store.add_tag("ideas", "#000000"), "tag names are not case sensitive"
assert store.rename_tag(ideas, "Thoughts") and not store.rename_tag(ideas, "Work") and not store.rename_tag(ideas, " ")
store.recolor_tag(ideas, "#111111")
assert [t["color"] for t in store.list_tags() if t["id"] == ideas] == ["#111111"]
store.set_tag(first, ideas)
store.delete_tag(ideas)
assert store.get_clip(first)["tag_id"] is None, "a deleted tag leaves its clips, untagged"
assert "Thoughts" not in [t["name"] for t in store.list_tags()]
print("tags OK")

# ---- a tag is only given to a NEW clip ----
new = store.add_text("https://example.com", "chrome.exe", "Links")
assert store.get_clip(new)["tag_id"] == [t["id"] for t in store.list_tags() if t["name"] == "Links"][0]
store.set_tag(new, None)
store.add_text("https://example.com", "chrome.exe", "Links")
assert store.get_clip(new)["tag_id"] is None, "a clip you untagged is not tagged again"
assert store.get_clip(store.add_text("tagless", "", "No such tag"))["tag_id"] is None
print("tag rule OK")

# ---- text tools ----
assert texttools.apply("upper", "ab c") == "AB C" and texttools.apply("lower", "AB C") == "ab c"
assert texttools.apply("title", "it's a TEST of hello-world") == "It's A Test Of Hello-World"
assert texttools.apply("trim", "  a  \n  b \n\n") == "a\nb"
assert texttools.apply("oneline", "a\n  b\r\n c") == "a b c"
assert texttools.apply("sort", "b\nA\nc") == "A\nb\nc"
assert texttools.apply("links", "see https://x.com/p?a=1&utm_source=z&fbclid=9#top. ok") == "see https://x.com/p?a=1#top. ok"
assert texttools.apply("links", "https://x.com/?utm_a=1") == "https://x.com/"
assert texttools.apply("links", "no links here") == "no links here"
assert texttools.apply("nothing", "same") == "same"
print("text tools OK")

# ---- auto-sorting ----
assert autotag.looks_like_links("https://a.com\nwww.b.org") and not autotag.looks_like_links("see https://a.com")
assert autotag.looks_like_code("const x = 5;") and autotag.looks_like_code("def f(x):\n    return x\n")
assert not autotag.looks_like_code("Hello (world), how are you today?") and not autotag.looks_like_code('print("hi")')
settings.load()
assert autotag.tag_name("https://example.com") == "Links" and autotag.tag_name("const x = 5;") == "Code"
assert autotag.tag_name("just words") is None
settings.set("auto_tag_links", "")
assert autotag.tag_name("https://example.com") is None, "a rule set to Off does nothing"
settings.set("auto_tag_links", "Links")
print("auto-sort OK")

# ---- the watcher (the clipboard is replaced by a recorder; the real one is never read) ----
snapshot = {"text": "https://example.com/new", "image": None, "files": None, "excluded": False, "owner": "chrome.exe"}
winclip.read_snapshot = lambda: dict(snapshot)
assert watcher.handle_change() is True
saved = [c for c in store.list_clips() if c["content"] == "https://example.com/new"][0]
assert saved["source"] == "chrome.exe" and saved["tag_name"] == "Links"
snapshot["text"] = "def go():\n    return 1\n"
assert watcher.handle_change() is True
assert [c for c in store.list_clips() if c["content"].startswith("def go")][0]["tag_name"] == "Code"
before = len(store.list_clips())
settings.set("paused", True)
snapshot["text"] = "copied while paused"
assert watcher.handle_change() is False and len(store.list_clips()) == before, "paused: nothing is saved"
settings.set("paused", False)
snapshot["excluded"] = True
assert watcher.handle_change() is False, "a password manager's copy is skipped"
snapshot["excluded"] = False
snapshot["text"] = "my ltoken_v2=abc"
assert watcher.handle_change() is False, "cookie names are never stored"
snapshot["text"] = "now it is saved"
assert watcher.handle_change() is True
# a picture arrives as DIB bytes (a BMP file without its 14-byte file header); copied files as a list of paths
from PIL import Image as _Image
_bmp = io.BytesIO()
_Image.new("RGB", (7, 5), (10, 200, 180)).save(_bmp, "BMP")
snapshot.update(text=None, image=_bmp.getvalue()[14:])
assert watcher.handle_change() is True and store.list_clips(unpinned_only=True)[0]["kind"] == "image", "a picture is saved"
snapshot["image"] = b"\x28" + b"\x00" * 50
assert watcher.handle_change() is False, "a broken picture is skipped, the watcher keeps going"
snapshot.update(image=None, files=["C:\\a.txt", "C:\\b.txt"])
assert watcher.handle_change() is True and store.list_clips(unpinned_only=True)[0]["content"] == "C:\\a.txt\nC:\\b.txt", "copied files keep their paths"
snapshot["files"] = None
print("watcher OK")
# ---- the Screenshots tab's filter, and emptying the whole history ----
config.IMAGE_DIR.mkdir(parents=True, exist_ok=True)
(config.IMAGE_DIR / "shot1.png").write_bytes(b"fake")
(config.IMAGE_DIR / "shot2.png").write_bytes(b"fake")
store.add_text("a note to keep", "notepad.exe")
store.toggle_pin(store.add_clip("image", "shot1.png", "h1", "snipper.exe"))
store.add_clip("image", "shot2.png", "h2", "snippingtool.exe")
only_images = store.list_clips(kind="image")
assert only_images and all(c["kind"] == "image" for c in only_images), "the Screenshots tab shows pictures only"
assert len(store.list_clips(kind="image")) < len(store.list_clips()), "text clips are left out of it"
gone = store.delete_all(keep_pinned=True)
assert gone >= 1 and not (config.IMAGE_DIR / "shot2.png").exists(), "an unpinned picture's file is removed too"
left = store.list_clips()
assert left and all(c["pinned"] for c in left) and (config.IMAGE_DIR / "shot1.png").exists(), "pinned clips survive 'Delete all unpinned'"
assert store.delete_all() == len(left) and store.list_clips() == [] and not (config.IMAGE_DIR / "shot1.png").exists()
assert store.delete_all() == 0, "emptying an empty history is harmless"
print("delete all OK")
print("all engine tests passed")
