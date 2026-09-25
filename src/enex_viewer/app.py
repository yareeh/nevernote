"""FastAPI app: JSON API, sandboxed note bodies and attachment files."""

import re
from collections.abc import Iterator
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, HTMLResponse

from enex_viewer.index import INDEX_NAME, blob_path
from enex_viewer.render import render
from enex_viewer.store import (
    IndexMissingError,
    Notebook,
    NoteDetail,
    NotePage,
    Store,
    Tag,
    file_url,
)

_MD5 = re.compile(r"^[0-9a-f]{32}$")

# Types a browser shows without running any script; everything else (SVG, HTML,
# XML, ...) is served under a CSP sandbox in case someone opens it directly.
_PASSIVE = re.compile(
    r"^(application/pdf|image/(png|jpeg|gif|webp|bmp|avif|tiff)|video/.*|audio/.*)$"
)
_FILE_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "Cache-Control": "public, max-age=31536000, immutable",  # content-addressed
}
_SANDBOX_FILE_CSP = (
    "sandbox; default-src 'none'; img-src data:; style-src 'unsafe-inline'"
)

# Note bodies are standalone documents shown in an <iframe>. No script can run,
# remote images/fonts are allowed, links may open new tabs or (on click)
# navigate the viewer to another note.
_NOTE_CSP = "; ".join(
    [
        "default-src 'none'",
        "script-src 'none'",
        "img-src * data:",
        "media-src *",
        "font-src * data:",
        "style-src 'unsafe-inline'",
        "base-uri 'none'",
        "form-action 'none'",
        "frame-ancestors 'self'",
        "sandbox allow-popups allow-popups-to-escape-sandbox"
        " allow-top-navigation-by-user-activation",
    ]
)
_NOTE_CSS = """
html { background: #fff; color: #1f2328; }
body { margin: 0; padding: 20px 24px 48px; font: 15px/1.6 -apple-system,
  BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
  overflow-wrap: anywhere; }
img, video { max-width: 100%; height: auto; }
pre { white-space: pre-wrap; }
table { border-collapse: collapse; max-width: 100%; }
td, th { vertical-align: top; }
a { color: #0969da; }
.en-attachment { display: inline-block; margin: 4px 0; padding: 6px 10px;
  border: 1px solid #d0d7de; border-radius: 6px; background: #f6f8fa;
  text-decoration: none; }
.en-size { color: #59636e; }
.en-attachments { margin-top: 32px; border-top: 1px solid #d0d7de; }
.en-attachments ul { list-style: none; padding: 0; }
.en-missing, .en-crypt { color: #9a6700; font-style: italic; }
.en-link-unresolved { text-decoration: underline dotted; cursor: help; }
"""


def get_store(request: Request) -> Iterator[Store]:
    """One read-only connection per request."""
    try:
        store = Store(request.app.state.db_path)
    except IndexMissingError:
        raise HTTPException(503, "Index not built yet") from None
    try:
        yield store
    finally:
        store.close()


StoreDep = Annotated[Store, Depends(get_store)]


def create_app(data_dir: Path) -> FastAPI:
    app = FastAPI(title="ENEX viewer", docs_url="/api/docs", redoc_url=None)
    db_path = data_dir / INDEX_NAME

    app.state.db_path = db_path

    @app.get("/healthz")
    def healthz(store: StoreDep) -> dict[str, object]:
        return {"notes": store.note_count(), "built_at": store.meta("built_at")}

    @app.get("/api/notebooks")
    def notebooks(store: StoreDep) -> list[Notebook]:
        return store.notebooks()

    @app.get("/api/tags")
    def tags(store: StoreDep) -> list[Tag]:
        return store.tags()

    @app.get("/api/notes")
    def notes(
        store: StoreDep,
        notebook: str | None = None,
        tag: str | None = None,
        q: str | None = None,
        limit: Annotated[int, Query(ge=1, le=500)] = 50,
        offset: Annotated[int, Query(ge=0)] = 0,
    ) -> NotePage:
        return store.notes(
            notebook_id=notebook, tag=tag, q=q, limit=limit, offset=offset
        )

    @app.get("/api/notes/{note_id}")
    def note(note_id: str, store: StoreDep) -> NoteDetail:
        detail = store.note(note_id)
        if detail is None:
            raise HTTPException(404, "No such note")
        return detail

    @app.get("/notes/{note_id}/content", response_class=HTMLResponse)
    def note_content(note_id: str, store: StoreDep) -> HTMLResponse:
        source = store.note_source(note_id)
        if source is None:
            raise HTTPException(404, "No such note")
        enml, source_url = source
        attachments = store.attachments(note_id)
        names = {a.hash: a.filename for a in attachments}
        body = render(
            enml,
            attachments=attachments,
            resolve_guid=store.resolve_guid,
            source_url=source_url,
            file_url=lambda h: file_url(h, names.get(h)),
        )
        page = (
            '<!doctype html><html><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width, initial-scale=1">'
            f"<style>{_NOTE_CSS}</style></head><body>{body}</body></html>"
        )
        return HTMLResponse(
            page,
            headers={
                "Content-Security-Policy": _NOTE_CSP,
                "Referrer-Policy": "no-referrer",
                "X-Content-Type-Options": "nosniff",
            },
        )

    def serve_file(md5: str, name: str | None, store: Store) -> FileResponse:
        if not _MD5.match(md5):
            raise HTTPException(404, "No such file")
        mime = store.resource_mime(md5)
        path = blob_path(data_dir, md5)
        if mime is None or not path.is_file():
            raise HTTPException(404, "No such file")
        headers = dict(_FILE_HEADERS)
        if not _PASSIVE.match(mime):
            headers["Content-Security-Policy"] = _SANDBOX_FILE_CSP
        return FileResponse(
            path,
            media_type=mime,
            filename=name,
            content_disposition_type="inline",
            headers=headers,
        )

    @app.get("/files/{md5}")
    def file(md5: str, store: StoreDep) -> FileResponse:
        return serve_file(md5, None, store)

    @app.get("/files/{md5}/{name}")
    def named_file(md5: str, name: str, store: StoreDep) -> FileResponse:
        return serve_file(md5, name, store)

    return app
