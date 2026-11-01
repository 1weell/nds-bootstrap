#!/usr/bin/env python3
"""Summarize a negative graphics experiment; never certify hardware behavior."""
import argparse
import collections
import csv
import gzip
import json
import struct
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('baseline')
parser.add_argument('candidate')
parser.add_argument('--output', type=Path)
args = parser.parse_args()

def read(prefix, suffix):
    p = Path(prefix + suffix)
    return p.read_bytes() if p.exists() else gzip.decompress(Path(str(p) + '.gz').read_bytes())

base = list(csv.DictReader(read(args.baseline, '-metrics.csv').decode().splitlines()))
rows = list(csv.DictReader(read(args.candidate, '-metrics.csv').decode().splitlines()))
a, b = read(args.baseline, '-lines.bin'), read(args.candidate, '-lines.bin')
assert len(base) == len(rows) and len(a) == len(b) == len(rows) * 3072
outside, changed, after = [], [], []
for i, row in enumerate(rows):
    assert row['frame'] == base[i]['frame'] == str(i)
    aa, bb = struct.unpack_from('<384Q', a, 3072*i), struct.unpack_from('<384Q', b, 3072*i)
    differences = [j for j, (x, y) in enumerate(zip(aa, bb)) if x != y]
    if differences:
        changed.append(i)
    start = (192 if int(row['power'], 16) & 0x8000 else 0) + int(row['row']) * 8
    bad = [j for j in differences if not int(row['left']) or not start <= j < start+16]
    if bad:
        outside.append({'frame': i, 'first_line': min(bad), 'last_line': max(bad)})
    if differences and row['left'] == '0' and int(row['shows']):
        after.append(i)

active = [r for r in rows if int(r['left'])]
bg_active = [r for r in active if r['sprites'] == '0']
sprite_active = [r for r in active if r['sprites'] != '0']
first = bg_active[0] if bg_active else None
layer = int(first['layer']) if first else 0
block = (int(first[f'bg{layer}'], 16) >> 2) & 15 if first else 0
def bank_count(r):
    return ((int(r['C'], 16) & 0x87) == 0x84) + ((int(r['H'], 16) & 0x83) == 0x81 and block < 2) + ((int(r['I'], 16) & 0x83) == 0x81 and block == 2)

denials = []
last_denied = 0
for r in rows:
    count = int(r['denied'])
    if count > last_denied:
        flags = int(r['admission_flags'])
        denials.append({k: r[k] for k in ('frame', 'display', 'admission_flags', 'disabled_oam', 'used_slots')} |
                      {'gates': {name: bool(flags & (1 << i)) for i, name in enumerate(
                          ('obj_enabled', 'tile_1d', 'one_obj_bank', 'eight_admissible_entries', 'spare_2k_slot'))}})
    last_denied = count

oam_summary = None
oam_path = Path(args.candidate + '-preview-oam.bin')
if oam_path.exists():
    entries = list(struct.iter_unpack('<4H', oam_path.read_bytes()))
    counts = collections.Counter(tuple(e[:3]) for e in entries)
    oam_summary = {'entries_with_disable_bit': sum((e[0] & 0x300) == 0x200 for e in entries),
                   'common_attributes': [{'attributes': [hex(x) for x in v], 'count': n}
                                         for v, n in counts.most_common(4)],
                   'tail_120_127': [[hex(v) for v in e[:3]] for e in entries[120:128]]}

summary = {
    'frames': len(rows), 'different_frames': len(changed),
    'changed_frames_outside_active_band': len(outside), 'first_outside': outside[:8],
    'changed_frames_after_popup_lifetime': len(after), 'first_after_lifetime': after[:8],
    'active_clock_frames': len(active), 'selected_bg_layer': layer, 'selected_bg_block': block,
    'active_frames_without_unique_physical_bg_backing': sum(bank_count(r) != 1 for r in bg_active),
    'active_frames_bg_disabled': sum(not (int(r['display'], 16) & (1 << (8+layer))) for r in bg_active),
    'active_frames_ink_not_white': [int(r['frame']) for r in bg_active if r['bg_ink'] != '7fff'],
    'active_sprite_clock_frames': len(sprite_active),
    'sprite_frames_with_eight_owned_entries': sum(r.get('owned_oam') == '8' for r in sprite_active),
    'denial_events': denials, 'preview_oam': oam_summary,
    'last': rows[-1],
    'limits': 'Host compositor has zero emulated CPU cost; no nds-bootstrap boot, MPU/WRAM/cache integration or hardware timing. Fixed-line late mode is only an ordering oracle. Reported outside-band changes are failures, not successful compatibility results.'
}
text = json.dumps(summary, indent=2) + '\n'
if args.output:
    args.output.write_text(text)
print(text, end='')
