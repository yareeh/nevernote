import hashlib
import os
import sqlite3
from pathlib import Path
from typing import Any

import pytest

from enex_viewer.index import build_index, index_is_stale
from enexgen import PDF, PNG, note, resource, write

G1 = "11111111-1111-1111-1111-111111111111"
G2 = "22222222-2222-2222-2222-222222222222"


@pytest.fixture
def enex_dir(tmp_path: Path) -> Path:
    src = tmp_path / "enex"
    write(
        src / "Work" / "Recipes.enex",
        note(
            "Pancakes",
            '<div>flour and eggs</div><en-media hash="x" type="image/png"/>',
            guid=G1,
            tags=["food", "breakfast"],
            resources=[resource(PNG, "image/png", "pan.png")],
        ),
        note("Soup", "<div>leeks</div>", guid=G2),
    )
    write(
        src / "Inbox.enex",
        note(
            "Scan", "<div>tax form</div>", resources=[resource(PDF, "application/pdf")]
        ),
        note("Same image again", resources=[resource(PNG, "image/png", "copy.png")]),
    )
    # macOS AppleDouble file that rides along when copying from a Mac.
    (src / "._Inbox.enex").write_bytes(b"\x00\x05\x16\x07junk")
    return src


def rows(db: Path, sql: str) -> list[tuple[Any, ...]]:
    with sqlite3.connect(db) as conn:
        return conn.execute(sql).fetchall()


def ids_by_title(db: Path) -> dict[str, str]:
    return {str(t): str(i) for t, i in rows(db, "SELECT title, id FROM notes")}


def test_indexes_notebooks_notes_and_stacks(enex_dir: Path, tmp_path: Path) -> None:
    data = tmp_path / "data"
    stats = build_index(enex_dir, data)
    assert (stats.notebooks, stats.notes) == (2, 4)
    db = data / "index.sqlite"
    assert rows(db, "SELECT name, stack, note_count FROM notebooks ORDER BY name") == [
        ("Inbox", None, 2),
        ("Recipes", "Work", 2),
    ]


def test_note_ids_use_guid_else_stable_hash(enex_dir: Path, tmp_path: Path) -> None:
    data = tmp_path / "data"
    build_index(enex_dir, data)
    db = data / "index.sqlite"
    ids = ids_by_title(db)
    assert ids["Pancakes"] == G1
    assert ids["Soup"] == G2
    assert len(str(ids["Scan"])) == 16
    build_index(enex_dir, data)
    assert ids_by_title(db) == ids


def test_stores_note_metadata_and_tags(enex_dir: Path, tmp_path: Path) -> None:
    data = tmp_path / "data"
    build_index(enex_dir, data)
    db = data / "index.sqlite"
    [(guid, created, content)] = rows(
        db, "SELECT guid, created, content FROM notes WHERE title = 'Pancakes'"
    )
    assert guid == G1
    assert created == "2024-01-01T10:00:00+00:00"
    assert "flour and eggs" in str(content)
    assert rows(
        db, f"SELECT tag FROM note_tags WHERE note_id = '{G1}' ORDER BY tag"
    ) == [
        ("breakfast",),
        ("food",),
    ]


def test_stores_each_attachment_once(enex_dir: Path, tmp_path: Path) -> None:
    data = tmp_path / "data"
    stats = build_index(enex_dir, data)
    png_hash = hashlib.md5(PNG).hexdigest()
    pdf_hash = hashlib.md5(PDF).hexdigest()
    assert stats.resources == 2
    assert (data / "blobs" / png_hash[:2] / png_hash).read_bytes() == PNG
    assert (data / "blobs" / pdf_hash[:2] / pdf_hash).read_bytes() == PDF
    db = data / "index.sqlite"
    assert rows(db, "SELECT filename FROM note_resources ORDER BY filename") == [
        (None,),
        ("copy.png",),
        ("pan.png",),
    ]


def test_full_text_search(enex_dir: Path, tmp_path: Path) -> None:
    data = tmp_path / "data"
    build_index(enex_dir, data)
    found = rows(
        data / "index.sqlite",
        "SELECT n.title FROM notes_fts f JOIN notes n ON n.rowid = f.rowid "
        "WHERE notes_fts MATCH 'leeks'",
    )
    assert found == [("Soup",)]


def test_broken_file_keeps_parsed_notes_and_other_notebooks(
    enex_dir: Path, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    broken = write(enex_dir / "Broken.enex", note("Good one"), note("Lost"))
    text = broken.read_text()
    broken.write_text(text[: text.index("<title>Lost")] + "<title>Lost</oops>")
    stats = build_index(enex_dir, tmp_path / "data")
    assert stats.notebooks == 3
    assert stats.notes == 5  # 4 from the fixture + "Good one"
    assert stats.broken_files == ["Broken.enex"]
    assert "Broken.enex" in caplog.text
    titles = {
        t
        for (t,) in rows(tmp_path / "data" / "index.sqlite", "SELECT title FROM notes")
    }
    assert "Good one" in titles


def test_duplicate_guid_keeps_first(enex_dir: Path, tmp_path: Path) -> None:
    write(enex_dir / "Zdup.enex", note("Pancakes copy", guid=G1))
    stats = build_index(enex_dir, tmp_path / "data")
    assert stats.duplicate_guids == 1
    assert stats.notes == 4


def test_rebuild_drops_removed_notes_and_blobs(enex_dir: Path, tmp_path: Path) -> None:
    data = tmp_path / "data"
    build_index(enex_dir, data)
    (enex_dir / "Inbox.enex").unlink()
    stats = build_index(enex_dir, data)
    assert (stats.notebooks, stats.notes, stats.resources) == (1, 2, 1)
    pdf_hash = hashlib.md5(PDF).hexdigest()
    assert not (data / "blobs" / pdf_hash[:2] / pdf_hash).exists()
    assert sorted(p.name for p in data.iterdir()) == ["blobs", "index.sqlite"]


def test_staleness(enex_dir: Path, tmp_path: Path) -> None:
    data = tmp_path / "data"
    assert index_is_stale(enex_dir, data)
    build_index(enex_dir, data)
    assert not index_is_stale(enex_dir, data)
    f = enex_dir / "Inbox.enex"
    st = f.stat()
    os.utime(f, ns=(st.st_atime_ns, st.st_mtime_ns + 1_000_000_000))
    assert index_is_stale(enex_dir, data)
