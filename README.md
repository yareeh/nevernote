# my-joplin

Migrate Evernote to a self-hosted Joplin Server on this Linux box, then use
it from the Mac.

```
Evernote ──evernote-backup──► SQLite + .enex        (data/evernote, data/enex)
                                   │
                         Joplin CLI import           (patched, verified counts)
                                   │ sync
                         Joplin Server + Postgres    (Docker, :22300)
                                   │ sync
                         Joplin desktop (Mac)
```

Joplin Server can't import ENEX itself. A client has to import, then sync
to the server. Here that client is a pinned Joplin terminal app with a
repo-local profile, so the import never touches any other Joplin install.

## Prerequisites

Docker (with Compose), [uv](https://docs.astral.sh/uv/), Node.js ≥ 18.

```bash
make setup      # uv sync, npm ci (applies patches/), creates .env with random passwords
```

## Phase 1: test server with sample notebooks

Put some `.enex` files in `tmp/evernote/`. Mac `._*` files are ignored. Then:

```bash
make test-server         # :22301, own DB volume and data-test/ profile, then import + sync
make ENV_FILE=.env.test status
make test-server-reset   # throw it all away
```

`make test-server` writes `.env.test` on first run. Your login details are
in `JOPLIN_USER_EMAIL` and `JOPLIN_USER_PASSWORD` in that file.

## Phase 2: the real migration

1. Set `JOPLIN_USER_EMAIL`, `JOPLIN_USER_NAME` and `APP_BASE_URL` in `.env`.
   Reserve the box's IP in your router's DHCP settings so the URL keeps
   working.
2. Start the server and create your account:
   `make server-up server-user`. This also rotates the default
   `admin@localhost` / `admin` password to `JOPLIN_ADMIN_PASSWORD`.
3. Back up Evernote:
   ```bash
   make evernote-init     # prints an OAuth URL; works with 2FA/SSO
   make evernote-sync     # full download into data/evernote/en_backup.db
   make evernote-export   # one .enex per notebook into data/enex/
   ```
4. Import and sync: `make joplin-configure import`

`make import` refuses to run if:
- this profile already imported, since a second import duplicates every note;
- the profile isn't empty;
- the Joplin CLI isn't patched.

It also counts the `<note>` elements in the ENEX files and refuses to sync
unless Joplin ended up with exactly that many notes.

## On the Mac

Joplin → Settings → Synchronisation:

- Target: **Joplin Server**
- URL: exactly `APP_BASE_URL`, e.g. `http://192.168.1.123:22300`
  (test instance: `:22301`)
- Email and password: `JOPLIN_USER_EMAIL` and `JOPLIN_USER_PASSWORD` from
  the env file

Don't import ENEX on the Mac as well, or you'll get duplicates.

The admin web UI is at `APP_BASE_URL/login`.

## Joplin CLI bug (patched)

Joplin CLI 3.7.1 (and upstream `dev` as of 2026-09) silently drops notes
when importing small ENEX files. It reports "Created: 3" but keeps only the
first note. Cause: `ItemChange` rows are written in the background inside a
transaction on the shared SQLite connection. The CLI closes the DB right
after the command finishes, so that COMMIT fails with `SQLITE_MISUSE` and
everything written since its BEGIN is rolled back, including note INSERTs.

`patches/joplin+3.7.1.patch` makes the CLI call
`ItemChange.waitForAllSaved()` before closing. It is applied by
patch-package on every `npm ci`. When you bump the `joplin` version,
regenerate the patch and rerun `make test`, which catches the regression.

A second CLI quirk is handled in `scripts/import-enex.sh`: without an explicit
target notebook, `joplin import` puts every file after the first into the
first notebook. The script runs `mkbook "<file name>"` for each file and
imports into it. It then checks every notebook's note count against its ENEX
file.

## Choices and gotchas

- **Markdown vs HTML**: `IMPORT_OUTPUT_FORMAT=md` gives editable Markdown.
  `html` keeps Evernote's formatting as a faithful archive (it's the CLI's
  `--output-format html`).
- **End-to-end encryption**: if you want it, enable it before the first big
  sync (`scripts/joplin.sh e2ee enable`). Enabling it later re-uploads
  everything, and every client then needs the master password.
- **Re-exporting later** and importing again creates duplicates. Treat the
  migration as one-off, or reset: stop the server, `docker compose down -v`,
  delete `data/joplin-cli`.
- **Keep `data/evernote/en_backup.db`** and the `.enex` files whatever
  happens. They are the raw backup.
- **Backups of the server**: `make backup` writes a gzipped `pg_dump` to
  `$DATA_DIR/backups/`.

## Layout

| Path | What |
|---|---|
| `compose.yaml` | Postgres 16 + `joplin/server:3.7.2` |
| `.env`, `.env.test` | per-instance config and secrets (gitignored) |
| `scripts/` | provisioning, CLI config, import, backup |
| `patches/` | Joplin CLI fix, applied by patch-package |
| `tests/e2e.sh` | `make test`: throwaway stack on :22399, import, sync, second client verifies |
