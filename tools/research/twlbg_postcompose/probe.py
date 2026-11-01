#!/usr/bin/env python3
"""Read-only inventory of historical TwlBg signatures in a DECOMPRESSED code dump.

Offsets are file offsets, never patch addresses. A unique short signature is
only a lead for disassembly, not proof of a function/hook or an unused area.
Containers/encrypted firmware are deliberately unsupported. Never uploads.
"""
import argparse
import hashlib
import json
from pathlib import Path

# Primary-source references, pinned in README.md. These are search data only.
PATTERNS = {
    'rtc_update': bytes.fromhex('0025c01d4557002d08d038492669'),
    'pxi_log': bytes.fromhex('f3b5041eadb03cda'),
    'dma_start_commented_experiment': bytes.fromhex('f8b5002504461ae0'),
    'relocation_descriptor': bytes.fromhex('7f0001000000f01e'),
}


def inventory(data):
    if not data or len(data) > 0x400000:
        raise ValueError('Expected nonempty decompressed code, at most 4 MiB')
    if data[:4] in (b'FIRM', b'NCCH') or data[0x100:0x104] == b'NCCH':
        raise ValueError('Extract/decompress the code first; containers are not scanned')
    signatures = {}
    for name, pattern in PATTERNS.items():
        offsets = [i for i in range(0, len(data) - len(pattern) + 1, 2)
                   if data.startswith(pattern, i)]
        signatures[name] = {
            'count': len(offsets), 'file_offsets': [hex(i) for i in offsets],
            'status': 'absent' if not offsets else 'unique_lead' if len(offsets) == 1
                      else 'ambiguous',
        }
    return {
        'sha256': hashlib.sha256(data).hexdigest(), 'size': len(data),
        'deployable': False, 'signatures': signatures,
        'limits': ['Historical short patterns only; firmware identity unverified',
                   'No buffer addresses, lifetime, DMA completion or cache policy established',
                   'No code cave, branch target or installation is authorized by a match'],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('code', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    # Stat before reading to avoid loading arbitrary large dumps.
    if args.code.stat().st_size > 0x400000:
        parser.error('Code dump exceeds 4 MiB')
    try:
        report = inventory(args.code.read_bytes())
    except ValueError as error:
        parser.error(str(error))
    encoded = json.dumps(report, indent=2) + '\n'
    if args.output:
        # Never overwrite even a hardlink/symlink to the inspected firmware.
        with args.output.open('x') as target:
            target.write(encoded)
    print(encoded, end='')


if __name__ == '__main__':
    main()
