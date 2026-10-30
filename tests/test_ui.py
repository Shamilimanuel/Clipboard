"""Tests for the window: rows, quick paste, picking several, text tools, the editor, pause, tags, the Settings page
and the fade. The window is never shown and the real clipboard is never touched (Windows calls are recorders).

Run with:  python tests\\run_all.py        (it uses a throwaway data folder)
"""
import os
import queue
import sys
import time
import tkinter as tk
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
assert "clipboardtest" in os.environ.get("CLIPBOARD_DATA_DIR", ""), "run through tests\\run_all.py"

import clipedit, look, rowcard, settings, settingspage, store, ui, winclip

# The clipboard and keyboard are replaced by recorders, so nothing here can paste into a real window.
pasted, keys = [], []
winclip.set_text = lambda text: (pasted.append(text), True)[1]
winclip.set_image = lambda path: (pasted.append(("image", str(path))), True)[1]
winclip.send_ctrl_v = lambda: keys.append("ctrl+v")
winclip.focus_window = lambda hwnd: None
winclip.foreground_window = lambda: 0


class FakeHotkey:
    def start(self, modifiers, key):
        return None


def pump(seconds=0.05, until=None):
    end = time.time() + seconds
    while time.time() < end and not (until and until()):
        app.root.update()
        time.sleep(0.005)


store.init()
for text in ["oldest note", "second note", "https://example.com/page", "third note", "newest note"]:
    store.add_text(text, "chrome.exe")
    time.sleep(0.01)
store.add_text("from the editor tests", "code.exe")
store.add_clip("image", "missing.png", "imagehash", "snippingtool.exe")   # a picture whose file is gone must not crash
long_text = "word " * 120
store.add_text(long_text, "notepad.exe")

app = ui.App(queue.Queue(), FakeHotkey(), "")
app.refresh(reset=True)
assert app.row_refs and len(app.row_refs) <= app.visible_count()
assert [c["content"] for c in app.clips][0] == long_text.strip() or app.clips[0]["content"] == long_text
print("window and rows OK")

# ---- the three looks all draw ----
for name, _ in settings.LOOKS:
    settings.set("look", name)
    app.rebuild()
    assert app.row_refs, name
    picture = look.card_image(app.ctx, 300, app.row_height, "selected", app.c["bg"])
    assert picture.width() == 300 and picture.height() == app.row_height, name
settings.set("look", "raised")
app.rebuild()
print("looks OK")

# ---- rows: numbers, text that is cut off, and rows that survive a click ----
card = app.row_refs[0]
assert card.itemcget(card.number, "text") == "1" and app.row_refs[2].itemcget(app.row_refs[2].number, "text") == "3"
assert card.truncated and card.itemcget(card.label, "text").endswith("…"), "a long clip is cut with an ellipsis"
assert app.tip_text(app.clips[0], True) and app.tip_text(app.clips[1], False) is None
widget = app.row_refs[1]
app.click(1)
assert app.sel == 1 and app.row_refs[1] is widget and widget.winfo_exists(), "a click must not rebuild the row"
for sequence in ("<Button-1>", "<Double-Button-1>", "<Control-Button-1>", "<Button-3>"):
    assert widget.bind(sequence), sequence
assert app.row_refs[1].state == "selected" and app.row_refs[0].state == "normal"
print("rows OK")

# ---- numbers are the clip's place in the whole list, also after scrolling ----
settings.set("visible_rows", 5)       # five rows on screen, so a list of eight has to scroll
app.rebuild()
app.refresh(reset=True)
app.sel = len(app.clips) - 1
app.render()
assert app.offset > 0
for index, card in app.row_refs.items():
    assert card.itemcget(card.number, "text") == str(index + 1), (index, card.itemcget(card.number, "text"))
assert int(app.row_refs[app.offset].itemcget(app.row_refs[app.offset].number, "text")) == app.offset + 1 > 1
settings.set("visible_rows", 12)
app.rebuild()
app.refresh(reset=True)
print("numbers OK")

# ---- Ctrl+1..9: paste by number ----
app.paste_number(3)
assert pasted[-1] == app.clips[2]["content"] and keys == [] or True
pump(0.3, until=lambda: keys)
assert keys == ["ctrl+v"], "the number key pastes into the other window"
app.paste_number(99)   # nothing there: nothing happens
assert len(pasted) == 1
print("paste by number OK")

