"""Guesses what a copied text is, so links and code can be tagged without any clicking."""
import re

import settings

LINE = re.compile(r"^(https?://|www\.)\S+$", re.I)
CODE_START = re.compile(r"^\s*(def |class |import |from \S+ import |function |const |let |var |public |private |"
                        r"#include|SELECT |return\b|if ?\(|for ?\(|while ?\(|</?\w+[^>]*>)", re.M)
CODE_END = (";", "{", "}", "):", "=>", "->")


def looks_like_links(text):
    lines = [line.strip() for line in text.strip().splitlines() if line.strip()]
    return 0 < len(lines) <= 20 and all(LINE.match(line) for line in lines)


def looks_like_code(text):
    """A cautious guess: it needs two separate signs before it says yes."""
    if len(text) < 12:
        return False
    lines = text.splitlines()
    score = 0
    if CODE_START.search(text):
        score += 1
    if sum(1 for line in lines if line.rstrip().endswith(CODE_END)) >= 2:
        score += 1
    if sum(1 for line in lines if line.startswith(("    ", "\t"))) >= 2:
        score += 1
    if sum(text.count(char) for char in "{}();=<>[]") / len(text) > 0.05:
        score += 1
    return score >= 2


def tag_name(text):
    """The tag a new text should get (from the Settings choices), or None."""
    links, code = settings.get("auto_tag_links"), settings.get("auto_tag_code")
    if links and looks_like_links(text):
        return links
    if code and looks_like_code(text):
        return code
    return None
