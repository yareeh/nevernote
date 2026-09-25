"""Server-rendered web UI: notebooks and tags | note list | note.

No JavaScript. The list pane keeps its context (notebook, tag, search or all
notes) in the note links' query string, so opening a note from search results
keeps the results next to it.
"""

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Annotated, Any
from urllib.parse import quote, urlencode

from fastapi import APIRouter, FastAPI, HTTPException, Query, Request
from fastapi.exception_handlers import http_exception_handler
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.exceptions import HTTPException as StarletteHTTPException

from enex_viewer.render import human_size
from enex_viewer.store import (
    IndexMissingError,
    Notebook,
    NoteDetail,
    NoteSummary,
    Store,
)

_HERE = Path(__file__).parent
_API_PREFIXES = ("/api/", "/files/", "/healthz", "/static/")

Offset = Annotated[int, Query(ge=0)]


@dataclass
class NoteList:
    kind: str  # all | notebook | tag | search
    heading: str
    items: list[NoteSummary]
    total: int
    offset: int
    page_size: int
    base_url: str  # list page URL without offset
    context: dict[str, str] = field(default_factory=lambda: {})

    def note_url(self, note_id: str) -> str:
        ctx = dict(self.context)
        if self.offset:
            ctx["offset"] = str(self.offset)
        return f"/notes/{note_id}" + (f"?{urlencode(ctx)}" if ctx else "")

    def page_url(self, offset: int) -> str:
        sep = "&" if "?" in self.base_url else "?"
        return self.base_url + (f"{sep}offset={offset}" if offset else "")

    @property
    def prev_url(self) -> str | None:
        if self.offset <= 0:
            return None
        return self.page_url(max(0, self.offset - self.page_size))

    @property
    def next_url(self) -> str | None:
        if self.offset + self.page_size >= self.total:
            return None
        return self.page_url(self.offset + self.page_size)

    @property
    def more_url(self) -> str | None:
        """Fragment with the next batch of list items (infinite scroll)."""
        if self.offset + self.page_size >= self.total:
            return None
        ctx = {**self.context, "offset": str(self.offset + self.page_size)}
        return f"/ui/items?{urlencode(ctx)}"


def _date(value: str | None, with_time: bool = False) -> str:
    if not value:
        return ""
    dt = datetime.fromisoformat(value)
    return dt.strftime("%Y-%m-%d %H:%M UTC" if with_time else "%Y-%m-%d")


def _host(url: str | None) -> str:
    if not url:
        return ""
    return url.split("//", 1)[-1].split("/", 1)[0]


def _path_segment(value: str) -> str:
    return quote(value, safe="")


def _grouped(notebooks: list[Notebook]) -> list[tuple[str | None, list[Notebook]]]:
    groups: dict[str | None, list[Notebook]] = {}
    for nb in notebooks:
        groups.setdefault(nb.stack, []).append(nb)
    return list(groups.items())


