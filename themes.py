"""Colour themes. Each theme is a dict of named colours that the window reads."""
import settings

THEMES = {
    "teal": {"label": "Teal", "bg": "#06141a", "panel": "#071a21", "row_alt": "#08202a", "sel": "#0f3a45",
             "search": "#0c2c35", "border": "#12303a", "text": "#e6fbfb", "accent": "#8ff3ff",
             "dim": "#6fa9b3", "secondary": "#4eb1b1"},
    "dark": {"label": "Dark", "bg": "#141518", "panel": "#1a1b1f", "row_alt": "#181a1d", "sel": "#2c3038",
             "search": "#23262c", "border": "#2a2d34", "text": "#e8e8ea", "accent": "#7aa2f7",
             "dim": "#8b8f98", "secondary": "#6b7280"},
    "light": {"label": "Light", "bg": "#f7f9fa", "panel": "#eef3f5", "row_alt": "#f0f4f6", "sel": "#cfe9ee",
              "search": "#e3edf0", "border": "#cdd9de", "text": "#16282d", "accent": "#0b6f82",
              "dim": "#5d7780", "secondary": "#2a8a99"},
}
CUSTOM_LABEL = "Custom"
CUSTOM_FIELDS = [("bg", "Background"), ("text", "Text"), ("accent", "Accent"), ("sel", "Selection")]


def _rgb(color):
    return int(color[1:3], 16), int(color[3:5], 16), int(color[5:7], 16)


def blend(first, second, amount):
    """Mixes two #rrggbb colours. amount 0 = first, 1 = second."""
    a, b = _rgb(first), _rgb(second)
    return "#%02x%02x%02x" % tuple(round(x + (y - x) * amount) for x, y in zip(a, b))


def from_custom(custom):
    """Builds a full theme from the four colours you pick; the rest are mixed from them."""
    bg, text, accent, sel = custom["bg"], custom["text"], custom["accent"], custom["sel"]
    return {"label": CUSTOM_LABEL, "bg": bg, "text": text, "accent": accent, "sel": sel,
            "panel": blend(bg, text, 0.03), "row_alt": blend(bg, text, 0.05),
            "search": blend(bg, sel, 0.6), "border": blend(bg, text, 0.14),
            "dim": blend(bg, text, 0.55), "secondary": blend(accent, bg, 0.35)}


def current():
    name = settings.get("theme")
    if name == "custom":
        try:
            return from_custom(settings.get("custom_colors"))
        except (ValueError, KeyError, IndexError):
            return dict(THEMES["teal"])
    return dict(THEMES.get(name, THEMES["teal"]))


def choices():
    """(key, label) for the theme buttons."""
    return [(key, theme["label"]) for key, theme in THEMES.items()] + [("custom", CUSTOM_LABEL)]
