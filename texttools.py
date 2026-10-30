"""Small changes to a clip's text on the way out ("Paste as..."). The saved clip is never changed."""
import re

TRACKING_NAMES = {"fbclid", "gclid", "dclid", "msclkid", "yclid", "mc_eid", "mc_cid", "igshid",
                  "_hsenc", "_hsmi", "ref_src", "twclid"}
URL = re.compile(r"https?://[^\s<>\"]+")
TRAILING = ".,;:!?)]}'"


def upper(text):
    return text.upper()


def lower(text):
    return text.lower()


def title_case(text):
    """Every word starts with a capital; "it's" becomes "It's", not "It'S"."""
    return re.sub(r"[^\W\d_][\w']*", lambda m: m.group().capitalize(), text)


def trim(text):
    """No spaces at the start or end of any line, and no empty lines at the start or end."""
    return "\n".join(line.strip() for line in text.strip().splitlines())


def one_line(text):
    return " ".join(text.split())


def sort_lines(text):
    return "\n".join(sorted(text.splitlines(), key=str.casefold))


def _is_tracking(name):
    name = name.lower()
    return name.startswith("utm_") or name in TRACKING_NAMES


def _clean_url(url):
    tail = ""
    while url and url[-1] in TRAILING:
        tail = url[-1] + tail
        url = url[:-1]
    base, hash_mark, fragment = url.partition("#")
    path, question, query = base.partition("?")
    if question:
        kept = [part for part in query.split("&") if part and not _is_tracking(part.split("=", 1)[0])]
        path = path + ("?" + "&".join(kept) if kept else "")
    return path + (hash_mark + fragment if hash_mark else "") + tail


def clean_links(text):
    """Removes tracking bits (utm_..., fbclid, gclid and so on) from every link in the text."""
    return URL.sub(lambda match: _clean_url(match.group()), text)


# (key, name in the menu, function)
TOOLS = [("upper", "UPPERCASE", upper), ("lower", "lowercase", lower), ("title", "Title Case", title_case),
         ("trim", "Trim spaces", trim), ("oneline", "On one line", one_line),
         ("links", "Clean links", clean_links), ("sort", "Sort lines A-Z", sort_lines)]


def apply(key, text):
    for tool_key, _, function in TOOLS:
        if tool_key == key:
            return function(text)
    return text
