import hashlib
from datetime import UTC, datetime
from pathlib import Path

import pytest

from enex_viewer.enex import iter_notes, repair_cdata
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


def test_content_containing_cdata_end_marker(tmp_path: Path) -> None:
    # evernote-backup wraps content in CDATA without escaping "]]>", so a web
    # clip that itself contains a CDATA section breaks the XML.
    clip = '<div><a href="x"><![CDATA[>]]></a>next &gt;&gt;|</div>'
    path = tmp_path / "nb.enex"
    path.write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n<en-export>\n'
        "<note><title>Before</title><content><![CDATA[<en-note>ok</en-note>]]>"
        "</content></note>\n"
        "<note><title>Clip</title><content>\n      <![CDATA["
        '<?xml version="1.0" encoding="UTF-8" standalone="no"?>\n'
        f"<en-note>{clip}</en-note>]]>\n    </content>"
        f"<guid>{GUID}</guid></note>\n"
        "<note><title>After</title><content><![CDATA[<en-note>tail</en-note>]]>"
        "</content></note>\n</en-export>\n",
        encoding="utf-8",
    )
    before, clip_note, after = iter_notes(path)
    assert (before.title, clip_note.title, after.title) == ("Before", "Clip", "After")
    assert clip_note.guid == GUID
    assert "<![CDATA[>]]>" in clip_note.content
    assert clip_note.content.rstrip().endswith("</en-note>")
    assert "tail" in after.content


RAW = (
    b"<en-export><note><title>A ]]> b</title><content>\n  <![CDATA[<en-note>"
    b"x<![CDATA[>]]>y ]]]]><![CDATA[> z</en-note>]]>\n  </content></note>"
    b"<note><content><![CDATA[<en-note>q]]></content></note></en-export>"
)
REPAIRED = (
    b"<en-export><note><title>A ]]> b</title><content>\n  <![CDATA[<en-note>"
    b"x<![CDATA[>]]]]><![CDATA[>y ]]]]><![CDATA[> z</en-note>]]>\n  </content></note>"
    b"<note><content><![CDATA[<en-note>q]]></content></note></en-export>"
)


@pytest.mark.parametrize("size", [1, 2, 3, 5, 8, 13, 64, len(RAW)])
def test_repair_is_independent_of_chunking(size: int) -> None:
    chunks = [RAW[i : i + size] for i in range(0, len(RAW), size)]
    assert b"".join(repair_cdata(chunks)) == REPAIRED


def test_correctly_escaped_content_is_unchanged(tmp_path: Path) -> None:
    # Evernote's own exporter splits "]]>" as "]]]]><![CDATA[>".
    path = write(tmp_path / "nb.enex", note("Esc", "<div>a]]]]><![CDATA[>b</div>"))
    [n] = iter_notes(path)
    assert "<div>a]]>b</div>" in n.content


def test_streams_many_notes_in_order(tmp_path: Path) -> None:
    path = write(tmp_path / "nb.enex", *(note(f"N{i}") for i in range(50)))
    assert [n.title for n in iter_notes(path)] == [f"N{i}" for i in range(50)]
