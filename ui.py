"""The clipboard window: borderless, themed, opened with a hotkey."""
import queue
import re
import time
import tkinter as tk
from tkinter import colorchooser
from tkinter import font as tkfont

import clipedit
import config
import flow
import look
import rowcard
import settings
import settingspage
import store
import texttools
import themes
import winclip

MODIFIER_KEYSYMS = {"Control_L", "Control_R", "Alt_L", "Alt_R", "Shift_L", "Shift_R",
                    "Super_L", "Super_R", "Meta_L", "Meta_R", "Caps_Lock", "Num_Lock"}
SLIDE_PIXELS, FADE_IN_SECONDS, FADE_OUT_SECONDS = 12, 0.15, 0.10
PAUSED_COLOR = "#f0c274"


def ease_out(t):
    """Starts fast and settles gently: 0 -> 1."""
    t = max(0.0, min(1.0, t))
    return 1 - (1 - t) ** 3


class App:
    FOOTER = "Enter paste   Ctrl+1–9 paste that number   Ctrl+click or Shift+click pick several   Ctrl+E edit   Esc close"

    def __init__(self, events, hotkey, notice=""):
        self.events = events           # a queue; other threads put "toggle" / "changed" in it
        self.hotkey = hotkey           # winclip.Hotkey, so Settings can change the shortcut
        self.notice = notice           # a message shown at the bottom of Settings
        self.clips = []                # what the list currently shows
        self.sel = 0                   # index of the selected clip
        self.offset = 0                # index of the first visible row
        self.view = None               # the open tab: None = All, "pinned", "settings" or a tag id
        self.multi = []                # ids of the clips picked for "paste several", in the order picked
        self.prev_hwnd = None          # the window that had focus before we opened
        self.visible = False
        self.had_focus = False
        self.menu_open = False
        self.dialog_open = False
        self.capturing = False         # True while waiting for a new hotkey
        self.entry_shown = True
        self.thumbs = {}               # keeps thumbnail images alive (Tk forgets unreferenced ones)
        self.row_refs = {}             # the RowCard of each visible row, by clip index
        self.tip = None                # the hover box, while it is showing
        self.tip_index = None
        self.tip_photo = None          # keeps the hover picture alive
        self.tip_show_timer = self.tip_hide_timer = None
        self.anim_token = 0            # a new fade cancels the one before it
        self.softened = False          # rounded corners and shadow are set once
        self.editor = None             # the "edit clip" window while it is open
        self.page = settingspage.SettingsPage(self)

        root = self.root = tk.Tk()
        root.withdraw()
        root.overrideredirect(True)
        root.attributes("-topmost", True)
        self.query = tk.StringVar()
        self.query.trace_add("write", lambda *_: self.refresh(reset=True))

        root.bind("<MouseWheel>", self.on_wheel)
        root.bind("<FocusIn>", lambda event: setattr(self, "had_focus", True))
        root.bind("<FocusOut>", lambda event: root.after(150, self.check_focus))
        root.bind("<KeyPress>", self.on_key_press, add="+")
        root.bind("<Escape>", lambda event: self.on_escape())
        root.bind("<Control-Left>", lambda event: self.step_tab(-1))
        root.bind("<Control-Right>", lambda event: self.step_tab(1))

        self.build()
        root.after(60, self.poll_events)

    # ---------- building the window ----------

    def build(self):
        """Creates every widget from the current theme, look and font size. Call again to re-theme."""
        for child in self.root.winfo_children():
            child.destroy()
        c = self.c = themes.current()
        size = settings.get("font_size")
        self.f = {"base": ("Segoe UI", size), "small": ("Segoe UI", max(7, size - 2)),
                  "title": ("Segoe UI Semibold", size + 2), "tab_pt": max(8, size - 1)}
        self.root.configure(bg=c["border"])
        self.ctx = look.Context(self.root, colors=c)
        self.page.canvas = None

        scale = self.scale = self.root.winfo_fpixels("1i") / 96   # 1.0 at 100%, 1.5 at 150% display scaling
        self.base_font = tkfont.Font(font=self.f["base"])
        card_height = max(self.base_font.metrics("linespace") + int(14 * scale), config.THUMB_SIZE[1] + int(10 * scale))
        self.row_height = card_height + int(6 * scale)             # the card plus the gap between cards
        self.settings_min_height = int(400 * scale)
        self.tallest = self.root.winfo_screenheight() - int(220 * scale)   # the window never grows past the screen
        self.default_size = (int(500 * scale),
                             max(min(settings.get("visible_rows") * self.row_height, self.tallest),
                                 self.settings_min_height))
        saved = settings.get("window_size")           # your own size, if you resized the window
        screen_w, screen_h = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        self.user_size = ([min(saved[0], screen_w - 60), min(saved[1], screen_h - 100)]
                          if len(saved) == 2 else None)
        self.resizing = None
        self.last_count = 0
        self.sync_rows()

        body = tk.Frame(self.root, bg=c["bg"])
        body.pack(padx=4, pady=4, fill="both", expand=True)  # the 4 px ring around it holds the resize handles

        header = tk.Frame(body, bg=c["bg"], cursor="fleur")
        header.pack(fill="x", padx=14, pady=(12, 4))
        title = tk.Label(header, text="Clipboard", bg=c["bg"], fg=c["accent"], font=self.f["title"], cursor="fleur")
        title.pack(side="left")
        self.count_label = tk.Label(header, text="", bg=c["bg"], fg=c["dim"], font=self.f["small"], cursor="fleur")
        self.count_label.pack(side="right")
        self.status = tk.Label(header, bg=c["bg"], font=self.f["small"], cursor="hand2", padx=8)
        self.status.pack(side="right")
        self.status.bind("<Button-1>", lambda e: self.toggle_pause())
        self.update_status()
        for handle in (header, title, self.count_label):  # drag the window by its title bar
            handle.bind("<ButtonPress-1>", self.drag_start)
            handle.bind("<B1-Motion>", self.drag_move)
            handle.bind("<ButtonRelease-1>", self.drag_end)

        self.tabs = flow.Flow(body, c["bg"], gap_x=2, gap_y=2)   # wraps onto a second line in a narrow window
        self.tabs.pack(fill="x", padx=10, pady=(2, 6))

        self.entry = tk.Entry(body, textvariable=self.query, bg=c["search"], fg=c["text"],
                              insertbackground=c["accent"], relief="flat", font=self.f["base"],
                              highlightthickness=1, highlightbackground=c["border"],
                              highlightcolor=c["secondary"])
        self.entry.pack(fill="x", padx=14, ipady=6)
        self.entry_shown = True

        width, height = self.current_size()
        self.rows = tk.Frame(body, bg=c["bg"], width=width, height=height)
        self.rows.pack(fill="both", expand=True, pady=(8, 0))
        self.rows.pack_propagate(False)  # the list area has exactly the size we give it

        self.footer = tk.Label(body, bg=c["bg"], fg=c["dim"], font=self.f["small"], anchor="w", justify="left",
                               text=self.FOOTER)
        self.footer.pack(fill="x", padx=14, pady=(6, 10))   # wraps onto more lines in a narrow window

        self.menu = tk.Menu(self.root, tearoff=0, bg=c["panel"], fg=c["text"],
                            activebackground=c["sel"], activeforeground=c["accent"], bd=0)

        keys = [("<Up>", lambda: self.move(-1)), ("<Down>", lambda: self.move(1)),
                ("<Prior>", lambda: self.move(-self.visible_count())),
                ("<Next>", lambda: self.move(self.visible_count())),
                ("<Return>", self.paste), ("<Escape>", self.on_escape),
                ("<Control-Left>", lambda: self.step_tab(-1)), ("<Control-Right>", lambda: self.step_tab(1)),
                ("<Control-p>", self.toggle_pin), ("<Control-t>", self.cycle_tag),
                ("<Control-e>", self.edit_clip), ("<Control-r>", self.toggle_pause),
                ("<Control-space>", self.toggle_pick), ("<Control-Delete>", self.delete)]
        for number in range(1, 10):
            keys.append((f"<Control-Key-{number}>", lambda n=number: self.paste_number(n)))
        for key, action in keys:
            self.entry.bind(key, lambda event, action=action: (action(), "break")[1])
        self.apply_size()
        self.add_resize_handles()

    def update_status(self):
        paused = settings.get("paused")
        self.status.config(text="⏸ Paused" if paused else "● Recording",
                           fg=PAUSED_COLOR if paused else self.c["secondary"])

    # ---------- the size of the window ----------

    def current_size(self):
        """(width, height) of the list area: your own size if you resized, else the default.
        The Settings tab is never shorter than it needs."""
        width, height = self.user_size or self.default_size
        if self.view == "settings":
            height = max(height, self.settings_min_height)
        return width, height

    def apply_size(self):
        width, height = self.current_size()
        self.rows.config(width=width, height=height)
        self.footer.config(wraplength=max(60, width - int(28 * self.scale)))

    def visible_count(self):
        """How many clip rows fit. Your own size decides it; otherwise the 'Rows shown' setting."""
        fits = max(3, self.current_size()[1] // self.row_height)
        return fits if self.user_size else min(settings.get("visible_rows"), fits)

    def keep_on_screen(self):
        self.root.update_idletasks()
        x, y = self.window_position()
        width, height = self.root.winfo_reqwidth(), self.root.winfo_reqheight()
        x = max(0, min(x, self.root.winfo_screenwidth() - width))
        y = max(0, min(y, self.root.winfo_screenheight() - height))
        self.root.geometry(f"+{x}+{y}")

    def add_resize_handles(self):
        """Thin grab areas on the 4 edges and 4 corners. Dragging one resizes the window."""
        thick, grip = 4, 12
        specs = [  # (direction x, direction y, mouse cursor, where to place it)
            (0, -1, "sb_v_double_arrow", dict(x=grip, y=0, relwidth=1, width=-2 * grip, height=thick)),
            (0, 1, "sb_v_double_arrow", dict(x=grip, rely=1, y=-thick, relwidth=1, width=-2 * grip, height=thick)),
            (-1, 0, "sb_h_double_arrow", dict(x=0, y=grip, relheight=1, height=-2 * grip, width=thick)),
            (1, 0, "sb_h_double_arrow", dict(relx=1, x=-thick, y=grip, relheight=1, height=-2 * grip, width=thick)),
            (-1, -1, "size_nw_se", dict(x=0, y=0, width=grip, height=grip)),
            (1, -1, "size_ne_sw", dict(relx=1, x=-grip, y=0, width=grip, height=grip)),
            (-1, 1, "size_ne_sw", dict(x=0, rely=1, y=-grip, width=grip, height=grip)),
            (1, 1, "size_nw_se", dict(relx=1, x=-grip, rely=1, y=-grip, width=grip, height=grip)),
        ]
        for dx, dy, cursor, place in specs:
            handle = tk.Frame(self.root, bg=self.c["border"], cursor=cursor)
            handle.place(**place)
            handle.bind("<ButtonPress-1>", lambda e, d=(dx, dy): self.resize_start(e, d))
            handle.bind("<B1-Motion>", self.resize_move)
            handle.bind("<ButtonRelease-1>", self.resize_end)

    def resize_start(self, event, direction):
        self.hide_tip()
        self.resizing = {"dir": direction, "mouse": (event.x_root, event.y_root),
                         "size": list(self.current_size()), "pos": self.window_position(),
                         "window": (self.root.winfo_reqwidth(), self.root.winfo_reqheight())}

    def resize_move(self, event):
        state = self.resizing
        if not state:
            return
        dx_dir, dy_dir = state["dir"]
        screen_w, screen_h = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        min_w, min_h = int(260 * self.scale), int(200 * self.scale)
        if self.view == "settings":
            min_h = max(min_h, self.settings_min_height)
        width = state["size"][0] + dx_dir * (event.x_root - state["mouse"][0])
        height = state["size"][1] + dy_dir * (event.y_root - state["mouse"][1])
        self.user_size = [max(min_w, min(width, screen_w - 60)), max(min_h, min(height, screen_h - 100))]
        self.apply_size()
        self.root.update_idletasks()
        # Dragging the left or top edge must move the window by exactly as much as it grew.
        x = state["pos"][0] + (state["window"][0] - self.root.winfo_reqwidth() if dx_dir < 0 else 0)
        y = state["pos"][1] + (state["window"][1] - self.root.winfo_reqheight() if dy_dir < 0 else 0)
        self.root.geometry(f"+{x}+{y}")
        if self.view != "settings" and self.visible_count() != self.last_count:
            self.render()  # more or fewer rows fit now

    def resize_end(self, event):
        if not self.resizing:
            return
        self.resizing = None
        settings.set("window_size", list(self.user_size))
        self.sync_rows()
        if settings.get("open_at") == "last":
            settings.set("window_pos", list(self.window_position()))
        self.refresh()

    def sync_rows(self):
        """"Rows shown" always says how many rows the window really shows. If you drag the window to a height
        of its own, the number follows it (and it follows a change of font size too)."""
        if self.user_size and self.view != "settings":
            low, high = settings.LIMITS["visible_rows"]
            rows = max(low, min(high, self.user_size[1] // self.row_height))
            if rows != settings.get("visible_rows"):
                settings.set("visible_rows", rows)

    def reset_size(self):
        self.user_size = None
        settings.set("window_size", [])
        self.rebuild()

    def rebuild(self):
        """Re-creates the window after a theme, look or font change, staying on the same tab."""
        self.build()
        self.refresh_tabs()
        self.apply_layout()
        self.refresh()
        self.focus_input()

    def focus_input(self):
        if self.entry_shown:
            self.entry.focus_force()
        else:
            self.root.focus_force()

    # ---------- showing and hiding ----------

    def run(self):
        self.root.mainloop()

    def toggle(self):
        self.hide(fade=True) if self.visible else self.show()

    def show(self):
        self.prev_hwnd = winclip.foreground_window()
        self.view = None  # every opening starts on the All tab
        self.multi = []
        self.query.set("")
        self.refresh_tabs()
        self.apply_layout()
        self.refresh(reset=True)
        self.root.update_idletasks()
        width, height = self.root.winfo_reqwidth(), self.root.winfo_reqheight()
        screen_w, screen_h = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        saved = settings.get("window_pos")
        caret = winclip.caret_position() if settings.get("open_at") == "caret" else None
        if settings.get("open_at") == "last" and len(saved) == 2:
            x, y = saved  # where you left it last time
        elif caret:
            x, y = caret[0], caret[1] + 8  # just below the text cursor
        else:  # at the mouse pointer (also the fallback when no text cursor is reported)
            x = self.root.winfo_pointerx() - width // 2
            y = min(self.root.winfo_pointery() + 12, screen_h - height - 60)
        x = max(0, min(x, screen_w - width))      # always keep the window on screen
        y = max(0, min(y, screen_h - height))
        self.anim_token += 1                      # cancels a fade-out that is still running
        animate = settings.get("animations")
        self.root.attributes("-alpha", 0.0 if animate else 1.0)
        self.root.geometry(f"+{x}+{y + (round(SLIDE_PIXELS * self.scale) if animate else 0)}")
        self.root.deiconify()
        self.root.lift()
        if not self.softened:
            self.softened = True
            winclip.soften_window(winclip.toplevel_hwnd(self.root.winfo_id()))
        self.visible = True
        self.had_focus = False
        winclip.focus_window(winclip.toplevel_hwnd(self.root.winfo_id()))
        self.focus_input()
        if animate:
            self.animate("in", x, y)

    def hide(self, fade=False):
        """Closes the window. With fade=True it fades out first (not used when pasting, which must be quick)."""
        self.hide_tip()
        self.capturing = False
        self.multi = []
        was_visible, self.visible = self.visible, False
        if fade and was_visible and settings.get("animations"):
            self.animate("out", *self.window_position(), done=self.finish_hide)
        else:
            self.anim_token += 1
            self.finish_hide()

    def finish_hide(self):
        self.root.withdraw()
        self.root.attributes("-alpha", 1.0)

    def animate(self, direction, x, y, done=None):
        """Fades the window in (with a small glide up) or out. A newer animation or a show/hide cancels this one."""
        self.anim_token += 1
        token, started = self.anim_token, time.perf_counter()
        duration = FADE_IN_SECONDS if direction == "in" else FADE_OUT_SECONDS
        slide = round(SLIDE_PIXELS * self.scale)

        def step():
            if token != self.anim_token:
                return
            progress = (time.perf_counter() - started) / duration
            eased = ease_out(progress)
            if direction == "in":
                self.root.attributes("-alpha", eased)
                self.root.geometry(f"+{x}+{round(y + slide * (1 - eased))}")
            else:
                self.root.attributes("-alpha", 1 - eased)
            if progress < 1:
                self.root.after(12, step)
            else:
                if direction == "in":
                    self.root.attributes("-alpha", 1.0)
                    self.root.geometry(f"+{x}+{y}")
                if done:
                    done()
        step()

    # ---------- moving the window ----------

    def window_position(self):
        """Where the window is (or is about to be), read from Tk's own geometry string."""
        match = re.search(r"\+(-?\d+)\+(-?\d+)$", self.root.geometry())
        return (int(match.group(1)), int(match.group(2))) if match else (0, 0)

    def drag_start(self, event):
        self.hide_tip()
        x, y = self.window_position()
        self.drag_offset = (event.x_root - x, event.y_root - y)

    def drag_move(self, event):
        screen_w, screen_h = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        width = max(self.root.winfo_width(), self.root.winfo_reqwidth())
        height = max(self.root.winfo_height(), self.root.winfo_reqheight())
        x = max(0, min(event.x_root - self.drag_offset[0], screen_w - width))
        y = max(0, min(event.y_root - self.drag_offset[1], screen_h - height))
        self.root.geometry(f"+{x}+{y}")

    def drag_end(self, event):
        """Remember the new place, and open there from now on (change this in Settings)."""
        settings.set("window_pos", list(self.window_position()))
        if settings.get("open_at") != "last":
            settings.set("open_at", "last")
            self.notice = "Moved. It will now open where you leave it (change this in Settings)."

    def on_escape(self):
        if self.capturing:
            self.end_capture()
        elif self.multi:
            self.multi = []
            self.restyle_rows()
        else:
            self.hide(fade=True)

    def check_focus(self):
        """Close when you click away, but only after the window has had focus at least once.
        (Otherwise a slow focus hand-over would close it the moment it opens.)"""
        busy = self.menu_open or self.dialog_open
        if self.visible and self.had_focus and not busy and self.root.focus_displayof() is None:
            self.hide(fade=True)

    def poll_events(self):
        try:
            while True:
                event = self.events.get_nowait()
                if event == "toggle":
                    self.toggle()
                elif event == "changed" and self.visible and self.view != "settings":
                    self.refresh()
        except queue.Empty:
            pass
        self.root.after(60, self.poll_events)

    def on_wheel(self, event):
        if self.view == "settings":
            if self.page.canvas is not None and self.page.canvas.winfo_exists():
                self.page.canvas.yview_scroll(-3 if event.delta > 0 else 3, "units")
        else:
            self.move(-1 if event.delta > 0 else 1)

    # ---------- tabs ----------

    def tab_entries(self):
        """(label, view) for every tab: All, Pinned, Screenshots, the tags, then Settings."""
        return ([("All", None), ("★ Pinned", "pinned"), ("📷 Screenshots", "images")]
                + [(t["name"], t["id"]) for t in store.list_tags()]
                + [("⚙ Settings", "settings")])

    def refresh_tabs(self):
        c = self.c
        self.tabs.clear()
        for name, view in self.tab_entries():
            self.tabs.add(self.ctx.button(self.tabs, name, lambda v=view: self.set_view(v), active=view == self.view,
                                          bg=c["bg"], pt=self.f["tab_pt"], pad_x=9, pad_y=3))
        self.tabs.layout(self.current_size()[0] - int(20 * self.scale))

    def apply_layout(self):
        """The search box is hidden on the Settings tab."""
        if self.view == "settings" and self.entry_shown:
            self.entry.pack_forget()
            self.entry_shown = False
        elif self.view != "settings" and not self.entry_shown:
            self.entry.pack(fill="x", padx=14, ipady=6, before=self.rows)
            self.entry_shown = True
        self.apply_size()  # the Settings tab may need a taller list area than the clips do
        if self.visible:
            self.keep_on_screen()

    def set_view(self, view):
        self.view = view
        self.multi = []
        self.refresh_tabs()
        self.apply_layout()
        self.refresh(reset=True)
        self.focus_input()

    def step_tab(self, step):
        """Ctrl+Left / Ctrl+Right: move to the previous or next tab."""
        views = [view for _, view in self.tab_entries()]
        current = views.index(self.view) if self.view in views else 0
        self.set_view(views[(current + step) % len(views)])

    # ---------- the clip list ----------

    def refresh(self, reset=False):
        if self.view == "settings":
            self.clips = []
            self.count_label.config(text="")
            self.page.render()
            return
        tag_id = self.view if isinstance(self.view, int) else None
        query = self.query.get().strip()
        self.clips = store.list_clips(query, tag_id, pinned_only=self.view == "pinned",
                                      limit=max(config.LIST_LIMIT, settings.get("visible_rows")),
                                      kind="image" if self.view == "images" else None,   # the Screenshots tab: pictures only
                                      unpinned_only=self.view is None and not query)     # pinning moves a clip out of All (a search still finds it)
        if reset:
            self.sel = self.offset = 0
        self.sel = min(self.sel, max(0, len(self.clips) - 1))
        self.update_count()
        self.render()

    def update_count(self):
        self.count_label.config(text=f"{len(self.multi)} picked" if self.multi else f"{len(self.clips)} clips")

    def render(self):
        c = self.c
        rows = self.last_count = self.visible_count()
        self.offset = max(0, min(self.offset, self.sel))
        if self.sel >= self.offset + rows:
            self.offset = self.sel - rows + 1
        self.hide_tip()
        for child in self.rows.winfo_children():
            child.destroy()
        self.row_refs = {}  # index -> the RowCard of that row
        shown = self.clips[self.offset: self.offset + rows]
        if not shown:
            empty = "No screenshots yet. Take one with Snipper or Print Screen!" if self.view == "images" else "Nothing here yet. Copy something!"
            tk.Label(self.rows, text=empty, bg=c["bg"],
                     fg=c["dim"], font=self.f["base"], pady=40).pack()
        for position, clip in enumerate(shown):
            self.make_row(self.offset + position, position, clip)

    def style_row(self, index):
        """Colours one row as selected, picked or plain. Done in place so the row survives a click."""
        card = self.row_refs[index]
        picked = card.clip["id"] in self.multi
        card.set_state("selected" if index == self.sel else ("picked" if picked else "normal"), picked)

    def restyle_rows(self):
        for index in self.row_refs:
            self.style_row(index)
        self.update_count()
        if self.multi:   # the hint line says what the picks are for, so it is clear they worked
            self.footer.config(text=f"{len(self.multi)} picked   Enter pastes them together   Esc clears", fg=self.c["accent"])
        else:
            self.footer.config(text=self.FOOTER, fg=self.c["dim"])

    def make_row(self, index, position, clip):
        card = rowcard.RowCard(self.rows, self, index, position, clip)
        card.pack(fill="x")
        self.row_refs[index] = card
        self.style_row(index)
        card.bind("<Button-1>", lambda e, i=index: self.click(i))
        card.bind("<Control-Button-1>", lambda e, i=index: self.ctrl_click(i))
        card.bind("<Shift-Button-1>", lambda e, i=index: self.shift_click(i))
        card.bind("<Double-Button-1>", lambda e, i=index: (self.click(i), self.paste()))
        card.bind("<Button-3>", lambda e, i=index: self.context_menu(e, i))
        card.bind("<Enter>", lambda e, i=index: self.row_enter(i))
        card.bind("<Leave>", lambda e, i=index: self.row_leave(i))

    def row_enter(self, index):
        card = self.row_refs.get(index)
        if card is not None and card.state == "normal":
            card.set_state("hover", card.picked)
        self.hover_enter(index)

    def row_leave(self, index):
        if index in self.row_refs:
            self.style_row(index)
        self.hover_leave()

    def thumbnail(self, filename):
        if filename not in self.thumbs:
            try:
                from PIL import Image, ImageTk
                with Image.open(config.IMAGE_DIR / filename) as image:
                    image.thumbnail(config.THUMB_SIZE)
                    self.thumbs[filename] = ImageTk.PhotoImage(image.copy())
            except Exception:
                self.thumbs[filename] = None
        return self.thumbs[filename]

    # ---------- actions on clips ----------

    def current(self):
        return self.clips[self.sel] if self.clips else None

    # ---------- hover: show the whole clip ----------

    def tip_text(self, clip, cut_off):
        """The text for the hover box, or None when the row already shows everything."""
        if clip["kind"] != "text":
            return None
        full = clip["content"].strip()
        if "\n" not in full and not cut_off:
            return None  # it fits in the row, nothing to reveal
        lines = full.splitlines()
        text = "\n".join(lines[:25]) + ("\n…" if len(lines) > 25 else "")
        return text[:1500] + ("…" if len(text) > 1500 else "")

    def hover_enter(self, index):
        if not settings.get("hover_preview"):
            return
        self.cancel_timer("tip_hide")
        if self.tip is not None and self.tip_index == index:
            return  # moving between parts of the same row
        self.cancel_timer("tip_show")
        self.tip_show_timer = self.root.after(450, lambda: self.show_tip(index))

    def hover_leave(self):
        self.cancel_timer("tip_show")
        self.cancel_timer("tip_hide")
        self.tip_hide_timer = self.root.after(120, self.hide_tip)

    def cancel_timer(self, name):
        timer = getattr(self, name + "_timer", None)
        if timer:
            self.root.after_cancel(timer)
        setattr(self, name + "_timer", None)

    def show_tip(self, index, at=None):
        """A small box next to the pointer with the full text (or a bigger picture)."""
        self.hide_tip()
        if index >= len(self.clips) or not self.visible and at is None:
            return
        clip, c = self.clips[index], self.c
        card = self.row_refs.get(index)
        tip = tk.Toplevel(self.root)
        tip.withdraw()
        tip.overrideredirect(True)
        tip.attributes("-topmost", True)
        tip.configure(bg=c["accent"])
        inner = tk.Frame(tip, bg=c["panel"])
        inner.pack(padx=1, pady=1)
        if clip["kind"] == "image":
            try:
                from PIL import Image, ImageTk
                with Image.open(config.IMAGE_DIR / clip["content"]) as image:
                    width, height = image.size
                    image.thumbnail((int(380 * self.scale), int(280 * self.scale)))
                    self.tip_photo = ImageTk.PhotoImage(image.copy())
                tk.Label(inner, image=self.tip_photo, bg=c["panel"], padx=6, pady=6).pack()
                tk.Label(inner, text=f"{width} x {height}", bg=c["panel"], fg=c["dim"],
                         font=self.f["small"]).pack(pady=(0, 6))
            except Exception:
                tip.destroy()
                return
        else:
            text = self.tip_text(clip, bool(card and card.truncated))
            if not text:
                tip.destroy()
                return
            tk.Label(inner, text=text, bg=c["panel"], fg=c["text"], font=self.f["base"], justify="left",
                     anchor="w", wraplength=int(480 * self.scale), padx=10, pady=8).pack()
        if clip.get("source"):  # where and when it was copied
            when = time.strftime("%d %b %H:%M", time.localtime(clip["created"]))
            tk.Label(inner, text=f"{rowcard.app_name(clip['source'])} · {when}", bg=c["panel"], fg=c["dim"],
                     font=self.f["small"], anchor="w", padx=10).pack(fill="x", pady=(0, 6))
        tip.update_idletasks()
        screen_w, screen_h = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        x, y = at or (self.root.winfo_pointerx() + 16, self.root.winfo_pointery() + 20)
        x = max(0, min(x, screen_w - tip.winfo_reqwidth()))
        y = max(0, min(y, screen_h - tip.winfo_reqheight()))
        tip.geometry(f"+{x}+{y}")
        tip.deiconify()
        self.tip, self.tip_index = tip, index

    def hide_tip(self):
        self.cancel_timer("tip_show")
        self.cancel_timer("tip_hide")
        if self.tip is not None:
            self.tip.destroy()
            self.tip = None

    # ---------- selecting ----------

    def select(self, index):
        """Moves the highlight. The rows are NOT rebuilt: a double-click needs the same row
        widget under the pointer for both clicks, or it would never be recognised."""
        self.hide_tip()
        if index in self.row_refs:
            previous, self.sel = self.sel, index
            if previous in self.row_refs:
                self.style_row(previous)
            self.style_row(index)
        else:
            self.sel = index
            self.render()

    def click(self, index):
        """A plain click: highlights the row and drops any several-clip selection."""
        if self.multi:
            self.multi = []
            self.restyle_rows()
        self.select(index)

    def ctrl_click(self, index):
        self.toggle_pick(index)
        self.select(index)

    def shift_click(self, index):
        """Shift+click: picks every text clip from the highlighted row to this one."""
        low, high = sorted((self.sel, index))
        picked = [c["id"] for c in self.clips[low:high + 1] if c["kind"] == "text"]
        self.multi = picked if low == self.sel else picked[::-1]
        self.select(index)
        self.restyle_rows()

    def toggle_pick(self, index=None):
        """Adds a text clip to (or removes it from) the clips picked for pasting together."""
        index = self.sel if index is None else index
        if not 0 <= index < len(self.clips):
            return
        clip = self.clips[index]
        if clip["kind"] != "text":
            return  # pictures cannot be joined with text
        current = self.current()
        if not self.multi and current and current["kind"] == "text" and current["id"] != clip["id"]:
            self.multi.append(current["id"])  # the highlighted row counts as the first pick
        if clip["id"] in self.multi:
            self.multi.remove(clip["id"])
        else:
            self.multi.append(clip["id"])
        self.restyle_rows()

    def move(self, step):
        if self.clips:
            self.sel = max(0, min(len(self.clips) - 1, self.sel + step))
            self.render()

    # ---------- pasting ----------

    def finish_paste(self):
        """The text is on the clipboard: close, give the other window its focus back, press Ctrl+V."""
        previous = self.prev_hwnd
        self.hide()
        self.root.after(80, lambda: (winclip.focus_window(previous), self.root.after(80, winclip.send_ctrl_v)))

    def paste_text(self, text):
        """Pastes this text (from a text tool, the editor or several picked clips). The saved clip is untouched."""
        if winclip.set_text(text):
            self.finish_paste()

    def paste(self):
        if self.multi:
            return self.paste_picked()
        clip = self.current()
        if not clip:
            return
        if clip["kind"] == "image":
            done = winclip.set_image(config.IMAGE_DIR / clip["content"])
        else:
            done = winclip.set_text(clip["content"])
        if not done:
            return
        store.touch(clip["id"])
        self.finish_paste()

    def paste_picked(self):
        clips = [store.get_clip(clip_id) for clip_id in self.multi]
        texts = [clip["content"] for clip in clips if clip and clip["kind"] == "text"]
        self.multi = []
        if texts:
            self.paste_text(settings.SEPARATORS[settings.get("multi_separator")].join(texts))
        else:
            self.restyle_rows()

    def paste_number(self, number):
        """Ctrl+1 to Ctrl+9: pastes the clip with that number (rows are numbered from the top of the whole list)."""
        index = number - 1
        if index < len(self.clips):
            self.multi = []
            self.sel = index
            self.paste()

    def paste_as(self, key):
        clip = self.current()
        if clip and clip["kind"] == "text":
            self.paste_text(texttools.apply(key, clip["content"]))

    def edit_clip(self):
        clip = self.current()
        if not clip or clip["kind"] != "text" or self.editor is not None:
            return
        self.hide()
        self.editor = clipedit.ClipEditor(self, clip["content"])

    # ---------- other actions ----------

    def toggle_pin(self):
        clip = self.current()
        if clip:
            store.toggle_pin(clip["id"])
            self.refresh()

    def cycle_tag(self):
        """Ctrl+T: none -> first tag -> second tag -> ... -> none."""
        clip = self.current()
        if not clip:
            return
        ids = [None] + [t["id"] for t in store.list_tags()]
        store.set_tag(clip["id"], ids[(ids.index(clip["tag_id"]) + 1) % len(ids)])
        self.refresh()

    def delete(self):
        clip = self.current()
        if clip:
            store.delete(clip["id"])
            self.refresh()

    def set_paused(self, paused):
        settings.set("paused", bool(paused))
        self.update_status()
        if self.view == "settings":
            self.page.render()

    def toggle_pause(self):
        self.set_paused(not settings.get("paused"))

    def context_menu(self, event, index):
        c = self.c
        self.select(index)
        clip = self.current()
        text_clip = clip["kind"] == "text"
        self.menu.delete(0, "end")
        self.menu.add_command(label="Paste", command=self.paste)
        if text_clip:
            tools = tk.Menu(self.menu, tearoff=0, bg=c["panel"], fg=c["text"],
                            activebackground=c["sel"], activeforeground=c["accent"], bd=0)
            for key, name, _ in texttools.TOOLS:
                tools.add_command(label=name, command=lambda k=key: self.paste_as(k))
            self.menu.add_cascade(label="Paste as…", menu=tools)
            self.menu.add_command(label="Edit before pasting…", command=self.edit_clip)
            self.menu.add_command(label="Remove from the pick" if clip["id"] in self.multi else "Pick to paste several",
                                  command=self.toggle_pick)
        self.menu.add_separator()
        self.menu.add_command(label="Unpin" if clip["pinned"] else "Pin (moves it to Pinned)", command=self.toggle_pin)
        tag_menu = tk.Menu(self.menu, tearoff=0, bg=c["panel"], fg=c["text"],
                           activebackground=c["sel"], activeforeground=c["accent"], bd=0)
        tag_menu.add_command(label="No tag", command=lambda: self.set_tag(None))
        for tag in store.list_tags():
            tag_menu.add_command(label="●  " + tag["name"], foreground=tag["color"],
                                 command=lambda t=tag["id"]: self.set_tag(t))
        self.menu.add_cascade(label="Tag", menu=tag_menu)
        self.menu.add_separator()
        self.menu.add_command(label="Delete", command=self.delete)
        self.menu_open = True
        try:
            self.menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.menu.grab_release()
            self.menu_open = False
            self.focus_input()

    def set_tag(self, tag_id):
        clip = self.current()
        if clip:
            store.set_tag(clip["id"], tag_id)
            self.refresh()

    # ---------- the Settings tab (drawn by settingspage.py) ----------

    def apply_number(self, key, variable):
        low, high = settings.LIMITS[key]
        try:
            value = max(low, min(high, int(variable.get())))
        except ValueError:
            variable.set(str(settings.get(key)))
            return
        variable.set(str(value))
        if value != settings.get(key):
            settings.set(key, value)
            if key == "visible_rows" and self.user_size:   # your own window size must follow the number you typed
                height = max(int(200 * self.scale), min(value * self.row_height, self.tallest))
                settings.set("window_size", [self.user_size[0], height])
            if key in ("font_size", "visible_rows"):
                self.rebuild()

    def save_ignored(self):
        names = [part.strip().lower() for part in self.ignored.get().split(",") if part.strip()]
        if names != settings.get("extra_ignored_apps"):
            settings.set("extra_ignored_apps", names)

    def choose_theme(self, key):
        settings.set("theme", key)
        self.rebuild()

    def pick_color(self, key):
        custom = dict(settings.get("custom_colors"))
        self.dialog_open = True
        self.root.attributes("-topmost", False)  # otherwise our window would cover the colour dialog
        try:
            chosen = colorchooser.askcolor(color=custom.get(key), parent=self.root, title="Pick a colour")[1]
        finally:
            self.root.attributes("-topmost", True)
            self.dialog_open = False
        if chosen:
            custom[key] = chosen
            settings.set("custom_colors", custom)
            settings.set("theme", "custom")
            self.rebuild()

    def reset_settings(self):
        settings.reset()
        error = self.hotkey.start(*settings.hotkey_parts(settings.get("hotkey"))[:2])
        self.notice = error or "Settings reset."
        self.rebuild()

    # ---------- changing the hotkey ----------

    def start_capture(self):
        self.capturing = True
        self.hotkey_text.config(text="Press the new shortcut...")
        self.change_button.set_text("Esc to cancel")
        self.root.focus_force()

    def end_capture(self):
        self.capturing = False
        if self.view == "settings":
            self.page.render()

    def on_key_press(self, event):
        if not self.capturing or event.keysym in MODIFIER_KEYSYMS:
            return None
        symbol = event.keysym
        key = None
        if len(symbol) == 1 and symbol.isalnum():
            key = symbol.upper()
        elif re.fullmatch(r"F\d{1,2}", symbol) and 1 <= int(symbol[1:]) <= 24:
            key = symbol
        elif symbol in settings.KEYSYM_TO_KEY:
            key = settings.KEYSYM_TO_KEY[symbol]
        ctrl, shift, alt = bool(event.state & 0x4), bool(event.state & 0x1), bool(event.state & 0x20000)
        if symbol == "Escape":
            return None  # the Escape binding cancels
        if not key or not (ctrl or alt):
            self.notice = "Use Ctrl or Alt together with a letter, number, F-key or punctuation key."
            self.end_capture()
            return "break"

        new = {"ctrl": ctrl, "alt": alt, "shift": shift, "key": key}
        old = settings.get("hotkey")
        error = self.hotkey.start(*settings.hotkey_parts(new)[:2])
        if error:
            self.hotkey.start(*settings.hotkey_parts(old)[:2])  # put the old shortcut back
            self.notice = f"{settings.hotkey_parts(new)[2]}: {error}"
        else:
            settings.set("hotkey", new)
            self.notice = f"Hotkey is now {settings.hotkey_parts(new)[2]}."
        self.capturing = False
        self.rebuild()
        return "break"
