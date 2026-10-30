"""The Settings tab: a scrolling page in sections (Look and feel, Window, Pasting, History and privacy, Sorting
and tags). Buttons are drawn in the chosen look; clicking one saves the choice straight away."""
import tkinter as tk
from tkinter import colorchooser

import config
import flow
import settings
import store
import themes
import thinbar

TAG_COLORS = ["#8ff3ff", "#4eb1b1", "#ffc857", "#ff8fb1", "#b69cff", "#7be0a0", "#ff9f6e", "#7fb8ff"]
KEYS = ["Enter paste        Ctrl+1 to Ctrl+9 paste that row",
        "Ctrl+click or Ctrl+Space pick several, Enter pastes them together",
        "Ctrl+P pin     Ctrl+T cycle the tag     Ctrl+E edit before pasting",
        "Ctrl+R pause or resume recording     Ctrl+Del delete",
        "Ctrl+Left or Right switch tab     Esc close"]


class SettingsPage:
    def __init__(self, app):
        self.app = app
        self.canvas = None
        self.tag_message = ""
        self.wipe_armed = None      # "unpinned" or "all" after the first click on a delete button, until the second click
        self.wipe_message = ""

    # ---------- building blocks ----------

    def section(self, title):
        c, f = self.app.c, self.app.f
        tk.Label(self.form, text=title.upper(), bg=c["bg"], fg=c["accent"], font=f["small"], anchor="w"
                 ).grid(row=self.line, column=0, columnspan=2, sticky="w", pady=(16, 2))
        self.line += 1
        tk.Frame(self.form, bg=c["border"], height=1).grid(row=self.line, column=0, columnspan=2, sticky="ew", pady=(0, 4))
        self.line += 1

    def row(self, caption):
        c, f = self.app.c, self.app.f
        tk.Label(self.form, text=caption, bg=c["bg"], fg=c["dim"], font=f["small"], anchor="w"
                 ).grid(row=self.line, column=0, sticky="nw", pady=4, padx=(0, 14))
        holder = flow.Flow(self.form, c["bg"], gap_x=2, gap_y=2)   # buttons wrap onto a new line when narrow
        holder.grid(row=self.line, column=1, sticky="ew", pady=2)
        self.line += 1
        return holder

    def row_plain(self, caption):
        """Like row(), but the right side is an ordinary frame you pack things into."""
        holder = self.row(caption)
        holder.destroy()
        plain = tk.Frame(self.form, bg=self.app.c["bg"])
        plain.grid(row=self.line - 1, column=1, sticky="w", pady=2)
        return plain

    def button(self, parent, text, command, active=False):
        pt = max(8, settings.get("font_size") - 1)
        return self.app.ctx.button(parent, text, command, active=active, bg=self.app.c["bg"], pt=pt, pad_x=9, pad_y=3)

    def choices(self, holder, options, current, command):
        """A row of buttons, one per option; the current one is lit."""
        for key, name in options:
            holder.add(self.button(holder, name, lambda k=key: command(k), active=key == current))

    def note(self, holder, text):
        c = self.app.c
        holder.add(tk.Label(holder, text=text, bg=c["bg"], fg=c["dim"], font=self.app.f["small"], padx=6))

    def set_and_redraw(self, key, value):
        settings.set(key, value)
        self.render()

    # ---------- the page ----------

    def render(self):
        app = self.app
        c, f = app.c, app.f
        fraction = self.canvas.yview()[0] if self.canvas is not None and self.canvas.winfo_exists() else 0.0
        for child in app.rows.winfo_children():
            child.destroy()
        canvas = self.canvas = tk.Canvas(app.rows, bg=c["bg"], highlightthickness=0, bd=0, yscrollincrement=28)
        bar = self.bar = thinbar.ThinScrollbar(app.rows, canvas.yview, c, app.scale)
        canvas.configure(yscrollcommand=bar.set)
        bar.pack(side="right", fill="y", padx=(0, int(3 * app.scale)))
        canvas.pack(side="left", fill="both", expand=True)
        form = self.form = tk.Frame(canvas, bg=c["bg"])
        margin = int(14 * app.scale)
        window = canvas.create_window((margin, 0), window=form, anchor="nw")
        canvas.bind("<Configure>", lambda e: canvas.itemconfigure(window, width=max(50, e.width - 2 * margin)))
        form.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        form.columnconfigure(0, minsize=int(112 * app.scale))   # the captions line up in one column
        form.columnconfigure(1, weight=1)
        self.line = 0

        self.section("Look and feel")
        self.choices(self.row("Theme"), themes.choices(), settings.get("theme"), app.choose_theme)
        holder = self.row("Look")
        self.choices(holder, settings.LOOKS, settings.get("look"), lambda k: (settings.set("look", k), app.rebuild()))
        holder = self.row("Animations")
        self.choices(holder, [(True, "On"), (False, "Off")], settings.get("animations"),
                     lambda v: self.set_and_redraw("animations", v))
        self.note(holder, "the window fades and glides in")
        self.number_row(self.row("Font size"), "font_size")
        holder = self.row("Custom colours")
        try:
            custom = themes.from_custom(settings.get("custom_colors"))
        except (ValueError, KeyError, IndexError):
            custom = themes.THEMES["teal"]
        for key, name in themes.CUSTOM_FIELDS:
            piece = tk.Frame(holder, bg=c["bg"], padx=4)
            swatch = tk.Label(piece, bg=custom[key], width=3, relief="solid", bd=1, cursor="hand2")
            swatch.pack(side="left")
            caption = tk.Label(piece, text=name, bg=c["bg"], fg=c["text"], font=f["small"], cursor="hand2")
            caption.pack(side="left", padx=(4, 8))
            for widget in (swatch, caption):
                widget.bind("<Button-1>", lambda e, k=key: app.pick_color(k))
            holder.add(piece)

        self.section("Window")
        self.choices(self.row("Opens"), [("mouse", "At the mouse"), ("caret", "At the text cursor"), ("last", "Where I left it")],
                     settings.get("open_at"), lambda k: self.set_and_redraw("open_at", k))
        self.choices(self.row("Hover to read"), [(True, "Show the full text"), (False, "Off")],
                     settings.get("hover_preview"), lambda v: self.set_and_redraw("hover_preview", v))
        holder = self.row("Window size")
        width, height = app.current_size()
        holder.add(tk.Label(holder, text=f"{width} x {height}   drag any edge or corner", bg=c["bg"], fg=c["text"],
                            font=f["small"], padx=4))
        holder.add(self.button(holder, "Reset size", app.reset_size))
        self.number_row(self.row("Rows shown"), "visible_rows")

        self.section("Pasting")
        holder = self.row("Pick several")
        self.choices(holder, [("newline", "New line"), ("comma", "Comma"), ("space", "Space")],
                     settings.get("multi_separator"), lambda k: self.set_and_redraw("multi_separator", k))
        self.note(holder, "Ctrl+click clips, then Enter")
        holder = self.row("Hotkey")
        app.hotkey_text = tk.Label(holder, text=settings.hotkey_parts(settings.get("hotkey"))[2], bg=c["search"],
                                   fg=c["accent"], font=f["base"], padx=10, pady=2)
        holder.add(app.hotkey_text)
        app.change_button = holder.add(self.button(holder, "Change", app.start_capture))

        self.section("History and privacy")
        holder = self.row("Recording")
        self.choices(holder, [(False, "On"), (True, "Paused")], settings.get("paused"), app.set_paused)
        self.note(holder, "Ctrl+R in the list does the same")
        self.number_row(self.row("Clips to keep"), "max_clips")
        holder = self.row("Never record apps")
        app.ignored = tk.StringVar(value=", ".join(settings.get("extra_ignored_apps")))
        entry = tk.Entry(holder, textvariable=app.ignored, width=30, bg=c["search"], fg=c["text"],
                         insertbackground=c["accent"], relief="flat", font=f["small"], highlightthickness=1,
                         highlightbackground=c["border"], highlightcolor=c["secondary"])
        holder.add(entry)
        entry.bind("<Return>", lambda e: app.save_ignored())
        entry.bind("<FocusOut>", lambda e: app.save_ignored())
        self.note(holder, "e.g. myvault.exe")
        holder = self.row("Delete history")
        for which, name in (("unpinned", "Delete all unpinned"), ("all", "Delete everything")):
            armed = self.wipe_armed == which
            holder.add(self.button(holder, "Sure? Click again" if armed else name, lambda w=which: self.wipe(w), active=armed))
        self.note(holder, self.wipe_message or ("it cancels by itself in a few seconds" if self.wipe_armed else "pictures go too"))

        self.section("Sorting and tags")
        names = [(t["name"], t["name"]) for t in store.list_tags()]
        for caption, key in (("Links go to", "auto_tag_links"), ("Code goes to", "auto_tag_code")):
            holder = self.row(caption)
            self.choices(holder, [("", "Off")] + names, settings.get(key), lambda v, k=key: self.set_and_redraw(k, v))
        self.tag_editor()

        self.section("Keys")
        for line in KEYS:
            tk.Label(self.form, text=line, bg=c["bg"], fg=c["text"], font=f["small"], anchor="w"
                     ).grid(row=self.line, column=0, columnspan=2, sticky="w", pady=1)
            self.line += 1

        app.message = tk.Label(self.form, text=app.notice, bg=c["bg"], fg=c["secondary"], font=f["small"], anchor="w",
                               justify="left", wraplength=int(app.current_size()[0] * 0.85))
        app.message.grid(row=self.line, column=0, columnspan=2, sticky="w", pady=(14, 0))
        self.line += 1
        reset = self.button(self.form, "Reset all settings", app.reset_settings)
        reset.grid(row=self.line, column=0, columnspan=2, sticky="w", pady=(6, 0))
        self.line += 1
        tk.Label(self.form, text=f"Saved in {config.SETTINGS_FILE}", bg=c["bg"], fg=c["dim"], font=f["small"],
                 anchor="w").grid(row=self.line, column=0, columnspan=2, sticky="w", pady=(8, 12))

        canvas.update_idletasks()
        for child in self.form.winfo_children():
            if isinstance(child, flow.Flow):
                child.layout(max(80, canvas.winfo_width() - int(150 * app.scale) - 2 * margin) if canvas.winfo_width() > 1 else None)
        canvas.yview_moveto(fraction)

    def wipe(self, which):
        """Two clicks: the first turns the button into 'Sure? Click again', the second empties the history."""
        if self.wipe_armed != which:
            self.wipe_armed, self.wipe_message = which, ""
            self.render()
            self.app.root.after(4000, lambda: self.disarm(which))
            return
        gone = store.delete_all(keep_pinned=which == "unpinned")
        self.wipe_armed = None
        self.wipe_message = f"Deleted {gone} clip{'' if gone == 1 else 's'}." + (" Pinned ones are kept." if which == "unpinned" else "")
        self.app.multi = []
        self.render()

    def disarm(self, which):
        """The 'Sure?' question times out: the button goes back to normal."""
        if self.wipe_armed == which and self.app.view == "settings":
            self.wipe_armed = None
            self.render()

    # ---------- numbers ----------

    def number_row(self, holder, key):
        app, c = self.app, self.app.c
        low, high = settings.LIMITS[key]
        variable = tk.StringVar(value=str(settings.get(key)))
        spin = tk.Spinbox(holder, from_=low, to=high, width=6, textvariable=variable, bg=c["search"], fg=c["text"],
                          buttonbackground=c["panel"], insertbackground=c["accent"], relief="flat", font=app.f["small"],
                          highlightthickness=1, highlightbackground=c["border"], highlightcolor=c["secondary"],
                          command=lambda: app.apply_number(key, variable))
        holder.add(spin)
        spin.bind("<Return>", lambda e: app.apply_number(key, variable))
        spin.bind("<FocusOut>", lambda e: app.apply_number(key, variable))
        self.note(holder, f"{low} to {high}")

    # ---------- tags ----------

    def tag_editor(self):
        app, c, f = self.app, self.app.c, self.app.f
        holder = self.row_plain("Tags")
        for tag in store.list_tags():
            line = tk.Frame(holder, bg=c["bg"])
            line.pack(anchor="w", pady=2)
            swatch = tk.Label(line, bg=tag["color"], width=3, relief="solid", bd=1, cursor="hand2")
            swatch.pack(side="left")
            swatch.bind("<Button-1>", lambda e, t=tag: self.recolor(t))
            variable = tk.StringVar(value=tag["name"])
            entry = tk.Entry(line, textvariable=variable, width=16, bg=c["search"], fg=c["text"],
                             insertbackground=c["accent"], relief="flat", font=f["small"], highlightthickness=1,
                             highlightbackground=c["border"], highlightcolor=c["secondary"])
            entry.pack(side="left", padx=6, ipady=2)
            entry.bind("<Return>", lambda e, t=tag, v=variable: self.rename(t, v))
            entry.bind("<FocusOut>", lambda e, t=tag, v=variable: self.rename(t, v))
            remove = tk.Label(line, text="✕", bg=c["bg"], fg=c["dim"], font=f["small"], cursor="hand2", padx=4)
            remove.pack(side="left")
            remove.bind("<Button-1>", lambda e, t=tag, w=remove: self.remove(t, w))
        add_line = tk.Frame(holder, bg=c["bg"])
        add_line.pack(anchor="w", pady=(6, 0))
        self.new_name = tk.StringVar()
        entry = tk.Entry(add_line, textvariable=self.new_name, width=16, bg=c["search"], fg=c["text"],
                         insertbackground=c["accent"], relief="flat", font=f["small"], highlightthickness=1,
                         highlightbackground=c["border"], highlightcolor=c["secondary"])
        entry.pack(side="left", ipady=2, padx=(0, 6))
        entry.bind("<Return>", lambda e: self.add())
        self.button(add_line, "New tag", self.add).pack(side="left")
        tk.Label(holder, text=self.tag_message or "click a colour to change it, type to rename", bg=c["bg"],
                 fg=c["dim"], font=f["small"]).pack(anchor="w", pady=(4, 0))

    def add(self):
        name = self.new_name.get().strip()
        color = TAG_COLORS[len(store.list_tags()) % len(TAG_COLORS)]
        self.tag_message = "" if store.add_tag(name, color) else "Type a new name that is not used yet."
        self.app.refresh_tabs()
        self.render()

    def rename(self, tag, variable):
        new = variable.get().strip()
        if new == tag["name"]:
            return
        if store.rename_tag(tag["id"], new):
            for key in ("auto_tag_links", "auto_tag_code"):   # a rule follows its tag when the tag is renamed
                if settings.get(key) == tag["name"]:
                    settings.set(key, new)
            self.tag_message = ""
            self.app.refresh_tabs()
        else:
            variable.set(tag["name"])
            self.tag_message = "That name is empty or already used."
        self.render()

    def recolor(self, tag):
        app = self.app
        app.dialog_open = True
        app.root.attributes("-topmost", False)
        try:
            chosen = colorchooser.askcolor(color=tag["color"], parent=app.root, title="Tag colour")[1]
        finally:
            app.root.attributes("-topmost", True)
            app.dialog_open = False
        if chosen:
            store.recolor_tag(tag["id"], chosen)
            app.refresh_tabs()
            self.render()

    def remove(self, tag, widget):
        """Two clicks: the first turns the cross into 'Sure?', the second removes the tag (its clips are kept)."""
        if widget.cget("text") != "Sure?":
            widget.config(text="Sure?", fg="#f0c274")
            widget.after(2500, lambda: widget.winfo_exists() and widget.config(text="✕", fg=self.app.c["dim"]))
            return
        store.delete_tag(tag["id"])
        for key in ("auto_tag_links", "auto_tag_code"):
            if settings.get(key) == tag["name"]:
                settings.set(key, "")
        if self.app.view == tag["id"]:
            self.app.view = "settings"
        self.tag_message = f"Removed {tag['name']}. Its clips are kept, untagged."
        self.app.refresh_tabs()
        self.render()
