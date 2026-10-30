"""The clip history, kept in a small SQLite database file."""
import hashlib
import sqlite3
import time
from contextlib import closing

import config
import settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS tags (
    id    INTEGER PRIMARY KEY,
    name  TEXT UNIQUE NOT NULL,
    color TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS clips (
    id      INTEGER PRIMARY KEY,
    kind    TEXT NOT NULL DEFAULT 'text',      -- 'text' or 'image'
    content TEXT NOT NULL,                     -- the text, or the image file name
    hash    TEXT NOT NULL UNIQUE,              -- same content = same clip
    created REAL NOT NULL,                     -- last copied / pasted (moves it to the top)
    pinned  INTEGER NOT NULL DEFAULT 0,
    tag_id  INTEGER REFERENCES tags(id) ON DELETE SET NULL,
    uses    INTEGER NOT NULL DEFAULT 0,
    source  TEXT NOT NULL DEFAULT ''           -- the program it was copied from, e.g. chrome.exe
);
CREATE INDEX IF NOT EXISTS idx_clips_created ON clips(created);
"""


def connect():
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(config.DB_FILE, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def init():
    config.IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    with closing(connect()) as conn, conn:
        conn.executescript(SCHEMA)
        if "source" not in [row["name"] for row in conn.execute("PRAGMA table_info(clips)")]:
            conn.execute("ALTER TABLE clips ADD COLUMN source TEXT NOT NULL DEFAULT ''")  # history from before this existed
        for name, color in config.DEFAULT_TAGS:
            conn.execute("INSERT OR IGNORE INTO tags (name, color) VALUES (?, ?)", (name, color))


def text_hash(text):
    return hashlib.sha1(text.encode("utf-8", "surrogatepass")).hexdigest()


def add_clip(kind, content, content_hash, source="", tag_name=None):
    """Saves a clip, or moves it to the top if we already have it. Returns its id.
    A tag is only given to a clip that is new: one you tagged (or untagged) yourself is never changed."""
    now = time.time()
    with closing(connect()) as conn, conn:
        row = conn.execute("SELECT id FROM clips WHERE hash = ?", (content_hash,)).fetchone()
        if row:
            conn.execute("UPDATE clips SET created = ?, source = CASE WHEN ? != '' THEN ? ELSE source END WHERE id = ?",
                         (now, source, source, row["id"]))
            return row["id"]
        tag = conn.execute("SELECT id FROM tags WHERE name = ?", (tag_name,)).fetchone() if tag_name else None
        cursor = conn.execute(
            "INSERT INTO clips (kind, content, hash, created, source, tag_id) VALUES (?, ?, ?, ?, ?, ?)",
            (kind, content, content_hash, now, source, tag["id"] if tag else None))
        clip_id = cursor.lastrowid
    prune()
    return clip_id


def add_text(text, source="", tag_name=None):
    return add_clip("text", text, text_hash(text), source, tag_name)


def get_clip(clip_id):
    with closing(connect()) as conn:
        row = conn.execute("SELECT * FROM clips WHERE id = ?", (clip_id,)).fetchone()
        return dict(row) if row else None


def list_clips(query="", tag_id=None, pinned_only=False, limit=config.LIST_LIMIT, kind=None, unpinned_only=False):
    """Pinned clips first, then newest first. Search only looks at text clips. `kind` keeps only 'text' or 'image'.
    `unpinned_only` leaves the pinned clips out (the All tab: pinned clips live in the Pinned tab)."""
    like = "%" + query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
    sql = """
        SELECT c.*, t.name AS tag_name, t.color AS tag_color
        FROM clips c LEFT JOIN tags t ON t.id = c.tag_id
        WHERE (? = '' OR (c.kind = 'text' AND c.content LIKE ? ESCAPE '\\') OR c.source LIKE ? ESCAPE '\\')
          AND (? IS NULL OR c.tag_id = ?)
          AND (? = 0 OR c.pinned = 1)
          AND (? = 0 OR c.pinned = 0)
          AND (? IS NULL OR c.kind = ?)
        ORDER BY c.pinned DESC, c.created DESC
        LIMIT ?"""
    with closing(connect()) as conn:
        return [dict(row) for row in conn.execute(
            sql, (query, like, like, tag_id, tag_id, 1 if pinned_only else 0, 1 if unpinned_only else 0, kind, kind, limit))]


def list_tags():
    with closing(connect()) as conn:
        return [dict(row) for row in conn.execute("SELECT * FROM tags ORDER BY id")]


def add_tag(name, color):
    """Adds a tag. Returns True, or False if the name is empty or already used."""
    name = name.strip()
    if not name:
        return False
    with closing(connect()) as conn, conn:
        if conn.execute("SELECT 1 FROM tags WHERE lower(name) = lower(?)", (name,)).fetchone():
            return False  # "Zed" and "zed" count as the same name
        return conn.execute("INSERT OR IGNORE INTO tags (name, color) VALUES (?, ?)", (name, color)).rowcount == 1


def rename_tag(tag_id, name):
    """Returns True, or False if the name is empty or another tag already has it."""
    name = name.strip()
    if not name:
        return False
    with closing(connect()) as conn, conn:
        taken = conn.execute("SELECT id FROM tags WHERE lower(name) = lower(?) AND id != ?", (name, tag_id)).fetchone()
        if taken:
            return False
        conn.execute("UPDATE tags SET name = ? WHERE id = ?", (name, tag_id))
        return True


def recolor_tag(tag_id, color):
    with closing(connect()) as conn, conn:
        conn.execute("UPDATE tags SET color = ? WHERE id = ?", (color, tag_id))


def delete_tag(tag_id):
    """Removes a tag. Its clips are kept, just untagged."""
    with closing(connect()) as conn, conn:
        conn.execute("UPDATE clips SET tag_id = NULL WHERE tag_id = ?", (tag_id,))
        conn.execute("DELETE FROM tags WHERE id = ?", (tag_id,))


def toggle_pin(clip_id):
    with closing(connect()) as conn, conn:
        conn.execute("UPDATE clips SET pinned = 1 - pinned WHERE id = ?", (clip_id,))


def set_tag(clip_id, tag_id):
    with closing(connect()) as conn, conn:
        conn.execute("UPDATE clips SET tag_id = ? WHERE id = ?", (tag_id, clip_id))


def touch(clip_id):
    """Called when a clip is pasted: moves it to the top and counts the use."""
    with closing(connect()) as conn, conn:
        conn.execute("UPDATE clips SET created = ?, uses = uses + 1 WHERE id = ?", (time.time(), clip_id))


def delete(clip_id):
    with closing(connect()) as conn, conn:
        row = conn.execute("SELECT kind, content FROM clips WHERE id = ?", (clip_id,)).fetchone()
        conn.execute("DELETE FROM clips WHERE id = ?", (clip_id,))
    if row and row["kind"] == "image":
        (config.IMAGE_DIR / row["content"]).unlink(missing_ok=True)


def delete_all(keep_pinned=False):
    """Empties the history (pictures included). With keep_pinned the pinned clips stay. Returns how many went."""
    where = "WHERE pinned = 0" if keep_pinned else ""
    with closing(connect()) as conn, conn:
        gone = conn.execute(f"SELECT kind, content FROM clips {where}").fetchall()
        conn.execute(f"DELETE FROM clips {where}")
    for row in gone:
        if row["kind"] == "image":
            (config.IMAGE_DIR / row["content"]).unlink(missing_ok=True)
    return len(gone)


def prune():
    """Keeps the newest MAX_CLIPS unpinned clips; pinned clips are never deleted."""
    with closing(connect()) as conn, conn:
        old = conn.execute(
            "SELECT id, kind, content FROM clips WHERE pinned = 0 "
            "ORDER BY created DESC LIMIT -1 OFFSET ?", (settings.get("max_clips"),)).fetchall()
        for row in old:
            conn.execute("DELETE FROM clips WHERE id = ?", (row["id"],))
    for row in old:
        if row["kind"] == "image":
            (config.IMAGE_DIR / row["content"]).unlink(missing_ok=True)
