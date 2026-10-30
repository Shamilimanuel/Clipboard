"""A small window to change a clip's text before pasting it, or to save the change as a new clip."""
import tkinter as tk

import look
import store


class ClipEditor:
    def __init__(self, app, text, show=True):
        self.app, self.closed = app, False
        c = app.c
        top = self.top = tk.Toplevel(app.root)
        top.withdraw()
        top.title("Edit clip")
        top.configure(bg=c["bg"])
        top.attributes("-topmost", True)
        top.protocol("WM_DELETE_WINDOW", self.close)

        self.text = tk.Text(top, width=64, height=14, wrap="word", undo=True, bg=c["search"], fg=c["text"],
                            insertbackground=c["accent"], relief="flat", font=app.f["base"], padx=10, pady=8,
                            highlightthickness=1, highlightbackground=c["border"], highlightcolor=c["secondary"],
                            selectbackground=c["sel"], selectforeground=c["accent"])
        self.text.pack(fill="both", expand=True, padx=12, pady=(12, 8))
        self.text.insert("1.0", text)

        bar = tk.Frame(top, bg=c["bg"])
        bar.pack(fill="x", padx=12, pady=(0, 12))
        ctx = look.Context(app.root, colors=c)
        ctx.button(bar, "Paste this", self.paste, active=True, bg=c["bg"]).pack(side="left")
        ctx.button(bar, "Save as new clip", self.save_new, bg=c["bg"]).pack(side="left", padx=6)
        ctx.button(bar, "Cancel", self.close, bg=c["bg"]).pack(side="left")
        tk.Label(bar, text="Ctrl+Enter paste   Esc cancel", bg=c["bg"], fg=c["dim"], font=app.f["small"]
                 ).pack(side="right")
        top.bind("<Escape>", lambda e: self.close())
        top.bind("<Control-Return>", lambda e: self.paste())

        top.update_idletasks()
        screen_w, screen_h = top.winfo_screenwidth(), top.winfo_screenheight()
        x = max(0, (screen_w - top.winfo_reqwidth()) // 2)
        y = max(0, (screen_h - top.winfo_reqheight()) // 3)
        top.geometry(f"+{x}+{y}")
        if show:
            top.deiconify()
            top.lift()
            top.focus_force()
            self.text.focus_set()

    def value(self):
        return self.text.get("1.0", "end-1c")

    def paste(self):
        text = self.value()
        self.close()
        if text.strip():
            self.app.paste_text(text)

    def save_new(self):
        text = self.value()
        if text.strip():
            store.add_text(text, "clipboard.exe")   # it shows up at the top of the list the next time you open it
        self.close()

    def close(self):
        if not self.closed:
            self.closed = True
            self.app.editor = None
            try:
                self.top.destroy()
            except tk.TclError:
                pass
