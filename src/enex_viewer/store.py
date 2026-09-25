"""Read-only queries over index.sqlite, returning Pydantic models."""

import html
import re
import sqlite3
from pathlib import Path
from typing import Any
from urllib.parse import quote

from pydantic import BaseModel

from enex_viewer.render import Attachment

_TERM = re.compile(r"\w+", re.UNICODE)
_MARK_OPEN, _MARK_CLOSE = "\x02", "\x03"


class IndexMissingError(Exception):
    pass


class Notebook(BaseModel):
    id: str
    name: str
    stack: str | None
    note_count: int


class Tag(BaseModel):
    name: str
    count: int


class NoteSummary(BaseModel):
    id: str
    title: str
    notebook_id: str
    created: str | None
    updated: str | None
    snippet_html: str | None = None  # search hit excerpt, HTML-escaped, <mark>ed


class NotePage(BaseModel):
    items: list[NoteSummary]
    total: int
    limit: int
    offset: int


class AttachmentInfo(BaseModel):
    hash: str
    filename: str | None
    mime: str
    size: int
    url: str


class NoteDetail(BaseModel):
    id: str
    guid: str | None
    title: str
    notebook: Notebook
    created: str | None
    updated: str | None
    author: str | None
    source_url: str | None
    tags: list[str]
    attachments: list[AttachmentInfo]
    content_url: str


def file_url(md5: str, filename: str | None = None) -> str:
    return f"/files/{md5}/{quote(filename)}" if filename else f"/files/{md5}"


def fts_query(q: str) -> str | None:
    """User input -> FTS5 query: every word must match, as a prefix.

    Words are quoted, so FTS5 operators and syntax in the input are inert.
    """
    terms = _TERM.findall(q)
    return " ".join(f'"{t}"*' for t in terms) or None


def _snippet_html(raw: str) -> str:
    escaped = html.escape(raw)
    return escaped.replace(_MARK_OPEN, "<mark>").replace(_MARK_CLOSE, "</mark>")


class Store:
    def __init__(self, db_path: Path) -> None:
        if not db_path.exists():
            raise IndexMissingError(str(db_path))
        self.conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        self.conn.row_factory = sqlite3.Row

    def close(self) -> None:
        self.conn.close()

    def _one(self, sql: str, *params: Any) -> sqlite3.Row | None:
        return self.conn.execute(sql, params).fetchone()

    def meta(self, key: str) -> str | None:
        row = self._one("SELECT value FROM meta WHERE key = ?", key)
        return row["value"] if row else None

    def note_count(self) -> int:
        row = self._one("SELECT count(*) AS n FROM notes")
        return int(row["n"]) if row else 0

    def notebooks(self) -> list[Notebook]:
        rows = self.conn.execute(
            "SELECT id, name, stack, note_count FROM notebooks"
            " ORDER BY stack IS NOT NULL, stack COLLATE NOCASE, name COLLATE NOCASE"
        )
        return [Notebook(**dict(r)) for r in rows]

    def notebook(self, notebook_id: str) -> Notebook | None:
        row = self._one(
            "SELECT id, name, stack, note_count FROM notebooks WHERE id = ?",
            notebook_id,
        )
        return Notebook(**dict(row)) if row else None

    def tags(self) -> list[Tag]:
        rows = self.conn.execute(
            "SELECT tag AS name, count(*) AS count FROM note_tags"
            " GROUP BY tag ORDER BY tag COLLATE NOCASE"
        )
        return [Tag(**dict(r)) for r in rows]

    def notes(
        self,
        *,
        notebook_id: str | None = None,
        tag: str | None = None,
        q: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> NotePage:
        where: list[str] = []
        params: list[Any] = []
        if notebook_id:
            where.append("n.notebook_id = ?")
            params.append(notebook_id)
        if tag:
            where.append("n.id IN (SELECT note_id FROM note_tags WHERE tag = ?)")
            params.append(tag)
        match = fts_query(q) if q else None
        if q and match is None:
            return NotePage(items=[], total=0, limit=limit, offset=offset)
        if match:
            source = "notes_fts f JOIN notes n ON n.rowid = f.rowid"
            where.append("notes_fts MATCH ?")
            params.append(match)
            snippet = f"snippet(notes_fts, 1, '{_MARK_OPEN}', '{_MARK_CLOSE}', '…', 16)"
            order = "bm25(notes_fts, 5.0, 1.0)"
        else:
            source = "notes n"
            snippet = "NULL"
            order = "coalesce(n.updated, n.created) DESC, n.title COLLATE NOCASE"
        clause = f"WHERE {' AND '.join(where)}" if where else ""
        total_row = self._one(f"SELECT count(*) AS n FROM {source} {clause}", *params)
        rows = self.conn.execute(
            f"SELECT n.id, n.title, n.notebook_id, n.created, n.updated,"
            f" {snippet} AS snippet FROM {source} {clause}"
            f" ORDER BY {order} LIMIT ? OFFSET ?",
            [*params, limit, offset],
        )
        items = [
            NoteSummary(
                id=r["id"],
                title=r["title"],
                notebook_id=r["notebook_id"],
                created=r["created"],
                updated=r["updated"],
                snippet_html=_snippet_html(r["snippet"]) if r["snippet"] else None,
            )
            for r in rows
        ]
        total = int(total_row["n"]) if total_row else 0
        return NotePage(items=items, total=total, limit=limit, offset=offset)

    def attachments(self, note_id: str) -> list[Attachment]:
        rows = self.conn.execute(
            "SELECT nr.hash, nr.mime, nr.filename, r.size FROM note_resources nr"
            " JOIN resources r USING (hash) WHERE nr.note_id = ? ORDER BY nr.position",
            (note_id,),
        )
        return [
            Attachment(r["hash"], r["mime"], r["filename"], r["size"]) for r in rows
        ]

    def note(self, note_id: str) -> NoteDetail | None:
        row = self._one(
            "SELECT id, guid, title, notebook_id, created, updated, author, source_url"
            " FROM notes WHERE id = ?",
            note_id,
        )
        if row is None:
            return None
        notebook = self.notebook(row["notebook_id"])
        assert notebook is not None
        tags = [
            r["tag"]
            for r in self.conn.execute(
                "SELECT tag FROM note_tags WHERE note_id = ?"
                " ORDER BY tag COLLATE NOCASE",
                (note_id,),
            )
        ]
        attachments = [
            AttachmentInfo(
                hash=a.hash,
                filename=a.filename,
                mime=a.mime,
                size=a.size,
                url=file_url(a.hash, a.filename),
            )
            for a in self.attachments(note_id)
        ]
        return NoteDetail(
            id=row["id"],
            guid=row["guid"],
            title=row["title"],
            notebook=notebook,
            created=row["created"],
            updated=row["updated"],
            author=row["author"],
            source_url=row["source_url"],
            tags=tags,
            attachments=attachments,
            content_url=f"/notes/{row['id']}/content",
        )

    def note_source(self, note_id: str) -> tuple[str, str | None] | None:
        """(ENML content, source URL) for rendering."""
        row = self._one("SELECT content, source_url FROM notes WHERE id = ?", note_id)
        return (row["content"], row["source_url"]) if row else None

    def resolve_guid(self, guid: str) -> str | None:
        row = self._one("SELECT id FROM notes WHERE guid = ?", guid.lower())
        return row["id"] if row else None

    def resource_mime(self, md5: str) -> str | None:
        row = self._one("SELECT mime FROM resources WHERE hash = ?", md5)
        return row["mime"] if row else None
