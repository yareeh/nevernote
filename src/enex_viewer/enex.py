"""Stream notes out of ENEX files (Evernote export format).

Notes are parsed one at a time with a pull parser, so multi-GB exports never
have to fit in memory; only the current note and its attachments do.

evernote-backup (1.14.0) wraps note content in <![CDATA[...]]> without
escaping "]]>" inside it, so a web clip that contains its own CDATA section
ends the wrapper early and the file is not well-formed XML. repair_cdata()
fixes that on the fly, the way Evernote's own exporter escapes it.
"""

import base64
import hashlib
import xml.etree.ElementTree as ET
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

ENEX_TIME = "%Y%m%dT%H%M%SZ"


@dataclass(frozen=True)
class Resource:
    hash: str  # md5 of data; what <en-media hash="..."> refers to
    mime: str
    filename: str | None
    data: bytes


@dataclass(frozen=True)
class Note:
    title: str
    content: str  # ENML document as a string
    guid: str | None = None
    created: datetime | None = None
    updated: datetime | None = None
    tags: list[str] = field(default_factory=lambda: [])
    author: str | None = None
    source_url: str | None = None
    resources: list[Resource] = field(default_factory=lambda: [])


def _text(elem: ET.Element | None) -> str | None:
    if elem is None or elem.text is None:
        return None
    text = elem.text.strip()
    return text or None


def _time(elem: ET.Element | None) -> datetime | None:
    raw = _text(elem)
    if raw is None:
        return None
    try:
        return datetime.strptime(raw, ENEX_TIME).replace(tzinfo=UTC)
    except ValueError:
        return None


def _resource(elem: ET.Element) -> Resource | None:
    data_elem = elem.find("data")
    if data_elem is None or not data_elem.text:
        return None
    data = base64.b64decode(data_elem.text)
    if not data:
        return None
    return Resource(
        hash=hashlib.md5(data).hexdigest(),
        mime=_text(elem.find("mime")) or "application/octet-stream",
        filename=_text(elem.find("resource-attributes/file-name")),
        data=data,
    )


def _note(elem: ET.Element) -> Note:
    guid = _text(elem.find("guid")) or _text(elem.find("note-custom-metadata/guid"))
    resources = [r for r in map(_resource, elem.findall("resource")) if r]
    return Note(
        title=_text(elem.find("title")) or "Untitled",
        content=elem.findtext("content") or "",
        guid=guid,
        created=_time(elem.find("created")),
        updated=_time(elem.find("updated")),
        tags=[t for t in (_text(e) for e in elem.findall("tag")) if t],
        author=_text(elem.find("note-attributes/author")),
        source_url=_text(elem.find("note-attributes/source-url")),
        resources=resources,
    )


_CONTENT_OPEN = b"<content>"
_CONTENT_CLOSE = b"</content>"
_CDATA_OPEN = b"<![CDATA["
_CDATA_CLOSE = b"]]>"
_CDATA_CLOSE_ESCAPED = b"]]]]><![CDATA[>"  # "]]" + close + reopen + ">"
_WHITESPACE = b" \t\r\n"
_READ_SIZE = 1 << 20


def repair_cdata(chunks: Iterable[bytes]) -> Iterator[bytes]:
    """Escape stray "]]>" inside <content> CDATA sections of an ENEX stream.

    Inside a note's content CDATA, a "]]>" ends the section only when
    whitespace and "</content>" follow; "]]><![CDATA[" is the standard way to
    split a section and is kept. Any other "]]>" is text and gets escaped.
    Output is the same however the input is chunked.
    """
    source = iter(chunks)
    buf = b""
    eof = False
    inside = False

    def more() -> None:
        nonlocal buf, eof
        try:
            buf += next(source)
        except StopIteration:
            eof = True

    def skip_ws(i: int) -> int:
        while i < len(buf) and buf[i] in _WHITESPACE:
            i += 1
        return i

    while True:
        marker = _CDATA_CLOSE if inside else _CONTENT_OPEN
        i = buf.find(marker)
        if i == -1:
            if eof:
                if buf:
                    yield buf
                return
            keep = len(marker) - 1  # the marker may straddle chunks
            if len(buf) > keep:
                yield buf[:-keep]
                buf = buf[-keep:]
            more()
            continue
        after = i + len(marker)
        k = skip_ws(after)
        lookahead = max(len(_CDATA_OPEN), len(_CONTENT_CLOSE))
        if not eof and (k == len(buf) or len(buf) - k < lookahead):
            more()
            continue
        if not inside:
            if buf.startswith(_CDATA_OPEN, k):
                inside = True
                after = k + len(_CDATA_OPEN)
            yield buf[:after]
        elif buf.startswith(_CONTENT_CLOSE, k):
            inside = False
            yield buf[:after]
        elif buf.startswith(_CDATA_OPEN, after):
            after += len(_CDATA_OPEN)
            yield buf[:after]
        else:
            yield buf[:i] + _CDATA_CLOSE_ESCAPED
        buf = buf[after:]


def iter_notes(path: Path) -> Iterator[Note]:
    parser: ET.XMLPullParser[ET.Element] = ET.XMLPullParser(events=("start", "end"))
    root: ET.Element | None = None
    with path.open("rb") as f:
        chunks = iter(lambda: f.read(_READ_SIZE), b"")
        for chunk in repair_cdata(chunks):
            parser.feed(chunk)
            for item in parser.read_events():
                # Only start/end are requested; other event shapes can't occur.
                if len(item) != 2 or not isinstance(item[1], ET.Element):
                    continue
                event, elem = item[0], item[1]
                if root is None:
                    root = elem  # <en-export>
                if event == "end" and elem.tag == "note":
                    yield _note(elem)
                    root.clear()  # drop parsed notes so memory stays flat
    parser.close()
