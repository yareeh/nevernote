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


def readme_section(name: str) -> str:
    readme = (ROOT / "README.md").read_text()
    assert f"\n## {name}\n" in readme, f"README has no '## {name}' section"
    return readme.split(f"\n## {name}\n", 1)[1].split("\n## ", 1)[0]


def test_targets_are_grouped_into_operating_and_development() -> None:
    groups = make_groups()
    assert list(groups) == ["Operating", "Development"]
    assert {"dev", "check"} <= groups["Development"]
    assert {"viewer-up", "evernote-export"} <= groups["Operating"]


def test_readme_sections_describe_each_group_exactly() -> None:
    for group, targets in make_groups().items():
        section = readme_section(group)
        documented = re.findall(r"^\| `make ([a-z-]+)` \|", section, re.MULTILINE)
        assert set(documented) == targets, group


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
