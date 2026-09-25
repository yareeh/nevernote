"""Command line: `enex-viewer index` and `enex-viewer serve`."""

import argparse
import logging
import os
import sys
from collections.abc import Sequence
from pathlib import Path

from uvicorn import run as uvicorn_run

from enex_viewer.app import create_app
from enex_viewer.index import build_index, index_is_stale

log = logging.getLogger(__name__)


def _parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--enex-dir",
        type=Path,
        default=Path(os.environ.get("ENEX_DIR", "data/enex")),
        help="directory with .enex files, one per notebook (env ENEX_DIR)",
    )
    common.add_argument(
        "--data-dir",
        type=Path,
        default=Path(os.environ.get("DATA_DIR", "data/viewer")),
        help="where the index and attachment files go (env DATA_DIR)",
    )
    parser = argparse.ArgumentParser(prog="enex-viewer")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("index", parents=[common], help="rebuild the index from ENEX files")
    serve = sub.add_parser(
        "serve", parents=[common], help="rebuild the index if stale, then serve"
    )
    serve.add_argument("--host", default=os.environ.get("HOST", "0.0.0.0"))
    serve.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8765")))
    return parser


def _index(enex_dir: Path, data_dir: Path) -> None:
    stats = build_index(enex_dir, data_dir)
    print(
        f"Indexed {stats.notebooks} notebooks, {stats.notes} notes, "
        f"{stats.resources} attachments into {data_dir}"
        + (
            f" ({stats.duplicate_guids} duplicate notes skipped)"
            if stats.duplicate_guids
            else ""
        ),
        flush=True,
    )


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    enex_dir: Path = args.enex_dir
    data_dir: Path = args.data_dir
    if not enex_dir.is_dir():
        print(f"error: {enex_dir} is not a directory", file=sys.stderr)
        return 2
    if args.command == "index":
        _index(enex_dir, data_dir)
        return 0
    if index_is_stale(enex_dir, data_dir):
        _index(enex_dir, data_dir)
    else:
        log.info("index is up to date")
    uvicorn_run(create_app(data_dir), host=args.host, port=args.port)
    return 0


if __name__ == "__main__":
    sys.exit(main())
