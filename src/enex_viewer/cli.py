"""Command line: `enex-viewer index`."""

import argparse
import logging
import os
import sys
from collections.abc import Sequence
from pathlib import Path

from enex_viewer.index import build_index


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
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    enex_dir: Path = args.enex_dir
    data_dir: Path = args.data_dir
    if not enex_dir.is_dir():
        print(f"error: {enex_dir} is not a directory", file=sys.stderr)
        return 2
    stats = build_index(enex_dir, data_dir)
    print(
        f"Indexed {stats.notebooks} notebooks, {stats.notes} notes, "
        f"{stats.resources} attachments into {data_dir}"
        + (
            f" ({stats.duplicate_guids} duplicate notes skipped)"
            if stats.duplicate_guids
            else ""
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
