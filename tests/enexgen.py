"""Build ENEX documents for tests, in the shape Evernote and evernote-backup write."""

import base64
from collections.abc import Iterable
from pathlib import Path

# 1x1 transparent PNG
PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
)
PDF = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"


def resource(data: bytes, mime: str, filename: str | None = None) -> str:
    attrs = (
        f"<resource-attributes><file-name>{filename}</file-name></resource-attributes>"
        if filename
        else ""
    )
    return (
        "<resource>"
        f'<data encoding="base64">{base64.b64encode(data).decode()}</data>'
        f"<mime>{mime}</mime>{attrs}"
        "</resource>"
    )


def note(
    title: str,
    content: str = "<div>body</div>",
    *,
    guid: str | None = None,
    metadata_guid: str | None = None,
    created: str | None = "20240101T100000Z",
    updated: str | None = None,
    tags: Iterable[str] = (),
    author: str | None = None,
    source_url: str | None = None,
    resources: Iterable[str] = (),
) -> str:
    parts = [f"<note><title>{title}</title>"]
    parts.append(
        "<content><![CDATA["
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<!DOCTYPE en-note SYSTEM "http://xml.evernote.com/pub/enml2.dtd">'
        f"<en-note>{content}</en-note>]]></content>"
    )
    if created:
        parts.append(f"<created>{created}</created>")
    if updated:
        parts.append(f"<updated>{updated}</updated>")
    parts.extend(f"<tag>{t}</tag>" for t in tags)
    attrs = ""
    if author:
        attrs += f"<author>{author}</author>"
    if source_url:
        attrs += f"<source-url>{source_url}</source-url>"
    parts.append(f"<note-attributes>{attrs}</note-attributes>")
    parts.extend(resources)
    if guid:
        parts.append(f"<guid>{guid}</guid>")
    if metadata_guid:
        parts.append(
            f"<note-custom-metadata><guid>{metadata_guid}</guid></note-custom-metadata>"
        )
    parts.append("</note>")
    return "".join(parts)


def enex(*notes: str) -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        "<!DOCTYPE en-export SYSTEM "
        '"http://xml.evernote.com/pub/evernote-export4.dtd">\n'
        '<en-export export-date="20260923T120000Z" application="Evernote"'
        ' version="10">\n' + "\n".join(notes) + "\n</en-export>\n"
    )


def write(path: Path, *notes: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(enex(*notes), encoding="utf-8")
    return path