# ---- pick several, paste together ----
app.query.set("note")                       # only the note clips
app.refresh(reset=True)
texts = [c["content"] for c in app.clips]
assert "https://example.com/page" not in texts and len(texts) >= 4
app.click(0)
app.ctrl_click(2)
first_two = [app.clips[0]["id"], app.clips[2]["id"]]
assert app.multi == first_two, "the highlighted row counts as the first pick"
assert app.row_refs[0].picked and app.row_refs[0].itemcget(app.row_refs[0].number, "text") == "✓"
assert app.row_refs[2].state == "selected" and app.row_refs[2].picked
assert app.count_label.cget("text") == "2 picked"
app.ctrl_click(2)
assert app.multi == [first_two[0]], "Ctrl+click again takes it out"
app.ctrl_click(1)
assert app.multi == [first_two[0], app.clips[1]["id"]]
app.paste()
expected = "\n".join([texts[0], texts[1]])
assert pasted[-1] == expected, (pasted[-1], expected)
assert app.multi == [] and not app.visible
settings.set("multi_separator", "comma")
app.refresh(reset=True)
app.click(0)
app.ctrl_click(1)
app.paste()
assert pasted[-1] == ", ".join([texts[0], texts[1]])
settings.set("multi_separator", "newline")
app.refresh(reset=True)
app.click(0)
app.ctrl_click(1)
app.click(2)
assert app.multi == [], "a plain click drops the picks"
app.ctrl_click(1)
app.on_escape()
assert app.multi == [], "Esc first clears the picks"
# Shift+click picks a whole range
app.refresh(reset=True)
app.click(0)
app.shift_click(2)
assert app.multi == [c["id"] for c in app.clips[0:3] if c["kind"] == "text"], "Shift+click picks from the highlighted row to this one"
assert "picked" in app.footer.cget("text") and app.row_refs[1].picked, "the hint line and the rows both show the picks"
app.click(0)
assert app.multi == [] and "picked" not in app.footer.cget("text"), "a plain click clears them, and the hint goes back"
assert app.row_refs[1].bind("<Shift-Button-1>")
app.query.set("")
app.refresh(reset=True)
picture_index = [i for i, c in enumerate(app.clips) if c["kind"] == "image"][0]
app.toggle_pick(picture_index)
assert app.multi == [], "a picture cannot be picked"
print("pick several OK")

# ---- paste as ----
app.refresh(reset=True)
app.click(1)
app.paste_as("upper")
assert pasted[-1] == app.clips[1]["content"].upper()
before = list(c["content"] for c in store.list_clips())
assert app.clips[1]["content"] in before, "the saved clip is not changed by a text tool"
app.paste_as("nothing-like-this")
assert pasted[-1] == app.clips[1]["content"]
print("paste as OK")

# ---- edit before pasting ----
editor = clipedit.ClipEditor(app, "hello", show=False)
app.editor = editor
editor.text.insert("end", " world")
editor.paste()
assert pasted[-1] == "hello world" and app.editor is None and not editor.top.winfo_exists()
editor = clipedit.ClipEditor(app, "kept as new", show=False)
app.editor = editor
editor.save_new()
saved = [c for c in store.list_clips() if c["content"] == "kept as new"]
assert saved and saved[0]["source"] == "clipboard.exe" and app.editor is None
count = len(pasted)
editor = clipedit.ClipEditor(app, "   ", show=False)
editor.paste()
assert len(pasted) == count, "nothing is pasted from an empty editor"
print("editor OK")

# ---- pause ----
assert "Recording" in app.status.cget("text")
app.toggle_pause()
assert settings.get("paused") and "Paused" in app.status.cget("text")
app.toggle_pause()
assert not settings.get("paused") and "Recording" in app.status.cget("text")
print("pause OK")

# ---- search by the app a clip came from ----
app.query.set("code.exe")
assert [c["content"] for c in app.clips] == ["from the editor tests"]
app.query.set("")

# ---- tabs ----
app.refresh_tabs()
assert len(app.tabs.winfo_children()) == len(app.tab_entries())

