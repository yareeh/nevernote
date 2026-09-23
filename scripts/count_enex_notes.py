"""Print the total number of <note> elements across the given ENEX files.

Streams with iterparse so multi-GB exports don't need to fit in memory.
"""

import sys
import xml.etree.ElementTree as ET


def count_notes(paths):
    total = 0
    for path in paths:
        for _, elem in ET.iterparse(path, events=("end",)):
            if elem.tag == "note":
                total += 1
                elem.clear()
    return total


if __name__ == "__main__":
    print(count_notes(sys.argv[1:]))
