"""Parse ENML (Evernote's XHTML dialect) into an lxml tree, and extract text.

ENML is XML, but notes use HTML named entities (&nbsp;, &eacute;) that are only
defined in Evernote's DTD, and web clips are not always well-formed. So named
entities are turned into numeric references first, and the XML parser runs in
recovery mode. No DTD or network access is ever used.
"""

import re
from html.entities import name2codepoint
from typing import cast

from lxml import etree

# lxml exposes its element type only under a private name.
Element = etree._Element  # pyright: ignore[reportPrivateUsage]

_XML_DECL = re.compile(r"^\s*<\?xml[^>]*\?>", re.IGNORECASE)
_DOCTYPE = re.compile(r"<!DOCTYPE[^>]*>", re.IGNORECASE)
_ENTITY = re.compile(r"&([A-Za-z][A-Za-z0-9]*);")
_XML_ENTITIES = {"lt", "gt", "amp", "quot", "apos"}
_WS = re.compile(r"\s+")

# Elements whose boundaries separate words in extracted text.
_BLOCK = {
    "address", "article", "aside", "blockquote", "br", "dd", "div", "dl", "dt",
    "en-note", "figcaption", "figure", "footer", "h1", "h2", "h3", "h4", "h5",
    "h6", "header", "hr", "li", "ol", "p", "pre", "section", "table", "td",
    "th", "tr", "ul", "en-media", "en-todo", "img",
}  # fmt: skip
_DROP = {"script", "style", "noscript", "title", "head"}

_PARSER = etree.XMLParser(
    recover=True,
    resolve_entities=False,
    no_network=True,
    load_dtd=False,
    huge_tree=True,
    remove_comments=True,
    remove_pis=True,
)


def _numeric_entity(m: re.Match[str]) -> str:
    name = m.group(1)
    if name in _XML_ENTITIES:
        return m.group(0)
    codepoint = name2codepoint.get(name)
    return f"&#{codepoint};" if codepoint else m.group(0)


def parse(enml: str) -> Element:
    """Return the <en-note> element (tags without namespaces)."""
    body = _DOCTYPE.sub("", _XML_DECL.sub("", enml, count=1), count=1).strip()
    body = _ENTITY.sub(_numeric_entity, body)
    root = etree.fromstring(body, _PARSER) if body else None
    if root is None:
        return etree.Element("en-note")
    for el in root.iter():
        tag = cast(object, el.tag)
        if isinstance(tag, str) and "}" in tag:
            el.tag = tag.split("}", 1)[1]
    return root


def to_text(enml: str) -> str:
    """Plain text for search: block boundaries become spaces, media is skipped."""
    out: list[str] = []
    _collect(parse(enml), out)
    return _WS.sub(" ", "".join(out)).strip()


def _collect(el: Element, out: list[str]) -> None:
    # Entity and comment nodes have non-str tags at runtime, despite the stubs.
    raw_tag = cast(object, el.tag)
    tag = raw_tag if isinstance(raw_tag, str) else None
    if tag and tag not in _DROP:
        block = tag in _BLOCK
        if block:
            out.append(" ")
        if el.text:
            out.append(el.text)
        for child in el:
            _collect(child, out)
        if block:
            out.append(" ")
    if el.tail:
        out.append(el.tail)
