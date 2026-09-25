# Evernote archive viewer

A read-only web viewer and JSON API for Evernote ENEX exports. It runs on
this Linux box and you browse it from any device on the LAN. Nothing is
copied to the client beyond what the browser shows.

```
Evernote ──evernote-backup──► data/evernote/en_backup.db ──export --add-guid──► data/enex/*.enex
                                                                                    │ (read-only)
                                        enex-viewer (Docker, :8765)  ◄──────────────┘
                                        ├── index.sqlite + blobs/<md5>   (derived, rebuilt when ENEX changes)
                                        ├── web UI      /               notebooks | notes | note
                                        └── JSON API    /api/...
```

## Quick start

```bash
make setup                                   # uv sync
make evernote-init evernote-sync evernote-export
make viewer-up                               # prints http://<this box>:8765
```

To serve other ENEX files, e.g. exports from Evernote.app, set `ENEX_DIR` in
`.env` (see `.env.example`):

```bash
echo 'ENEX_DIR=./tmp/evernote' > .env && make viewer-up
```

After re-exporting, run `make viewer-reindex` (or just restart the container).
On start it rebuilds the index when the ENEX files changed. An index takes
seconds: 632 MB of ENEX indexes in about 2 s.

## What it does

- **Notebooks and stacks:** one `.enex` file is one notebook, and a
  subdirectory is a stack (that's how `evernote-backup export` lays them
  out). Hidden files and macOS `._*` files are ignored.
- **Stable note IDs:** the note's Evernote GUID when the export has one
  (`--add-guid`, which `make evernote-export` uses). Otherwise a hash of
  file, position, title and date, which can change if the export changes.
- **Links between notes:** `evernote:///view/…` and
  `https://www.evernote.com/shard/…` links open the linked note in the viewer
  when it's in the archive. Otherwise the link is shown greyed out.
  Evernote.app exports have no GUIDs, so there these links can't resolve.
- **Attachments:** images display inline and video/audio play inline. PDFs and
  other files are links that open in the browser (on the Mac: Safari's PDF
  view, "Open in Preview" from there). Each file is stored once, by MD5.
- **Search:** full text over titles and bodies. Every word must match, as a
  prefix, and diacritics are ignored (`kaytto` finds `käyttö`).
- **Safety:** note HTML is sanitized with an allowlist. It's shown in a
  sandboxed iframe with no scripts, served under a CSP. Remote images in web
  clips load as-is. Attachments that could run script (SVG, HTML) are served
  sandboxed.
- **Access:** LAN only, no login. It's published on port 8765 of this box;
  don't forward that port on the router.

## API

Interactive docs at `/api/docs`.

| Endpoint | |
|---|---|
| `GET /api/notebooks` | notebooks with stack and note count |
| `GET /api/tags` | tags with counts |
| `GET /api/notes?notebook=&tag=&q=&limit=&offset=` | notes, newest first, or search results with `snippet_html` |
| `GET /api/notes/{id}` | metadata, tags, attachments (`url`), `content_url` |
| `GET /notes/{id}/content` | the rendered note body (HTML document) |
| `GET /files/{md5}[/{name}]` | attachment bytes |
| `GET /healthz` | note count, index build time |

## Development

```bash
make check                                   # ruff format/lint, pyright (strict), pytest
ENEX_DIR=tmp/evernote PORT=8799 make dev     # run without Docker
uv run enex-viewer index --enex-dir … --data-dir …
```

| Module | |
|---|---|
| `enex.py` | streaming ENEX parser |
| `enml.py` | ENML parsing and plain text |
| `index.py` | SQLite + FTS5 index, blob store, staleness |
| `render.py` | ENML → sanitized HTML, note-link resolution |
| `store.py` | read-only queries (Pydantic models) |
| `app.py` | API, note bodies, files |
| `ui.py` + `templates/` | web UI |

Keep `data/evernote/en_backup.db` and the ENEX files: they are the archive.
Everything under the Docker volume is derived from them.
