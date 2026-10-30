"""The looks: Flat, Raised and Glass (copied from Snipper, with row cards added for the clip list).

Raised and Glass draw their buttons and bars as pictures (3x bigger, then shrunk, so the edges are smooth)
with a soft shadow, a lit top edge, and a pressed-in version for the moment you click. Flat is the
plain version. Nothing here talks to the screen except the small Button classes at the bottom.
"""
import tkinter as tk

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps, ImageTk

import settings
import themes

S = 3                                                  # drawing is done 3x bigger and shrunk
WHITE, BLACK = "#ffffff", "#000000"


# ---------- small helpers ----------

def mix(first, second, amount):
    return themes.blend(first, second, amount)


def rgba(color, alpha=255):
    r, g, b = themes._rgb(color)
    return (r, g, b, alpha)


_fonts = {}


def font(px, symbol=False, bold=False):
    """A Windows font at this pixel size (Segoe UI for words, Segoe UI Symbol for arrows and shapes)."""
    key = (px, symbol, bold)
    if key not in _fonts:
        names = ("seguisym.ttf", "segoeui.ttf") if symbol else (("segoeuib.ttf", "arialbd.ttf") if bold else ("segoeui.ttf", "arial.ttf"))
        loaded = None
        for name in names:
            try:
                loaded = ImageFont.truetype(name, px)
                break
            except OSError:
                continue
        _fonts[key] = loaded or ImageFont.load_default()
    return _fonts[key]


def runs(text):
    """Splits text into pieces that use the symbol font (characters from U+2190 up) or the normal font."""
    pieces, current, current_symbol = [], "", None
    for char in text:
        symbol = ord(char) >= 0x2190
        if current and symbol != current_symbol:
            pieces.append((current, current_symbol))
            current = ""
        current += char
        current_symbol = symbol
    if current:
        pieces.append((current, current_symbol))
    return pieces


def text_length(text, px, bold=False):
    return sum(font(px, symbol, bold).getlength(piece) for piece, symbol in runs(text))


def draw_text(draw, x, y_middle, text, fill, px, bold=False):
    for piece, symbol in runs(text):
        chosen = font(px, symbol, bold)
        draw.text((x, y_middle), piece, font=chosen, fill=fill, anchor="lm")
        x += chosen.getlength(piece)


def rounded_mask(size, radius):
    mask = Image.new("L", size, 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, size[0] - 1, size[1] - 1], radius=radius, fill=255)
    return mask


def gradient(size, top, bottom):
    ramp = Image.linear_gradient("L").resize(size)
    return ImageOps.colorize(ramp, black=top[:3], white=bottom[:3]).convert("RGBA")


def over(layer, painter):
    """Lets `painter` draw with see-through colours that blend with what is already there."""
    sheet = Image.new("RGBA", layer.size, (0, 0, 0, 0))
    painter(ImageDraw.Draw(sheet))
    layer.alpha_composite(sheet)


def paint_surface(layer, box, radius, top, bottom, shadow=None, border=None, highlight=0, backdrop=None, frost=0.0):
    """A rounded surface on an RGBA layer: optional soft shadow, gradient (or frosted glass over `backdrop`),
    a thin border and a lit top edge. box is in layer pixels."""
    x1, y1, x2, y2 = box
    width, height = x2 - x1 + 1, y2 - y1 + 1
    if shadow:
        blur, offset, alpha = shadow
        reach = int(blur * 3) + 2   # the shadow fades out within about 3x the blur: only that small area needs blurring
        sx, sy = max(0, x1 - reach), max(0, y1 - reach)
        ex, ey = min(layer.width, x2 + reach + 1), min(layer.height, y2 + offset + reach + 1)
        sheet = Image.new("RGBA", (ex - sx, ey - sy), (0, 0, 0, 0))
        ImageDraw.Draw(sheet).rounded_rectangle([x1 - sx, y1 + offset - sy, x2 - sx, y2 + offset - sy],
                                                radius=radius, fill=(0, 0, 0, alpha))
        layer.alpha_composite(sheet.filter(ImageFilter.GaussianBlur(blur)), dest=(sx, sy))
    body = gradient((width, height), top, bottom)
    if backdrop is not None:  # frosted glass: the blurred picture behind, tinted, with the gradient on top
        blurred = backdrop.crop((x1, y1, x1 + width, y1 + height)).convert("RGBA")
        body = Image.blend(blurred, Image.new("RGBA", blurred.size, top[:3] + (255,)), frost)
        sheen = Image.new("RGBA", body.size, (255, 255, 255, 255))   # a soft white light fading down from the top edge
        sheen.putalpha(Image.linear_gradient("L").resize(body.size).point(lambda v: int((255 - v) * 0.16)))
        body.alpha_composite(sheen)
    body.putalpha(rounded_mask((width, height), radius))
    layer.alpha_composite(body, dest=(x1, y1))
    if border:
        over(layer, lambda d: d.rounded_rectangle([x1, y1, x2, y2], radius=radius, outline=border, width=S))
    if highlight:
        over(layer, lambda d: d.line([(x1 + radius, y1 + S), (x2 - radius, y1 + S)], fill=(255, 255, 255, highlight), width=S))


