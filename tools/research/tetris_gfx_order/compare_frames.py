#!/usr/bin/env python3
"""Compare two research runs; exclude only the overlay's actual panel/row band."""
import argparse
import collections
import csv
import gzip
import json
import struct
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("baseline", help="prefix, e.g. /tmp/ra-overlay-trace-auto")
parser.add_argument("candidate", help="prefix, e.g. /tmp/ra-overlay-split-auto")
args = parser.parse_args()
base = list(csv.DictReader(open(args.baseline + "-hashes.csv")))
rows = list(csv.DictReader(open(args.candidate + "-hashes.csv")))
def read_lines(prefix):
    path = Path(prefix + "-lines.bin")
    if path.exists():
        return path.read_bytes()
    with gzip.open(str(path) + ".gz", "rb") as source:
        return source.read()
a = read_lines(args.baseline)
b = read_lines(args.candidate)
assert len(base) == len(rows), "Frame counts differ"
assert len(a) == len(b) == len(rows) * 384 * 8
outside = []
counts = collections.Counter()
runs = []
start = None
for i, (x, y) in enumerate(zip(base, rows)):
    assert x["frame"] == y["frame"]
    aa = struct.unpack_from("<384Q", a, i * 3072)
    bb = struct.unpack_from("<384Q", b, i * 3072)
    changed = [n for n, (v, w) in enumerate(zip(aa, bb)) if v != w]
    panel = 192 if int(y["power"], 16) & 0x8000 else 0
    first = panel + int(y["row"]) * 8
    bad = [n for n in changed if not first <= n < first + 16]
    if bad:
        outside.append({"frame": i, "lines": bad})
    if changed:
        counts[(y["shows"], y["row"])] += 1
        if start is None:
            start = i
    elif start is not None:
        runs.append([start, i - 1, i - start])
        start = None
if start is not None:
    runs.append([start, len(rows) - 1, len(rows) - start])
print(json.dumps({
    "frames": len(rows),
    "different_frames": sum(counts.values()),
    "frames_by_notification_and_row": [
        {"notification": k[0], "row": k[1], "frames": v}
        for k, v in counts.items()
    ],
    "visible_runs": runs,
    "changed_frames_outside_dynamic_notification_band": len(outside),
    "first_outside": outside[:8],
    "last": rows[-1],
}, indent=2))
assert not outside, "Changes outside notification band"
