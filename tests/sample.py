"""Sample archive shared by the API and UI tests."""

import hashlib
from pathlib import Path

from enex_viewer.index import build_index
from enexgen import PDF, PNG, note, resource, write

G1 = "11111111-1111-1111-1111-111111111111"
G2 = "22222222-2222-2222-2222-222222222222"
PNG_HASH = hashlib.md5(PNG).hexdigest()
PDF_HASH = hashlib.md5(PDF).hexdigest()
SVG = b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'
SVG_HASH = hashlib.md5(SVG).hexdigest()


def build_sample(tmp_path: Path) -> Path:
    """Index a small archive: a stacked notebook with GUID notes, an inbox."""
    enex = tmp_path / "enex"
    write(
        enex / "Work" / "Recipes.enex",
        note(
            "Pancakes",
            f'<div>flour and eggs, see <a href="evernote:///view/1/s1/{G2}/{G2}/">'
            f'soup</a></div><en-media hash="{PNG_HASH}" type="image/png"/>',
            guid=G1,
            tags=["food", "breakfast"],
            created="20240101T100000Z",
            updated="20240301T100000Z",
            source_url="https://example.com/pancakes",
            resources=[resource(PNG, "image/png", "pan.png")],
        ),
        note(
            "Soup",
            "<div>leeks and potatoes</div>",
            guid=G2,
            tags=["food"],
            updated="20240401T100000Z",
        ),
    )
    write(
        enex / "Inbox.enex",
        note(
            "Tax scan",
            "<div>form <script>alert(1)</script></div>",
            resources=[
                resource(PDF, "application/pdf", "tax form.pdf"),
                resource(SVG, "image/svg+xml", "logo.svg"),
            ],
        ),
    )
    data = tmp_path / "data"
    build_index(enex, data)
    return data
