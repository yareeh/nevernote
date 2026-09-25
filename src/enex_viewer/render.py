"""Render ENML as safe HTML for the viewer.

ENML-specific elements become plain HTML (<en-media> -> img/video/audio or an
attachment link, <en-todo> -> disabled checkbox, <en-crypt> -> placeholder).
Links between notes (evernote:///view/..., evernote.com/shard/...) point at the
viewer's own note pages when the target GUID is in the index. Relative URLs in
web clips are resolved against the note's source URL. Remote images are
allowed. The result is sanitized with an allowlist (nh3), so no scripts,
event handlers, frames or javascript: URLs survive.
"""

import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit

import nh3
from lxml import etree

from enex_viewer.enml import Element, parse


@dataclass(frozen=True)
class Attachment:
    hash: str
    mime: str
    filename: str | None
    size: int


_GUID = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.IGNORECASE
)

_TAGS = {
    "a", "abbr", "address", "article", "aside", "audio", "b", "bdi", "bdo",
    "blockquote", "br", "caption", "center", "cite", "code", "col", "colgroup",
    "dd", "del", "details", "dfn", "div", "dl", "dt", "em", "figcaption",
    "figure", "font", "footer", "h1", "h2", "h3", "h4", "h5", "h6", "header",
    "hr", "i", "img", "input", "ins", "kbd", "li", "mark", "ol", "p", "pre",
    "q", "s", "samp", "section", "small", "source", "span", "strike", "strong",
    "sub", "summary", "sup", "table", "tbody", "td", "tfoot", "th", "thead",
    "time", "tr", "tt", "u", "ul", "var", "video", "wbr",
}  # fmt: skip
_ATTRIBUTES = {
    "*": {
        "style", "class", "title", "dir", "lang", "align", "valign", "width",
        "height", "bgcolor", "border",
    },
    "a": {"href", "target", "hreflang"},
    "img": {"src", "alt"},
    "video": {"src", "controls", "preload"},
    "audio": {"src", "controls", "preload"},
    "source": {"src", "type"},
    "input": {"type", "checked", "disabled"},
    "td": {"colspan", "rowspan"},
    "th": {"colspan", "rowspan", "scope"},
    "ol": {"start", "type"},
    "col": {"span"},
    "colgroup": {"span"},
    "font": {"color", "face", "size"},
}  # fmt: skip
_URL_SCHEMES = {"http", "https", "mailto", "data"}


def _only_image_data_urls(tag: str, attr: str, value: str) -> str | None:
    """Allow data: URLs only as <img src="data:image/...">; web clips use them
    for small inline icons, and an image can't run script."""
    if attr in ("href", "src") and value.strip().lower().startswith("data:"):
        is_image = value.strip().lower().startswith("data:image/")
        return value if tag == "img" and attr == "src" and is_image else None
    return value


def note_link_guid(href: str) -> str | None:
    """GUID of the note an Evernote note link points to, if it is one."""
    try:
        parts = urlsplit(href)
    except ValueError:
        return None
    host = (parts.hostname or "").lower()
    if parts.scheme != "evernote" and not (
        host == "evernote.com" or host.endswith(".evernote.com")
    ):
        return None
    m = _GUID.search(href)
    return m.group(0).lower() if m else None


def human_size(size: int) -> str:
    value = float(size)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{int(value)} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    raise AssertionError("unreachable")


def _absolute(url: str, source_url: str | None) -> str | None:
    """Absolute URL, resolving relative ones against the clip's source URL."""
    url = url.strip()
    if url.startswith("#"):
        return url
    if urlsplit(url).scheme:
        return url
    if source_url and urlsplit(source_url).scheme in ("http", "https"):
        return urljoin(source_url, url)
    return None


def _swap(old: Element, new: Element) -> None:
    new.tail = old.tail
    parent = old.getparent()
    if parent is not None:
        parent.replace(old, new)


