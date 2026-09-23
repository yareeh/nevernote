"""Print the total number of <note> elements across the given ENEX files.

Streams with iterparse so multi-GB exports don't need to fit in memory.
"""

import sys
import xml.etree.ElementTree as ET

total = 0
for path in sys.argv[1:]:
    for _, elem in ET.iterparse(path, events=("end",)):
        if elem.tag == "note":
            total += 1
            elem.clear()
print(total)