# ---------- one button ----------

def button_colours(look, colors, state, active):
    base = colors["sel"] if active else colors["panel"]
    if look == "glass":
        top, bottom = mix(base, WHITE, 0.24), mix(base, colors["accent"], 0.07)
    else:
        top, bottom = mix(base, WHITE, 0.10), mix(base, BLACK, 0.18)
    if state == "hover":
        top, bottom = mix(top, WHITE, 0.10), mix(bottom, WHITE, 0.08)
    elif state == "pressed":
        top, bottom = mix(base, BLACK, 0.34), mix(base, BLACK, 0.12)
    return base, top, bottom


def paint_button(layer, box, text, state, active, look, colors, text_px, dpi, bold=False):
    """Draws one button into `box` (layer pixels)."""
    x1, y1, x2, y2 = box
    if look == "flat":
        base = colors["sel"] if (active or state != "normal") else colors["panel"]
        if state == "pressed":
            base = mix(colors["sel"], colors["accent"], 0.22)  # a click is visible even in the plain look
        paint_surface(layer, box, int((y2 - y1) * 0.2), rgba(base), rgba(base))
    else:
        base, top, bottom = button_colours(look, colors, state, active)
        pressed = state == "pressed"
        shadow = None if pressed else (round(2.0 * dpi * S), round(1.6 * dpi * S), 130)
        paint_surface(layer, box, int((y2 - y1) * 0.30), rgba(top), rgba(bottom), shadow=shadow,
                      border=rgba(mix(base, WHITE, 0.20), 170), highlight=0 if pressed else (110 if look == "glass" else 70))
    colour = colors["accent"] if active else colors["text"]
    width = text_length(text, text_px * S, bold)
    draw_text(ImageDraw.Draw(layer), x1 + ((x2 - x1) - width) / 2, (y1 + y2) / 2 + (S if state == "pressed" and look != "flat" else 0),
              text, rgba(colour), text_px * S, bold)


def button_metrics(text, text_px, pad_x, pad_y, dpi):
    return (round(text_length(text, text_px) + 2 * pad_x * dpi), round(text_px * 1.3 + 2 * pad_y * dpi))


_images = {}


def button_image(ctx, text, state, active, pt, pad_x, pad_y, bg):
    """The finished picture of one button, on a plain background colour."""
    key = (ctx.look, tuple(sorted(ctx.colors.items())), text, state, active, pt, pad_x, pad_y, bg, round(ctx.dpi, 2))
    if key not in _images:
        if len(_images) > 500:
            _images.clear()
        text_px = ctx.px(pt)
        width, height = button_metrics(text, text_px, pad_x, pad_y, ctx.dpi)
        margin = 0 if ctx.look == "flat" else round(5 * ctx.dpi)
        layer = Image.new("RGBA", ((width + 2 * margin) * S, (height + 2 * margin) * S), (0, 0, 0, 0))
        paint_button(layer, (margin * S, margin * S, (margin + width) * S - 1, (margin + height) * S - 1), text, state, active,
                     ctx.look, ctx.colors, text_px, ctx.dpi)
        small = layer.resize((width + 2 * margin, height + 2 * margin), Image.LANCZOS)
        flat = Image.alpha_composite(Image.new("RGBA", small.size, rgba(bg)), small).convert("RGB")
        _images[key] = ImageTk.PhotoImage(flat)
    return _images[key]


# ---------- a clip row drawn as a card ----------

_cards = {}


def card_colours(look, colors, state):
    """(base, top, bottom, border, border alpha) of a row card in one of its states:
    normal, hover, selected (the highlighted row) or picked (chosen for pasting several)."""
    panel, accent = colors["panel"], colors["accent"]
    base = {"normal": panel, "hover": mix(panel, accent, 0.10),
            "selected": colors["sel"], "picked": mix(colors["sel"], accent, 0.34)}[state]
    if look == "glass":
        top, bottom = mix(base, WHITE, 0.20), mix(base, accent, 0.06)
    else:
        top, bottom = mix(base, WHITE, 0.07), mix(base, BLACK, 0.15)
    if state in ("selected", "picked"):
        return base, top, bottom, rgba(accent), 235 if state == "selected" else 255
    return base, top, bottom, rgba(mix(base, WHITE, 0.14)), 150


