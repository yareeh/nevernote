import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).parent.parent


def make_groups() -> dict[str, set[str]]:
    """Makefile targets by their `##@ Group` heading."""
    groups: dict[str, set[str]] = {}
    current = None
    for line in (ROOT / "Makefile").read_text().splitlines():
        if line.startswith("##@ "):
            current = line[4:].strip()
            groups[current] = set()
        elif m := re.match(r"^([a-z][a-z-]*):", line):
            assert current, f"target {m.group(1)} is before any ##@ group"
            groups[current].add(m.group(1))
    return groups


def test_targets_are_grouped_into_operating_and_development() -> None:
    groups = make_groups()
    assert list(groups) == ["Operating", "Development"]
    assert {"dev", "check"} <= groups["Development"]
    assert {"viewer-up", "evernote-export"} <= groups["Operating"]


def test_make_help_prints_groups() -> None:
    out = subprocess.run(
        ["make", "--no-print-directory", "help"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    lines = [line.split()[0] for line in out.splitlines() if line.strip()]
    operating, development = lines.index("Operating"), lines.index("Development")
    assert operating < lines.index("viewer-up") < development < lines.index("check")
