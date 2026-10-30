"""A frame that lays its children out left to right and starts a new line when they no longer fit.

Used for the tabs and for the buttons in Settings, so nothing is cut off when the window is made narrow.
Add each child with add(); the frame grows taller by itself when it has to wrap.
"""
import tkinter as tk


class Flow(tk.Frame):
    def __init__(self, parent, bg, gap_x=2, gap_y=2):
        super().__init__(parent, bg=bg, height=1)
        self.items = []
        self.gap_x, self.gap_y = gap_x, gap_y
        self.width = 0
        self.bind("<Configure>", self.on_configure)

    def add(self, widget, **options):
        self.items.append(widget)
        return widget

    def clear(self):
        for child in self.winfo_children():
            child.destroy()
        self.items = []

    def on_configure(self, event):
        if event.width != self.width:
            self.layout(event.width)

    def layout(self, width=None):
        """Places every child; wraps to a new line when the next one would pass `width`."""
        width = width or self.width or 100000
        self.width = width
        x = y = line_height = 0
        for widget in self.items:
            if not widget.winfo_exists():
                continue
            w, h = widget.winfo_reqwidth(), widget.winfo_reqheight()
            if x > 0 and x + w > width:
                x, y, line_height = 0, y + line_height + self.gap_y, 0
            widget.place(x=x, y=y)
            x += w + self.gap_x
            line_height = max(line_height, h)
        height = max(1, y + line_height)
        if int(self.cget("height")) != height:
            self.configure(height=height)