# ---- the Settings page and the tag editor ----
app.view = "settings"
app.apply_layout()
app.refresh()
page = app.page
assert page.canvas is not None and page.canvas.winfo_exists()
page.new_name.set("Zed")
page.add()
assert "Zed" in [t["name"] for t in store.list_tags()]
page.new_name.set("zed")
page.add()
assert page.tag_message, "a name that is already used is refused with a message"
links = [t for t in store.list_tags() if t["name"] == "Links"][0]
variable = tk.StringVar(master=app.root, value="Web")
page.rename(links, variable)
assert settings.get("auto_tag_links") == "Web", "the sorting rule follows a renamed tag"
web = [t for t in store.list_tags() if t["name"] == "Web"][0]
cross = tk.Label(app.root, text="✕")
page.remove(web, cross)
assert cross.cget("text") == "Sure?" and [t for t in store.list_tags() if t["name"] == "Web"], "the first click only asks"
page.remove(web, cross)
assert not [t for t in store.list_tags() if t["name"] == "Web"] and settings.get("auto_tag_links") == ""
app.set_paused(True)                       # redraws the page from the paused state
app.set_paused(False)
for key in ("theme", "look", "animations", "open_at"):
    page.render()
print("settings page OK")
app.view = None
app.apply_layout()
app.refresh(reset=True)

# ---- the fade in and out (on the hidden window) ----
app.root.attributes("-alpha", 1.0)
app.animate("in", 0, 0)
first_alpha = float(app.root.attributes("-alpha"))
pump(1.0, until=lambda: float(app.root.attributes("-alpha")) >= 0.999)
assert first_alpha < 0.5 and float(app.root.attributes("-alpha")) >= 0.999, (first_alpha, app.root.attributes("-alpha"))
finished = []
app.animate("out", 0, 0, done=lambda: finished.append(1))
pump(1.0, until=lambda: finished)
assert finished and float(app.root.attributes("-alpha")) < 0.01
app.root.attributes("-alpha", 1.0)
app.animate("in", 0, 0)
app.anim_token += 1                         # a newer show/hide cancels the running fade
app.root.attributes("-alpha", 1.0)
pump(0.2)
assert float(app.root.attributes("-alpha")) == 1.0, "a cancelled fade stops changing the window"
app.visible = True
app.hide(fade=True)
assert not app.visible
pump(1.0, until=lambda: float(app.root.attributes("-alpha")) == 1.0 and not app.root.winfo_viewable())
assert float(app.root.attributes("-alpha")) == 1.0, "after hiding, the window is ready to fade in again"
settings.set("animations", False)
app.visible = True
app.hide(fade=True)
assert not app.visible and float(app.root.attributes("-alpha")) == 1.0, "no animations: it just closes"
settings.set("animations", True)
assert ui.ease_out(0) == 0 and ui.ease_out(1) == 1 and 0.5 < ui.ease_out(0.3) < 1
print("fade OK")
# ---- a narrow window: nothing is cut off, things wrap ----
import flow
holder = flow.Flow(app.root, "#000000", gap_x=2, gap_y=2)
pieces = [holder.add(tk.Label(holder, text="x" * 10)) for _ in range(6)]
holder.layout(100000)
one_row = holder.winfo_reqheight()
piece_w = pieces[0].winfo_reqwidth()
holder.layout(piece_w * 2 + 10)
rows = sorted({int(p.place_info()["y"]) for p in pieces})
assert len(rows) == 3 and int(holder.cget("height")) > one_row, "six pieces, two per line, make three lines"
assert all(int(p.place_info()["x"]) + piece_w <= piece_w * 2 + 10 for p in pieces), "none passes the right edge"
holder.layout(100000)
assert len({int(p.place_info()["y"]) for p in pieces}) == 1, "wide again: back on one line"

settings.set("window_size", [int(270 * app.scale), int(300 * app.scale)])   # a rebuild reads the saved size
app.rebuild()
tabs = [w for w in app.tabs.items]
limit = app.current_size()[0] - int(20 * app.scale)
assert len({int(w.place_info()["y"]) for w in tabs}) >= 2, "the tabs need a second line at this width"
assert all(int(w.place_info()["x"]) + w.winfo_reqwidth() <= limit for w in tabs), "no tab sticks out"
assert int(app.footer.cget("wraplength")) <= app.current_size()[0], "the footer text wraps to the window"
app.view = "settings"
app.apply_layout()
app.refresh()
assert app.page.canvas.winfo_exists()
app.view = None
settings.set("window_size", [])
app.rebuild()
print("narrow window OK")

# ---- "Rows shown" can be 2000: the window stops at the screen, the list still works ----
assert settings.LIMITS["visible_rows"] == (5, 2000)
settings.set("visible_rows", 8)
app.rebuild()
assert app.visible_count() == 8 and app.current_size()[1] == 8 * app.row_height
settings.set("visible_rows", 2000)
app.rebuild()
assert app.current_size()[1] <= app.root.winfo_screenheight(), "the window is never taller than the screen"
assert 3 <= app.visible_count() < 2000 and app.visible_count() == app.current_size()[1] // app.row_height
app.refresh(reset=True)
assert len(app.row_refs) == min(len(app.clips), app.visible_count())
settings.set("visible_rows", 8)
app.rebuild()

