from pathlib import Path
from typing import cast

import pytest
from fastapi.testclient import TestClient
from lxml import html as lxml_html
from sample import G1, G2, PDF_HASH

from enex_viewer.app import create_app
from enex_viewer.index import build_index
from enexgen import note, write


@pytest.fixture
def client(data_dir: Path) -> TestClient:
    return TestClient(create_app(data_dir))


def page(client: TestClient, url: str) -> lxml_html.HtmlElement:
    r = client.get(url)
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("text/html")
    # lxml-stubs leave **kw untyped on this function.
    doc = lxml_html.document_fromstring(r.text)  # pyright: ignore[reportUnknownMemberType]
    return cast(lxml_html.HtmlElement, doc)


def texts(doc: lxml_html.HtmlElement, css_class: str) -> list[str]:
    return [e.text_content().strip() for e in doc.find_class(css_class)]


def list_titles(doc: lxml_html.HtmlElement) -> list[str]:
    return texts(doc, "note-title")


def test_home_lists_notebooks_tags_and_all_notes(client: TestClient) -> None:
    doc = page(client, "/")
    notebooks = texts(doc, "notebook-name")
    assert notebooks == ["Inbox", "Recipes"]
    assert "Work" in texts(doc, "stack-name")
    assert texts(doc, "tag-name") == ["breakfast", "food"]
    assert sorted(list_titles(doc)) == ["Pancakes", "Soup", "Tax scan"]


def test_branding_is_nevernote(client: TestClient) -> None:
    doc = page(client, "/")
    assert texts(doc, "brand") == ["Nevernote archive"]
    assert doc.findtext(".//title").endswith("· Nevernote archive")
    assert "Evernote" not in client.get("/").text


def test_notebook_page_lists_its_notes(client: TestClient) -> None:
    home = page(client, "/")
    [href] = home.xpath("//a[span[@class='notebook-name' and text()='Recipes']]/@href")
    doc = page(client, str(href))
    assert list_titles(doc) == ["Soup", "Pancakes"]
    assert texts(doc, "list-heading") == ["Recipes"]


def test_tag_page(client: TestClient) -> None:
    assert sorted(list_titles(page(client, "/tags/food"))) == ["Pancakes", "Soup"]


def test_search_page_highlights_hits(client: TestClient) -> None:
    doc = page(client, "/search?q=potat")
    assert list_titles(doc) == ["Soup"]
    assert [m.text for m in doc.iter("mark")] == ["potatoes"]
    [box] = doc.xpath("//input[@name='q']")
    assert box.get("value") == "potat"


def test_note_page(client: TestClient) -> None:
    doc = page(client, f"/notes/{G1}")
    assert texts(doc, "note-heading") == ["Pancakes"]
    assert texts(doc, "note-tag") == ["breakfast", "food"]
    [frame] = doc.iter("iframe")
    assert frame.get("src") == f"/notes/{G1}/content"
    assert "allow-scripts" not in (frame.get("sandbox") or "")
    source = doc.xpath("//a[@href='https://example.com/pancakes']")
    assert source and source[0].get("target") == "_blank"
    # The list shows the note's notebook, with this note marked current.
    assert list_titles(doc) == ["Soup", "Pancakes"]
    [current] = doc.find_class("current")
    assert "Pancakes" in current.text_content()


def test_note_page_keeps_search_context(client: TestClient) -> None:
    doc = page(client, f"/notes/{G2}?q=potat")
    assert list_titles(doc) == ["Soup"]
    links = [str(a.get("href")) for a in doc.find_class("note-link")]
    assert links == [f"/notes/{G2}?q=potat"]


def test_note_page_lists_attachments(tmp_path: Path, client: TestClient) -> None:
    scan = page(client, "/search?q=tax").find_class("note-link")[0].get("href")
    doc = page(client, str(scan))
    hrefs = [str(a.get("href")) for a in doc.find_class("attachment-link")]
    assert f"/files/{PDF_HASH}/tax%20form.pdf" in hrefs


def test_unknown_note_is_404(client: TestClient) -> None:
    r = client.get("/notes/nope")
    assert r.status_code == 404
    assert "not found" in r.text.lower()


def test_titles_are_escaped(tmp_path: Path) -> None:
    enex = tmp_path / "enex"
    write(enex / "Inbox.enex", note("Scary &lt;script&gt;alert(1)&lt;/script&gt;"))
    build_index(enex, tmp_path / "data")
    r = TestClient(create_app(tmp_path / "data")).get("/")
    assert "<script>alert(1)" not in r.text
    assert "&lt;script&gt;alert(1)" in r.text


def test_list_pagination(tmp_path: Path) -> None:
    enex = tmp_path / "enex"
    write(enex / "Inbox.enex", *(note(f"N{i:02d}") for i in range(5)))
    build_index(enex, tmp_path / "data")
    client = TestClient(create_app(tmp_path / "data", page_size=2))
    first = page(client, "/")
    assert len(list_titles(first)) == 2
    [older] = first.find_class("page-next")
    second = page(client, str(older.get("href")))
    assert len(list_titles(second)) == 2
    assert set(list_titles(first)).isdisjoint(list_titles(second))
    assert second.find_class("page-prev")


def test_missing_index_page(tmp_path: Path) -> None:
    r = TestClient(create_app(tmp_path / "empty")).get("/")
    assert r.status_code == 503
    assert "enex-viewer index" in r.text


def many_notes_client(tmp_path: Path, n: int, page_size: int) -> TestClient:
    enex = tmp_path / "enex"
    write(
        enex / "Inbox.enex",
        *(
            note(f"N{i:03d}", created=f"2024{1 + i // 28:02d}{1 + i % 28:02d}T100000Z")
            for i in range(n)
        ),
    )
    build_index(enex, tmp_path / "data")
    return TestClient(create_app(tmp_path / "data", page_size=page_size))


def test_list_page_loads_script_and_marks_more(tmp_path: Path) -> None:
    client = many_notes_client(tmp_path, 5, page_size=2)
    doc = page(client, "/")
    assert doc.xpath("//script[@src='/static/app.js']")
    [more] = doc.find_class("load-more")
    assert more.get("data-next") == "/ui/items?list=all&offset=2"


def test_items_fragment_continues_the_list(tmp_path: Path) -> None:
    client = many_notes_client(tmp_path, 5, page_size=2)
    first = list_titles(page(client, "/"))
    r = client.get("/ui/items?list=all&offset=2")
    assert r.status_code == 200
    frag = lxml_html.fragment_fromstring(r.text, create_parent="ol")
    titles = [e.text_content().strip() for e in frag.find_class("note-title")]
    assert len(titles) == 2 and set(titles).isdisjoint(first)
    links = [str(a.get("href")) for a in frag.find_class("note-link")]
    assert all(h.endswith("list=all&offset=2") for h in links)
    [more] = frag.find_class("load-more")
    assert more.get("data-next") == "/ui/items?list=all&offset=4"
    last = client.get("/ui/items?list=all&offset=4").text
    assert "load-more" not in last
    assert last.count("note-link") == 1


def test_note_fragment(client: TestClient) -> None:
    r = client.get(f"/ui/note/{G1}?q=flour")
    assert r.status_code == 200
    frag = lxml_html.fragment_fromstring(r.text, create_parent="div")
    assert texts(frag, "note-heading") == ["Pancakes"]
    [head] = frag.find_class("note-head")
    assert head.get("data-title") == "Pancakes · Nevernote archive"
    [back] = frag.find_class("back")
    assert back.get("href") == "/search?q=flour"
    assert frag.findall(".//iframe")
    assert client.get("/ui/note/nope").status_code == 404
