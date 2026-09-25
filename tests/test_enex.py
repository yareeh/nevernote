import hashlib
from datetime import UTC, datetime
from pathlib import Path

from enex_viewer.enex import iter_notes
from enexgen import PDF, PNG, note, resource, write

GUID = "0b1c2d3e-4f50-6172-8394-a5b6c7d8e9f0"


def test_parses_note_fields(tmp_path: Path) -> None:
    path = write(
        tmp_path / "nb.enex",
        note(
            "Grocery list",
            "<div>oat milk</div>",
            guid=GUID,
            created="20240101T100000Z",
            updated="20240102T113000Z",
            tags=["home", "food"],
            author="Jari",
            source_url="https://example.com/list",
        ),
    )
    [n] = list(iter_notes(path))
    assert n.title == "Grocery list"
    assert n.guid == GUID
    assert n.created == datetime(2024, 1, 1, 10, 0, tzinfo=UTC)
    assert n.updated == datetime(2024, 1, 2, 11, 30, tzinfo=UTC)
    assert n.tags == ["home", "food"]
    assert n.author == "Jari"
    assert n.source_url == "https://example.com/list"
    assert "<en-note><div>oat milk</div></en-note>" in n.content


def test_missing_optional_fields(tmp_path: Path) -> None:
    path = write(tmp_path / "nb.enex", note("Bare", created=None))
    [n] = list(iter_notes(path))
    assert n.guid is None
    assert n.created is None
    assert n.updated is None
    assert n.tags == []
    assert n.author is None
    assert n.source_url is None
    assert n.resources == []


def test_guid_from_custom_metadata(tmp_path: Path) -> None:
    path = write(tmp_path / "nb.enex", note("Meta", metadata_guid=GUID))
    [n] = list(iter_notes(path))
    assert n.guid == GUID


def test_decodes_resources(tmp_path: Path) -> None:
    path = write(
        tmp_path / "nb.enex",
        note(
            "With files",
            resources=[
                resource(PNG, "image/png", "dot.png"),
                resource(PDF, "application/pdf"),
            ],
        ),
    )
    [n] = list(iter_notes(path))
    png, pdf = n.resources
    assert png.data == PNG
    assert png.hash == hashlib.md5(PNG).hexdigest()
    assert png.mime == "image/png"
    assert png.filename == "dot.png"
    assert pdf.data == PDF
    assert pdf.filename is None


def test_streams_many_notes_in_order(tmp_path: Path) -> None:
    path = write(tmp_path / "nb.enex", *(note(f"N{i}") for i in range(50)))
    assert [n.title for n in iter_notes(path)] == [f"N{i}" for i in range(50)]
