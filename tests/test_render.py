from urllib.parse import unquote

import pytest
from lxml import html as lxml_html

from enex_viewer.render import Attachment, note_link_guid, render

IMG = Attachment(hash="a" * 32, mime="image/png", filename="dot.png", size=68)
PDF = Attachment(hash="b" * 32, mime="application/pdf", filename="form.pdf", size=2048)
VID = Attachment(hash="c" * 32, mime="video/mp4", filename=None, size=10)
DOCX = Attachment(
    hash="d" * 32,
    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    filename="memo.docx",
    size=5_000_000,
)
G2 = "22222222-2222-2222-2222-222222222222"
MISSING = "99999999-9999-9999-9999-999999999999"


def enml(body: str, note_style: str = "") -> str:
    style = f' style="{note_style}"' if note_style else ""
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<!DOCTYPE en-note SYSTEM "http://xml.evernote.com/pub/enml2.dtd">'
        f"<en-note{style}>{body}</en-note>"
    )


def do(
    body: str,
    attachments: list[Attachment] | None = None,
    source_url: str | None = None,
    note_style: str = "",
) -> lxml_html.HtmlElement:
    out = render(
        enml(body, note_style),
        attachments=attachments or [],
        resolve_guid=lambda g: g if g == G2 else None,
        source_url=source_url,
    )
    return lxml_html.fragment_fromstring(out, create_parent="div")


def test_image_media_becomes_img() -> None:
    doc = do(f'<en-media hash="{IMG.hash}" type="image/png" width="40"/>', [IMG])
    [img] = doc.findall(".//img")
    assert img.get("src") == f"/files/{IMG.hash}"
    assert img.get("width") == "40"
    assert img.get("alt") == "dot.png"


def test_pdf_media_becomes_attachment_link() -> None:
    doc = do(f'<en-media hash="{PDF.hash}" type="application/pdf"/>', [PDF])
    [a] = doc.findall(".//a")
    assert a.get("href") == f"/files/{PDF.hash}"
    assert a.get("target") == "_blank"
    assert "form.pdf" in a.text_content()
    assert "2.0 KB" in a.text_content()
    assert not doc.findall(".//embed") and not doc.findall(".//iframe")


def test_attachment_mime_wins_over_en_media_type() -> None:
    doc = do(f'<en-media hash="{DOCX.hash}" type="application/octet-stream"/>', [DOCX])
    [a] = doc.findall(".//a")
    assert "memo.docx" in a.text_content()
    assert "4.8 MB" in a.text_content()


def test_video_media_becomes_player() -> None:
    doc = do(f'<en-media hash="{VID.hash}" type="video/mp4"/>', [VID])
    [video] = doc.findall(".//video")
    assert video.get("src") == f"/files/{VID.hash}"
    assert video.get("controls") is not None


def test_missing_media_is_marked() -> None:
    doc = do('<en-media hash="deadbeef" type="image/png"/>')
    assert "missing attachment" in doc.text_content()


def test_unreferenced_attachments_are_listed() -> None:
    doc = do("<div>see attached</div>", [PDF])
    [section] = doc.find_class("en-attachments")
    assert "form.pdf" in section.text_content()


def test_referenced_attachments_are_not_listed_again() -> None:
    doc = do(f'<en-media hash="{IMG.hash}" type="image/png"/>', [IMG])
    assert not doc.find_class("en-attachments")


def test_todo_becomes_disabled_checkbox() -> None:
    doc = do('<div><en-todo checked="true"/>done</div><div><en-todo/>open</div>')
    done, open_ = doc.findall(".//input")
    assert done.get("type") == "checkbox"
    assert done.get("checked") is not None
    assert done.get("disabled") is not None
    assert open_.get("checked") is None


def test_encrypted_text_is_a_placeholder() -> None:
    doc = do('<en-crypt cipher="AES" length="128">U2VjcmV0</en-crypt>')
    assert "encrypted" in doc.text_content().lower()
    assert "U2VjcmV0" not in lxml_html.tostring(doc, encoding="unicode")


def test_active_content_is_removed() -> None:
    out = lxml_html.tostring(
        do(
            '<div onclick="evil()">x</div><script>evil()</script><style>*{}</style>'
            '<a href="javascript:evil()">bad</a><iframe src="https://x"></iframe>'
        ),
        encoding="unicode",
    )
    for needle in ("onclick", "<script", "<style", "javascript:", "<iframe"):
        assert needle not in out


def test_remote_images_and_styles_are_kept() -> None:
    doc = do(
        '<div style="color: red"><img src="https://example.com/x.png"/></div>',
        note_style="font-size: 14px",
    )
    assert doc.findall(".//img")[0].get("src") == "https://example.com/x.png"
    assert doc.find(".//div[@style='color: red']") is not None
    assert doc[0].get("style") == "font-size: 14px"


def test_inline_data_images_are_kept_but_data_links_are_not() -> None:
    svg = "data:image/svg+xml,%3csvg xmlns='http://www.w3.org/2000/svg'/%3e"
    doc = do(
        f'<img src="{svg}"/><img src="data:text/html,x"/>'
        '<a href="data:text/html,evil">bad</a>'
    )
    # The sanitizer percent-encodes spaces; compare the decoded URL.
    assert [unquote(img.get("src") or "") for img in doc.findall(".//img")] == [
        unquote(svg)
    ]
    assert not doc.findall(".//a[@href]")


def test_external_links_open_in_new_tab() -> None:
    [a] = do('<a href="https://example.com">site</a>').findall(".//a")
    assert a.get("target") == "_blank"
    assert "noopener" in (a.get("rel") or "")


@pytest.mark.parametrize(
    "href",
    [
        f"evernote:///view/123/s1/{G2}/{G2}/",
        f"https://www.evernote.com/shard/s1/nl/123/{G2}/",
        f"https://www.evernote.com/shard/s1/sh/{G2}/abcdef",
    ],
)
def test_evernote_note_links_resolve(href: str) -> None:
    [a] = do(f'<a href="{href}">other note</a>').findall(".//a")
    assert a.get("href") == f"/notes/{G2}"
    assert a.get("target") == "_top"


def test_unresolved_evernote_link_is_inert() -> None:
    doc = do(f'<a href="evernote:///view/1/s1/{MISSING}/{MISSING}/">gone</a>')
    [span] = doc.find_class("en-link-unresolved")
    assert span.text_content() == "gone"
    assert not doc.findall(".//a[@href]")


def test_relative_urls_resolve_against_source_url() -> None:
    doc = do(
        '<a href="/docs/page">rel</a><img src="img/p.png"/><a href="#top">anchor</a>',
        source_url="https://example.com/blog/post",
    )
    rel, anchor = doc.findall(".//a")
    assert rel.get("href") == "https://example.com/docs/page"
    assert doc.findall(".//img")[0].get("src") == "https://example.com/blog/img/p.png"
    assert anchor.get("href") == "#top"


def test_relative_urls_without_source_are_dropped() -> None:
    doc = do('<a href="/docs/page">rel</a><img src="img/p.png"/>')
    assert not doc.findall(".//a[@href]")
    assert not doc.findall(".//img")


def test_note_link_guid() -> None:
    assert note_link_guid(f"evernote:///view/1/s1/{G2}/{G2}/") == G2
    assert note_link_guid(f"https://www.evernote.com/shard/s9/nl/1/{G2}") == G2
    assert note_link_guid(f"https://example.com/{G2}") is None
    assert note_link_guid("https://www.evernote.com/") is None