def _media(att: Attachment, file_url: str, media_el: Element | None) -> Element:
    kind = att.mime.split("/", 1)[0]
    if kind == "image":
        el = etree.Element("img", src=file_url, alt=att.filename or "")
    elif kind in ("video", "audio"):
        el = etree.Element(kind, src=file_url, controls="", preload="metadata")
    else:
        el = etree.Element("a", href=file_url, target="_blank")
        el.set("class", "en-attachment")
        el.text = f"📎 {att.filename or att.mime} "
        size = etree.SubElement(el, "span")
        size.set("class", "en-size")
        size.text = f"({human_size(att.size)})"
        return el
    if media_el is not None:
        for name in ("width", "height", "style"):
            value = media_el.get(name)
            if value:
                el.set(name, value)
    return el


def render(
    enml: str,
    *,
    attachments: Sequence[Attachment],
    resolve_guid: Callable[[str], str | None],
    source_url: str | None = None,
    file_url: Callable[[str], str] = lambda h: f"/files/{h}",
    note_url: Callable[[str], str] = lambda i: f"/notes/{i}",
) -> str:
    root = parse(enml)
    by_hash = {a.hash.lower(): a for a in attachments}
    used: set[str] = set()

    for el in list(root.iter("en-media", "en-todo", "en-crypt", "a", "img")):
        tag = el.tag
        if tag == "en-media":
            att = by_hash.get((el.get("hash") or "").lower())
            if att is None:
                new = etree.Element("span")
                new.set("class", "en-missing")
                new.text = "[missing attachment]"
            else:
                used.add(att.hash.lower())
                new = _media(att, file_url(att.hash), el)
            _swap(el, new)
        elif tag == "en-todo":
            new = etree.Element("input", type="checkbox", disabled="")
            if (el.get("checked") or "").lower() == "true":
                new.set("checked", "")
            _swap(el, new)
        elif tag == "en-crypt":
            new = etree.Element("span")
            new.set("class", "en-crypt")
            new.text = "[encrypted content]"
            _swap(el, new)
        elif tag == "a":
            _link(el, resolve_guid, source_url, note_url)
        else:  # img
            src = _absolute(el.get("src") or "", source_url)
            if src is None or _only_image_data_urls("img", "src", src) is None:
                _swap(el, etree.Element("span"))
            else:
                el.set("src", src)

    style = root.get("style")
    root.tag = "div"
    root.attrib.clear()
    root.set("class", "en-note")
    if style:
        root.set("style", style)

    unused = [a for a in attachments if a.hash.lower() not in used]
    if unused:
        section = etree.SubElement(root, "div")
        section.set("class", "en-attachments")
        etree.SubElement(section, "h4").text = "Attachments"
        items = etree.SubElement(section, "ul")
        for att in unused:
            etree.SubElement(items, "li").append(_media(att, file_url(att.hash), None))

    html = etree.tostring(root, method="html", encoding="unicode")
    return nh3.clean(
        html,
        tags=_TAGS,
        attributes=_ATTRIBUTES,
        url_schemes=_URL_SCHEMES,
        attribute_filter=_only_image_data_urls,
        strip_comments=True,
        link_rel="noopener noreferrer",
    )


def _link(
    el: Element,
    resolve_guid: Callable[[str], str | None],
    source_url: str | None,
    note_url: Callable[[str], str],
) -> None:
    href = el.get("href")
    if href is None:
        return
    for name in ("target", "rel", "rev"):
        if name in el.attrib:
            del el.attrib[name]
    guid = note_link_guid(href)
    if guid is not None or urlsplit(href).scheme == "evernote":
        note_id = resolve_guid(guid) if guid else None
        if note_id:
            el.set("href", note_url(note_id))
            el.set("target", "_top")
        else:
            el.tag = "span"
            el.attrib.clear()
            el.set("class", "en-link-unresolved")
            el.set("title", "Link to a note that is not in this archive")
        return
    absolute = _absolute(href, source_url)
    if absolute is None:
        del el.attrib["href"]
        return
    el.set("href", absolute)
    if urlsplit(absolute).scheme in ("http", "https"):
        el.set("target", "_blank")
