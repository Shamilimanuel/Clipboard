"""A slim scroll bar in the theme's colours (Windows' own scroll bar cannot be recoloured).

Works like tk.Scrollbar: give it `command` (a canvas's yview) and pass its set() as yscrollcommand.
Drag the thumb, or click the track to jump there. It draws nothing when everything already fits.
"""
import tkinter as tk

import themes


class ThinScrollbar(tk.Canvas):
    def __init__(self, parent, command, colors, scale):
        super().__init__(parent, width=int(9 * scale), bg=colors["bg"], highlightthickness=0, bd=0, cursor="hand2")
        self.command, self.colors, self.scale = command, colors, scale
        self.first, self.last = 0.0, 1.0
        self.hover = False
        self.drag = None
        self.bind("<Configure>", lambda e: self.redraw())
        self.bind("<ButtonPress-1>", self.press)
        self.bind("<B1-Motion>", self.motion)
        self.bind("<ButtonRelease-1>", lambda e: setattr(self, "drag", None))
        self.bind("<Enter>", lambda e: self.set_hover(True))
        self.bind("<Leave>", lambda e: self.set_hover(False))

    def set(self, first, last):
        self.first, self.last = float(first), float(last)
        self.redraw()

    def set_hover(self, hover):
        self.hover = hover
        self.redraw()

    def thumb_range(self):
        height = max(1, self.winfo_height())
        top = self.first * height
        bottom = max(top + 24 * self.scale, self.last * height)   # never thinner than a fingertip
        return top, min(bottom, height)

    def redraw(self):
        self.delete("all")
        if self.last - self.first >= 0.999:
            return
        width, c = max(1, self.winfo_width()), self.colors
        middle = width / 2
        self.create_line(middle, 2, middle, max(3, self.winfo_height() - 2), width=2, fill=c["border"], capstyle="round")
        top, bottom = self.thumb_range()
        pad = 3 * self.scale
        color = c["accent"] if (self.hover or self.drag) else c["secondary"]
        self.create_line(middle, top + pad, middle, max(top + pad, bottom - pad), width=max(3, width - 3),
                         fill=color, capstyle="round")

    def press(self, event):
        top, bottom = self.thumb_range()
        if top <= event.y <= bottom:
            self.drag = (event.y, self.first)
        else:   # a click on the track centres the thumb there
            height = max(1, self.winfo_height())
            self.command("moveto", max(0.0, event.y / height - (self.last - self.first) / 2))
        self.redraw()

    def motion(self, event):
        if self.drag:
            start_y, start_first = self.drag
            self.command("moveto", max(0.0, start_first + (event.y - start_y) / max(1, self.winfo_height())))
