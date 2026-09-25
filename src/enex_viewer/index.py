"""Build the read-only index: <data>/index.sqlite plus <data>/blobs/<md5>.

Every build starts from scratch into a temp file and is swapped in atomically,
so the index always mirrors the current ENEX files exactly. Attachments are
content-addressed by md5, written once, and deleted when no note uses them.
"""

import hashlib
import logging
import os
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from enex_viewer.enex import Note, iter_notes
from enex_viewer.enml import to_text

log = logging.getLogger(__name__)

SCHEMA_VERSION = "1"
INDEX_NAME = "index.sqlite"
BLOBS_NAME = "blobs"

SCHEMA = """
CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE notebooks (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    stack TEXT,
    path TEXT NOT NULL,
    note_count INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE notes (
    id TEXT PRIMARY KEY,
    guid TEXT UNIQUE,
    notebook_id TEXT NOT NULL REFERENCES notebooks(id),
    position INTEGER NOT NULL,
    title TEXT NOT NULL,
    created TEXT,
    updated TEXT,
    author TEXT,
    source_url TEXT,
    content TEXT NOT NULL
);
CREATE INDEX notes_notebook ON notes(notebook_id, position);
CREATE TABLE note_tags (
    note_id TEXT NOT NULL REFERENCES notes(id),
    tag TEXT NOT NULL,
    PRIMARY KEY (note_id, tag)
);
CREATE INDEX note_tags_tag ON note_tags(tag);
CREATE TABLE resources (
    hash TEXT PRIMARY KEY,
    mime TEXT NOT NULL,
    size INTEGER NOT NULL
);
CREATE TABLE note_resources (
    note_id TEXT NOT NULL REFERENCES notes(id),
    position INTEGER NOT NULL,
    hash TEXT NOT NULL REFERENCES resources(hash),
    mime TEXT NOT NULL,
    filename TEXT,
    PRIMARY KEY (note_id, position)
);
CREATE VIRTUAL TABLE notes_fts USING fts5(
    title, body, tokenize = 'unicode61 remove_diacritics 2'
);
"""


@dataclass(frozen=True)
class IndexStats:
    notebooks: int
    notes: int
    resources: int
    duplicate_guids: int


def enex_files(enex_dir: Path) -> list[Path]:
    """All .enex files below enex_dir, skipping hidden and macOS "._" files."""
    return sorted(
        p
        for p in enex_dir.rglob("*.enex")
        if p.is_file()
        and not any(part.startswith(".") for part in p.relative_to(enex_dir).parts)
    )


def fingerprint(enex_dir: Path) -> str:
    h = hashlib.sha256(SCHEMA_VERSION.encode())
    for p in enex_files(enex_dir):
        st = p.stat()
        rel = p.relative_to(enex_dir).as_posix()
        h.update(f"{rel}\0{st.st_size}\0{st.st_mtime_ns}\n".encode())
    return h.hexdigest()


def index_is_stale(enex_dir: Path, data_dir: Path) -> bool:
    db = data_dir / INDEX_NAME
    if not db.exists():
        return True
    try:
        with sqlite3.connect(f"file:{db}?mode=ro", uri=True) as conn:
            row = conn.execute(
                "SELECT value FROM meta WHERE key = 'fingerprint'"
            ).fetchone()
    except sqlite3.Error:
        return True
    return row is None or row[0] != fingerprint(enex_dir)


def blob_path(data_dir: Path, md5: str) -> Path:
    return data_dir / BLOBS_NAME / md5[:2] / md5


def _write_blob(data_dir: Path, md5: str, data: bytes) -> None:
    path = blob_path(data_dir, md5)
    if path.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{md5}.tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None


def _fallback_id(rel: str, position: int, note: Note) -> str:
    key = f"{rel}\0{position}\0{note.title}\0{_iso(note.created)}"
    return hashlib.sha1(key.encode()).hexdigest()[:16]


