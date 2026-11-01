#!/usr/bin/env python3
"""Compare this fixed 1200-frame host model against the archived trace baseline."""
import argparse
import csv
import gzip
import hashlib
import json
from pathlib import Path


def read_lines(prefix):
    file = Path(str(prefix) + '-lines.bin')
    if file.exists():
        return file.read_bytes()
    return gzip.decompress(Path(str(file) + '.gz').read_bytes())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('baseline_prefix', type=Path)
    parser.add_argument('candidate_prefix', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    baseline, candidate = read_lines(args.baseline_prefix), read_lines(args.candidate_prefix)
    with Path(str(args.candidate_prefix) + '-metrics.csv').open() as file:
        rows = list(csv.DictReader(file))
    report = {
        'scope': 'Host postcomposition after melonDS RunFrame; no emulated ARM11 cost or TwlBg execution',
        'frames': len(rows),
        'active_frames': sum(int(r['active']) for r in rows),
        'frames_with_popup_pixels': sum(int(r['changed_pixels']) > 0 for r in rows),
        'outside_band_frames': sum(int(r['outside_band']) > 0 for r in rows),
        'source_changed_frames': sum(int(r['source_changed']) > 0 for r in rows),
        'inactive_changed_frames': sum(not int(r['active']) and int(r['changed_pixels']) > 0 for r in rows),
        'baseline_lines_sha256': hashlib.sha256(baseline).hexdigest(),
        'candidate_lines_sha256': hashlib.sha256(candidate).hexdigest(),
        'emulated_game_scanlines_identical': baseline == candidate,
        'hardware_ready': False,
    }
    passed = (len(rows) == 1200 and len(baseline) == len(candidate) == 1200 * 384 * 8 and
              [int(r['frame']) for r in rows] == list(range(1200)) and
              [int(r['active']) for r in rows] ==
              [int(320 <= i < 500 or 900 <= i < 1080) for i in range(1200)] and
              report['active_frames'] == report['frames_with_popup_pixels'] == 360 and
              not report['outside_band_frames'] and not report['source_changed_frames'] and
              not report['inactive_changed_frames'] and report['emulated_game_scanlines_identical'])
    report['model_passed'] = passed
    with args.output.open('x') as file:
        json.dump(report, file, indent=2)
        file.write('\n')
    print(json.dumps(report, indent=2))
    raise SystemExit(0 if passed else 1)


if __name__ == '__main__':
    main()
