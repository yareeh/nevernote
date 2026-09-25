import hashlib
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from enex_viewer.app import create_app
from enex_viewer.index import build_index
from enexgen import PDF, PNG, note, resource, write

G1 = "11111111-1111-1111-1111-111111111111"
G2 = "22222222-2222-2222-2222-222222222222"
PNG_HASH = hashlib.md5(PNG).hexdigest()
PDF_HASH = hashlib.md5(PDF).hexdigest()
SVG = b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'
SVG_HASH = hashlib.md5(SVG).hexdigest()


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
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


@pytest.fixture
def client(data_dir: Path) -> TestClient:
    return TestClient(create_app(data_dir))


def test_notebooks(client: TestClient) -> None:
    r = client.get("/api/notebooks")
    assert r.status_code == 200
    assert [(n["name"], n["stack"], n["note_count"]) for n in r.json()] == [
        ("Inbox", None, 1),
        ("Recipes", "Work", 2),
    ]


def test_tags(client: TestClient) -> None:
    assert client.get("/api/tags").json() == [
        {"name": "breakfast", "count": 1},
        {"name": "food", "count": 2},
    ]


def test_notes_in_notebook_newest_first(client: TestClient) -> None:
    nb = next(n for n in client.get("/api/notebooks").json() if n["name"] == "Recipes")
    page = client.get("/api/notes", params={"notebook": nb["id"]}).json()
    assert page["total"] == 2
    assert [n["title"] for n in page["items"]] == ["Soup", "Pancakes"]


def test_notes_by_tag_and_paging(client: TestClient) -> None:
    page = client.get("/api/notes", params={"tag": "food", "limit": 1}).json()
    assert page["total"] == 2
    assert len(page["items"]) == 1
    page2 = client.get(
        "/api/notes", params={"tag": "food", "limit": 1, "offset": 1}
    ).json()
    assert page2["items"][0]["id"] != page["items"][0]["id"]


def test_search_with_prefix_and_snippet(client: TestClient) -> None:
    page = client.get("/api/notes", params={"q": "potat"}).json()
    assert [n["title"] for n in page["items"]] == ["Soup"]
    assert "<mark>potatoes</mark>" in page["items"][0]["snippet_html"]


def test_search_escapes_note_text_in_snippet(client: TestClient) -> None:
    [item] = client.get("/api/notes", params={"q": "form"}).json()["items"]
    assert "<script>" not in item["snippet_html"]


def test_search_tolerates_fts_syntax(client: TestClient) -> None:
    r = client.get("/api/notes", params={"q": 'leeks" OR NEAR( *'})
    assert r.status_code == 200


def test_note_detail(client: TestClient) -> None:
    n = client.get(f"/api/notes/{G1}").json()
    assert n["title"] == "Pancakes"
    assert n["guid"] == G1
    assert n["notebook"]["name"] == "Recipes"
    assert n["tags"] == ["breakfast", "food"]
    assert n["source_url"] == "https://example.com/pancakes"
    assert n["created"] == "2024-01-01T10:00:00+00:00"
    [att] = n["attachments"]
    assert att["filename"] == "pan.png"
    assert att["url"] == f"/files/{PNG_HASH}/pan.png"
    assert n["content_url"] == f"/notes/{G1}/content"


def test_unknown_note_is_404(client: TestClient) -> None:
    assert client.get("/api/notes/nope").status_code == 404
    assert client.get("/notes/nope/content").status_code == 404


def test_note_content_is_sandboxed_html(client: TestClient) -> None:
    r = client.get(f"/notes/{G1}/content")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/html")
    csp = r.headers["content-security-policy"]
    assert "sandbox" in csp
    assert "script-src 'none'" in csp
    assert f'href="/notes/{G2}"' in r.text
    assert f'src="/files/{PNG_HASH}/pan.png"' in r.text


def test_note_content_strips_scripts(client: TestClient) -> None:
    [scan] = client.get("/api/notes", params={"q": "form"}).json()["items"]
    r = client.get(f"/notes/{scan['id']}/content")
    assert "alert(1)" not in r.text


def test_files_served_with_type_and_name(client: TestClient) -> None:
    r = client.get(f"/files/{PDF_HASH}/tax%20form.pdf")
    assert r.status_code == 200
    assert r.content == PDF
    assert r.headers["content-type"] == "application/pdf"
    assert r.headers["content-disposition"].startswith("inline")
    assert "tax%20form.pdf" in r.headers["content-disposition"]
    assert r.headers["x-content-type-options"] == "nosniff"
    assert client.get(f"/files/{PDF_HASH}").content == PDF


def test_active_file_types_are_sandboxed(client: TestClient) -> None:
    r = client.get(f"/files/{SVG_HASH}/logo.svg")
    assert r.status_code == 200
    assert "sandbox" in r.headers["content-security-policy"]
    pdf = client.get(f"/files/{PDF_HASH}")
    assert "content-security-policy" not in pdf.headers


def test_files_reject_bad_hashes(client: TestClient) -> None:
    assert client.get("/files/" + "0" * 32).status_code == 404
    assert client.get("/files/..%2F..%2Findex.sqlite").status_code == 404


def test_missing_index_is_503(tmp_path: Path) -> None:
    client = TestClient(create_app(tmp_path / "empty"))
    assert client.get("/api/notebooks").status_code == 503


def test_healthz(client: TestClient) -> None:
    body = client.get("/healthz").json()
    assert body["notes"] == 3
    assert body["built_at"]