class _Builder:
    def __init__(self, conn: sqlite3.Connection, data_dir: Path) -> None:
        self.conn = conn
        self.data_dir = data_dir
        self.hashes: set[str] = set()
        self.notes = 0
        self.duplicate_guids = 0

    def add_notebook(self, enex_dir: Path, path: Path) -> None:
        rel = path.relative_to(enex_dir)
        rel_s = rel.as_posix()
        notebook_id = hashlib.sha1(rel_s.encode()).hexdigest()[:12]
        stack = rel.parent.as_posix() if rel.parent != Path(".") else None
        self.conn.execute(
            "INSERT INTO notebooks (id, name, stack, path) VALUES (?, ?, ?, ?)",
            (notebook_id, path.stem, stack, rel_s),
        )
        count = 0
        for position, note in enumerate(iter_notes(path)):
            if self._add_note(notebook_id, rel_s, position, note):
                count += 1
        self.conn.execute(
            "UPDATE notebooks SET note_count = ? WHERE id = ?", (count, notebook_id)
        )
        log.info("indexed %s: %d notes", rel_s, count)

    def _add_note(self, notebook_id: str, rel: str, position: int, note: Note) -> bool:
        note_id = note.guid or _fallback_id(rel, position, note)
        try:
            cur = self.conn.execute(
                "INSERT INTO notes (id, guid, notebook_id, position, title, created,"
                " updated, author, source_url, content)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    note_id,
                    note.guid,
                    notebook_id,
                    position,
                    note.title,
                    _iso(note.created),
                    _iso(note.updated),
                    note.author,
                    note.source_url,
                    note.content,
                ),
            )
        except sqlite3.IntegrityError:
            self.duplicate_guids += 1
            log.warning(
                "skipping duplicate note %s (%r) in %s", note_id, note.title, rel
            )
            return False
        self.conn.execute(
            "INSERT INTO notes_fts (rowid, title, body) VALUES (?, ?, ?)",
            (cur.lastrowid, note.title, to_text(note.content)),
        )
        self.conn.executemany(
            "INSERT OR IGNORE INTO note_tags (note_id, tag) VALUES (?, ?)",
            [(note_id, tag) for tag in note.tags],
        )
        for i, res in enumerate(note.resources):
            _write_blob(self.data_dir, res.hash, res.data)
            self.hashes.add(res.hash)
            self.conn.execute(
                "INSERT OR IGNORE INTO resources (hash, mime, size) VALUES (?, ?, ?)",
                (res.hash, res.mime, len(res.data)),
            )
            self.conn.execute(
                "INSERT INTO note_resources (note_id, position, hash, mime, filename)"
                " VALUES (?, ?, ?, ?, ?)",
                (note_id, i, res.hash, res.mime, res.filename),
            )
        self.notes += 1
        return True


def _collect_garbage(data_dir: Path, keep: set[str]) -> None:
    blobs = data_dir / BLOBS_NAME
    if not blobs.exists():
        return
    for path in blobs.glob("*/*"):
        if path.name not in keep:
            path.unlink()
    for sub in blobs.iterdir():
        if sub.is_dir() and not any(sub.iterdir()):
            sub.rmdir()


def build_index(enex_dir: Path, data_dir: Path) -> IndexStats:
    files = enex_files(enex_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    tmp = data_dir / f".{INDEX_NAME}.tmp"
    tmp.unlink(missing_ok=True)
    conn = sqlite3.connect(tmp)
    try:
        conn.executescript(SCHEMA)
        builder = _Builder(conn, data_dir)
        for path in files:
            builder.add_notebook(enex_dir, path)
        conn.executemany(
            "INSERT INTO meta (key, value) VALUES (?, ?)",
            [
                ("fingerprint", fingerprint(enex_dir)),
                ("schema_version", SCHEMA_VERSION),
                ("built_at", datetime.now(UTC).isoformat()),
            ],
        )
        conn.commit()
    except BaseException:
        conn.close()
        tmp.unlink(missing_ok=True)
        raise
    conn.close()
    os.replace(tmp, data_dir / INDEX_NAME)
    _collect_garbage(data_dir, builder.hashes)
    return IndexStats(
        notebooks=len(files),
        notes=builder.notes,
        resources=len(builder.hashes),
        duplicate_guids=builder.duplicate_guids,
    )