def card_picture(ctx, width, height, state, bg):
    """One row card as a finished PIL picture, `width` x `height` pixels, on the plain window colour `bg`."""
    look, colors, dpi = ctx.look, ctx.colors, ctx.dpi
    base, top, bottom, border, border_alpha = card_colours(look, colors, state)
    mx, my = (round(6 * dpi), round(2 * dpi)) if look == "flat" else (round(8 * dpi), round(3 * dpi))
    layer = Image.new("RGBA", (width * S, height * S), (0, 0, 0, 0))
    box = (mx * S, my * S, (width - mx) * S - 1, (height - my) * S - 1)
    radius = int((box[3] - box[1]) * 0.22)
    if look == "flat":
        paint_surface(layer, box, radius, rgba(base), rgba(base),
                      border=rgba(colors["accent"], 200) if state in ("selected", "picked") else None)
    else:
        paint_surface(layer, box, radius, rgba(top), rgba(bottom),
                      shadow=(round(1.6 * dpi * S), round(1.2 * dpi * S), 110),
                      border=border[:3] + (border_alpha,), highlight=90 if look == "glass" else 55)
    small = layer.resize((width, height), Image.LANCZOS)
    return Image.alpha_composite(Image.new("RGBA", small.size, rgba(bg)), small).convert("RGB")


def card_image(ctx, width, height, state, bg):
    """The same picture ready for Tk. Only a handful exist (one per state and width), so rows are cheap to rebuild."""
    key = (ctx.look, tuple(sorted(ctx.colors.items())), width, height, state, bg, round(ctx.dpi, 2))
    if key not in _cards:
        if len(_cards) > 400:
            _cards.clear()
        _cards[key] = ImageTk.PhotoImage(card_picture(ctx, width, height, state, bg))
    return _cards[key]


# ---------- the context and the button widgets ----------

class Context:
    """The look, the colours and the screen's scaling, gathered in one place."""

    def __init__(self, root, look=None, colors=None):
        self.look = look or settings.get("look")
        self.colors = colors or themes.current()
        self.dpi = root.winfo_fpixels("1i") / 96

    def px(self, points):
        return max(8, round(points * 96 / 72 * self.dpi))

    def button(self, parent, text, command, active=False, bg=None, pt=10, pad_x=11, pad_y=5):
        """A button in this look: a drawn picture for Raised and Glass, a plain label for Flat."""
        cls = FlatButton if self.look == "flat" else PictureButton
        return cls(parent, self, text, command, active, bg, pt, pad_x, pad_y)


class FlatButton(tk.Label):
    def __init__(self, parent, ctx, text, command, active, bg, pt, pad_x, pad_y):
        super().__init__(parent, text=text, font=("Segoe UI", pt), padx=pad_x - 1, pady=pad_y - 2, cursor="hand2", bd=0)
        self.ctx, self.command, self.active, self.hovered = ctx, command, active, False
        self.bind("<Enter>", lambda e: self.update_state(hovered=True))
        self.bind("<Leave>", lambda e: self.update_state(hovered=False))
        self.bind("<Button-1>", lambda e: self.command())
        self.update_state()

    def update_state(self, hovered=None):
        if hovered is not None:
            self.hovered = hovered
        c = self.ctx.colors
        self.config(bg=c["sel"] if (self.active or self.hovered) else c["panel"], fg=c["accent"] if self.active else c["text"])

    def set_active(self, active):
        self.active = active
        self.update_state()

    def set_text(self, text):
        self.config(text=text)


class PictureButton(tk.Label):
    """A button drawn as a picture, with a hover look and a pressed-in look."""

    def __init__(self, parent, ctx, text, command, active, bg, pt, pad_x, pad_y):
        self.background = bg or parent.cget("bg")
        super().__init__(parent, bd=0, highlightthickness=0, bg=self.background, cursor="hand2")
        self.ctx, self.text, self.command, self.active = ctx, text, command, active
        self.pt, self.pad_x, self.pad_y = pt, pad_x, pad_y
        self.state = "normal"
        self.bind("<Enter>", lambda e: self.set_state("hover"))
        self.bind("<Leave>", lambda e: self.set_state("normal"))
        self.bind("<ButtonPress-1>", lambda e: self.set_state("pressed"))
        self.bind("<ButtonRelease-1>", self.released)
        self.redraw()

    def redraw(self):
        self.picture = button_image(self.ctx, self.text, self.state, self.active, self.pt, self.pad_x, self.pad_y, self.background)
        self.config(image=self.picture)

    def set_state(self, state):
        if state != self.state:
            self.state = state
            self.redraw()

    def released(self, event):
        inside = 0 <= event.x < self.winfo_width() and 0 <= event.y < self.winfo_height()
        self.set_state("hover" if inside else "normal")
        if inside:
            self.command()

    def set_active(self, active):
        self.active = active
        self.redraw()

    def set_text(self, text):
        self.text = text
        self.redraw()
