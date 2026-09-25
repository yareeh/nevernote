from enex_viewer.enml import to_text

ENML = (
    '<?xml version="1.0" encoding="UTF-8"?>'
    '<!DOCTYPE en-note SYSTEM "http://xml.evernote.com/pub/enml2.dtd">'
    "<en-note>{}</en-note>"
)


def test_extracts_text_and_collapses_whitespace() -> None:
    enml = ENML.format(
        "<div><b>Buy</b></div>\n<ul><li>oat   milk</li><li>rye</li></ul>"
    )
    assert to_text(enml) == "Buy oat milk rye"


def test_handles_html_entities() -> None:
    assert to_text(ENML.format("<div>caf&eacute;&nbsp;au&nbsp;lait</div>")) == (
        "café au lait"
    )


def test_ignores_media_and_scripts() -> None:
    enml = ENML.format(
        '<div>before<en-media hash="abc" type="image/png"/>after</div>'
        "<script>evil()</script><style>p{}</style>"
    )
    assert to_text(enml) == "before after"


def test_empty_and_broken_content() -> None:
    assert to_text("") == ""
    assert to_text(ENML.format("<div>unclosed <b>bold")) == "unclosed bold"