def install_ui(app: FastAPI, *, page_size: int) -> None:
    templates = Jinja2Templates(directory=_HERE / "templates")
    templates.env.filters["date"] = _date
    templates.env.filters["host"] = _host
    templates.env.filters["size"] = human_size
    templates.env.filters["q"] = _path_segment
    app.mount("/static", StaticFiles(directory=_HERE / "static"), name="static")

    def open_store(request: Request) -> Store:
        try:
            return Store(request.app.state.db_path)
        except IndexMissingError:
            raise HTTPException(503, "The index hasn't been built yet.") from None

    def note_list(
        store: Store,
        *,
        notebook: str | None = None,
        tag: str | None = None,
        q: str | None = None,
        offset: int = 0,
    ) -> NoteList:
        page = store.notes(
            notebook_id=notebook, tag=tag, q=q, limit=page_size, offset=offset
        )
        common: dict[str, Any] = {
            "items": page.items,
            "total": page.total,
            "offset": offset,
            "page_size": page_size,
        }
        if q is not None:
            return NoteList(
                kind="search",
                heading=f"Search: {q}",
                base_url=f"/search?{urlencode({'q': q})}",
                context={"q": q},
                **common,
            )
        if tag is not None:
            return NoteList(
                kind="tag",
                heading=f"#{tag}",
                base_url=f"/tags/{quote(tag, safe='')}",
                context={"tag": tag},
                **common,
            )
        if notebook is not None:
            nb = store.notebook(notebook)
            if nb is None:
                raise HTTPException(404, "Notebook not found.")
            return NoteList(
                kind="notebook",
                heading=nb.name,
                base_url=f"/notebooks/{nb.id}",
                context={"notebook": nb.id},
                **common,
            )
        return NoteList(
            kind="all",
            heading="All notes",
            base_url="/",
            context={"list": "all"},
            **common,
        )

    def browse(
        request: Request,
        store: Store,
        notes: NoteList,
        note: NoteDetail | None = None,
    ) -> HTMLResponse:
        return templates.TemplateResponse(
            request,
            "browse.html",
            {
                "notebook_groups": _grouped(store.notebooks()),
                "tags": store.tags(),
                "total_notes": store.note_count(),
                "list": notes,
                "note": note,
                "q": notes.context.get("q", ""),
                "active_notebook": note.notebook.id
                if note
                else notes.context.get("notebook"),
                "active_tag": notes.context.get("tag"),
            },
        )

    router = APIRouter(default_response_class=HTMLResponse)

    @router.get("/")
    def home(request: Request, offset: Offset = 0) -> HTMLResponse:
        store = open_store(request)
        try:
            return browse(request, store, note_list(store, offset=offset))
        finally:
            store.close()

    @router.get("/notebooks/{notebook_id}")
    def notebook_page(
        request: Request, notebook_id: str, offset: Offset = 0
    ) -> HTMLResponse:
        store = open_store(request)
        try:
            notes = note_list(store, notebook=notebook_id, offset=offset)
            return browse(request, store, notes)
        finally:
            store.close()

    @router.get("/tags/{tag:path}")
    def tag_page(request: Request, tag: str, offset: Offset = 0) -> HTMLResponse:
        store = open_store(request)
        try:
            return browse(request, store, note_list(store, tag=tag, offset=offset))
        finally:
            store.close()

    @router.get("/search")
    def search_page(request: Request, q: str = "", offset: Offset = 0) -> HTMLResponse:
        store = open_store(request)
        try:
            return browse(request, store, note_list(store, q=q, offset=offset))
        finally:
            store.close()

    def note_context(
        store: Store,
        note_id: str,
        request: Request,
        q: str | None,
        tag: str | None,
        notebook: str | None,
        offset: int,
    ) -> tuple[NoteDetail, NoteList]:
        note = store.note(note_id)
        if note is None:
            raise HTTPException(404, "Note not found.")
        listing = request.query_params.get("list") == "all"
        if q is None and tag is None and notebook is None and not listing:
            notebook = note.notebook.id  # default: the note's own notebook
        notes = note_list(store, notebook=notebook, tag=tag, q=q, offset=offset)
        return note, notes

    @router.get("/notes/{note_id}")
    def note_page(
        request: Request,
        note_id: str,
        q: str | None = None,
        tag: str | None = None,
        notebook: str | None = None,
        offset: Offset = 0,
    ) -> HTMLResponse:
        store = open_store(request)
        try:
            note, notes = note_context(
                store, note_id, request, q, tag, notebook, offset
            )
            return browse(request, store, notes, note)
        finally:
            store.close()

    # Fragments for static/app.js: swap the note pane in place and append list
    # items while scrolling, so the list is never re-rendered.

    @router.get("/ui/note/{note_id}")
    def note_fragment(
        request: Request,
        note_id: str,
        q: str | None = None,
        tag: str | None = None,
        notebook: str | None = None,
        offset: Offset = 0,
    ) -> HTMLResponse:
        store = open_store(request)
        try:
            note, notes = note_context(
                store, note_id, request, q, tag, notebook, offset
            )
            return templates.TemplateResponse(
                request, "_note_pane.html", {"note": note, "list": notes}
            )
        finally:
            store.close()

    @router.get("/ui/items")
    def items_fragment(
        request: Request,
        q: str | None = None,
        tag: str | None = None,
        notebook: str | None = None,
        offset: Offset = 0,
    ) -> HTMLResponse:
        store = open_store(request)
        try:
            notes = note_list(store, notebook=notebook, tag=tag, q=q, offset=offset)
            return templates.TemplateResponse(
                request, "_note_items.html", {"note": None, "list": notes}
            )
        finally:
            store.close()

    app.include_router(router)

    @app.exception_handler(StarletteHTTPException)
    async def html_errors(request: Request, exc: StarletteHTTPException) -> Any:
        if request.url.path.startswith(_API_PREFIXES):
            return await http_exception_handler(request, exc)
        return templates.TemplateResponse(
            request,
            "error.html",
            {"status": exc.status_code, "message": exc.detail, "q": ""},
            status_code=exc.status_code,
        )
