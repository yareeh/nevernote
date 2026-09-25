"""Stream notes out of ENEX files (Evernote export format).

Notes are parsed one at a time with iterparse, so multi-GB exports never have
to fit in memory; only the current note and its attachments do.
"""

import base64
import hashlib
import xml.etree.ElementTree as ET
from collections.abc import Iterator
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


def iter_notes(path: Path) -> Iterator[Note]:
    events = ET.iterparse(path, events=("start", "end"))
    _, root = next(events)  # <en-export>
    for event, elem in events:
        if event == "end" and elem.tag == "note":
            yield _note(elem)
            root.clear()  # drop parsed notes so memory stays flat
