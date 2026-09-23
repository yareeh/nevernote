"""Check that each ENEX file became its own notebook with the same note count.

Usage: joplin status | python3 verify_import.py FILE.enex...
Reads the "# Notebooks" section of `joplin status` ("<title>: N notes") from
stdin. Prints a table and exits 1 on any mismatch or unexpected notebook.
"""

import re
import sys
from pathlib import Path

from count_enex_notes import count_notes


def notebook_counts(status):
    counts = {}
    in_section = False
    for line in status.splitlines():
        if line.startswith("# "):
            in_section = line.strip() == "# Notebooks"
            continue
        m = re.match(r"^(.*): (\d+) notes?$", line)
        if in_section and m:
            counts[m.group(1)] = int(m.group(2))
    return counts


def main():
    actual = notebook_counts(sys.stdin.read())
    expected = {Path(p).stem: count_notes([p]) for p in sys.argv[1:]}
    ok = True
    for name in sorted(expected.keys() | actual.keys()):
        exp, got = expected.get(name), actual.get(name)
        mark = "ok" if exp == got else "MISMATCH"
        ok &= exp == got
        print(f"  {mark:8} {name}: expected {exp}, got {got}")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