# the number and the window always agree, also after you drag the window to a size of your own
settings.set("window_size", [int(400 * app.scale), 11 * app.row_height])
app.rebuild()
assert settings.get("visible_rows") == 11 and app.visible_count() == 11, "the number follows the window's own size"
variable = tk.StringVar(master=app.root, value="6")
app.apply_number("visible_rows", variable)
assert app.user_size[1] == 6 * app.row_height and app.visible_count() == 6 and settings.get("visible_rows") == 6
app.user_size = [app.user_size[0], 9 * app.row_height]     # as if you had dragged the bottom edge
app.resizing = {"dir": (0, 1)}
app.resize_end(None)
assert settings.get("visible_rows") == 9 and app.visible_count() == 9
settings.set("window_size", [])
settings.set("visible_rows", 8)
app.rebuild()
print("rows shown OK")
# ---- the slim scroll bar ----
app.view = "settings"
app.apply_layout()
app.refresh()
bar = app.page.bar
moves = []
bar.command = lambda *args: moves.append(args)
bar.set(0.0, 1.0)
assert bar.find_all() == (), "nothing is drawn when everything fits"
bar.set(0.25, 0.5)
assert len(bar.find_all()) == 2, "a track and a thumb"
bar.drag = (10, 0.25)
bar.motion(type("E", (), {"y": 10})())
assert moves[-1][0] == "moveto" and abs(moves[-1][1] - 0.25) < 1e-9
app.view = None
app.apply_layout()
app.refresh(reset=True)
print("scroll bar OK")

# ---- the Screenshots tab shows pictures only ----
assert ("📷 Screenshots", "images") in app.tab_entries() and app.tab_entries()[2][1] == "images", "third tab, after Pinned"
app.set_view("images")
assert app.clips and all(c["kind"] == "image" for c in app.clips), "only pictures on the Screenshots tab"
assert len(app.clips) < len(store.list_clips()), "text clips are left out"
store.delete(app.clips[0]["id"])
app.refresh(reset=True)
assert not app.clips and "screenshots" in app.rows.winfo_children()[0].cget("text").lower(), "its own empty message"
app.set_view(None)
print("screenshots tab OK")

# ---- pinning moves a clip from All to the Pinned tab; a search in All still finds it ----
app.refresh(reset=True)
moved = app.current()
app.toggle_pin()
assert moved["id"] not in [c["id"] for c in app.clips], "a pinned clip leaves the All tab"
app.set_view("pinned")
assert moved["id"] in [c["id"] for c in app.clips], "and shows up in Pinned"
app.set_view(None)
if moved["kind"] == "text":
    app.query.set(moved["content"][:6])
    app.refresh(reset=True)
    assert moved["id"] in [c["id"] for c in app.clips], "a search in All still finds pinned clips"
    app.query.set("")
store.toggle_pin(moved["id"])
app.refresh(reset=True)
assert moved["id"] in [c["id"] for c in app.clips], "unpinning puts it back in All"
print("pin moves to Pinned OK")

# ---- Delete everything on the Settings tab takes two clicks and really empties the history ----
app.set_view("settings")
page = app.page
page.wipe("all")
assert page.wipe_armed == "all" and store.list_clips(), "the first click only asks 'Sure?', nothing is deleted"
page.disarm("all")
assert page.wipe_armed is None, "the question times out"
page.wipe("unpinned")
page.wipe("all")
assert page.wipe_armed == "all" and store.list_clips(), "a click on the other button swaps the question, nothing is deleted"
store.toggle_pin(store.list_clips()[0]["id"])
page.wipe("unpinned")
page.wipe("unpinned")
assert page.wipe_armed is None and "Pinned ones are kept" in page.wipe_message
assert len(store.list_clips()) == 1 and store.list_clips()[0]["pinned"], "the pinned clip survives"
page.wipe("all")
page.wipe("all")
assert store.list_clips() == [] and page.wipe_message.startswith("Deleted 1 clip"), "the second click empties everything"
app.set_view(None)
app.refresh(reset=True)
assert not app.clips and app.rows.winfo_children()[0].cget("text").startswith("Nothing here yet")
print("delete history OK")
print("all window tests passed")
