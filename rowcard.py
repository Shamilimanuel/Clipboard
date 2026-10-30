"""One clip in the list, drawn as a card.

A row is a single Canvas: the card picture (see look.card_image), a tag colour stripe, a number for quick paste,
the text or a thumbnail, and the app and age on the right. Changing its state (hover, selected, picked) only swaps
the picture and recolours the text, it never rebuilds the row. That matters: a double-click needs the same widget
under the pointer for both clicks.
"""
import time
import tkinter as tk

import look


def ago(timestamp):
    seconds = max(0, int(time.time() - timestamp))
    if seconds < 60:
        return "now"
    if seconds < 3600:
        return f"{seconds // 60}m"
    if seconds < 86400:
        return f"{seconds // 3600}h"
    return f"{seconds // 86400}d"


def app_name(source):
    """'chrome.exe' -> 'chrome', short enough for a row."""
    name = source[:-4] if source.lower().endswith(".exe") else source
    return name if len(name) <= 11 else name[:10] + "…"


class RowCard(tk.Canvas):
    def __init__(self, parent, app, index, position, clip):
        self.app, self.index, self.position, self.clip = app, index, position, clip
        self.state = "normal"
        self.picked = False                 # chosen for "paste several": shows a tick instead of the number
        self.truncated = False
        self.drawn_width = 0
        c = app.c
        super().__init__(parent, width=app.current_size()[0], height=app.row_height, bg=c["bg"],
                         highlightthickness=0, bd=0, cursor="hand2")
        self.card = self.create_image(0, 0, anchor="nw")
        self.stripe = self.create_rectangle(0, 0, 0, 0, width=0, fill=clip["tag_color"] or c["bg"],
                                            state="normal" if clip["tag_color"] else "hidden")
        self.number = self.create_text(0, 0, anchor="e", font=app.f["small"], fill=c["dim"])   # right-aligned: 1 to 2000
        self.thumb = None
        if clip["kind"] == "image":
            self.thumb = self.create_image(0, 0, anchor="w")
        self.label = self.create_text(0, 0, anchor="w", font=app.f["base"], fill=c["text"])
        self.meta = self.create_text(0, 0, anchor="e", font=app.f["small"], fill=c["dim"])
        self.bind("<Configure>", self.on_configure)
        self.layout(int(self["width"]))

    # ---------- drawing ----------

    def on_configure(self, event):
        if event.width > 40 and event.width != self.drawn_width:
            self.layout(event.width)

    def meta_text(self):
        clip = self.clip
        parts = ["★"] if clip["pinned"] else []
        if clip.get("source"):
            parts.append(app_name(clip["source"]))
        parts.append(ago(clip["created"]))
        return "  ".join(parts)

    def fit(self, text, available):
        """The text cut with … so it fits `available` pixels. Sets self.truncated."""
        font = self.app.base_font
        self.truncated = False
        if font.measure(text) <= available:
            return text
        self.truncated = True
        low, high = 0, len(text)
        while low < high:
            middle = (low + high + 1) // 2
            if font.measure(text[:middle] + "…") <= available:
                low = middle
            else:
                high = middle - 1
        return text[:low].rstrip() + "…"

    def layout(self, width):
        app, clip = self.app, self.clip
        height = app.row_height
        self.drawn_width = width
        scale = app.scale
        mx = round((6 if app.ctx.look == "flat" else 8) * scale)
        left, right, middle = mx, width - mx, height / 2
        self.coords(self.stripe, left + 7 * scale, middle - height * 0.28, left + 10 * scale, middle + height * 0.28)
        self.coords(self.number, left + 40 * scale, middle)
        x = left + 46 * scale
        self.itemconfigure(self.meta, text=self.meta_text())
        self.coords(self.meta, right - 12 * scale, middle)
        meta_left = self.bbox(self.meta)[0] if self.bbox(self.meta) else right - 40 * scale
        available = max(20, meta_left - x - 14 * scale)
        if clip["kind"] == "image":
            picture = app.thumbnail(clip["content"])
            self.itemconfigure(self.thumb, image=picture or "")
            self.coords(self.thumb, x, middle)
            x += (picture.width() if picture else 0) + 8 * scale
            text = "Image"
            self.truncated = False
        else:
            text = self.fit(" ".join(clip["content"][:600].split()), max(20, available - (x - (left + 46 * scale))))
        self.itemconfigure(self.label, text=text)
        self.coords(self.label, x, middle)
        self.set_state(self.state, self.picked, force=True)

    def set_state(self, state, picked=False, force=False):
        if state == self.state and picked == self.picked and not force:
            return
        self.state, self.picked = state, picked
        c = self.app.c
        self.itemconfigure(self.card, image=look.card_image(self.app.ctx, self.drawn_width, self.app.row_height,
                                                            state, c["bg"]))
        self.itemconfigure(self.label, fill=c["accent"] if state == "selected" else c["text"])
        number = "✓" if picked else str(self.index + 1)   # the clip's real place in the list, not its place on screen
        self.itemconfigure(self.number, text=number, fill=c["accent"] if (picked or state == "selected") else c["dim"])
        self.itemconfigure(self.meta, fill=c["secondary"] if self.clip["pinned"] else c["dim"])
