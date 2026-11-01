#!/usr/bin/env python3
"""Synthetic integrity/BLZ tests. Optional differential oracle: ndspy source dir."""
import argparse
import hashlib
import importlib
import json
from pathlib import Path
import random
import struct
import sys
import types

from extract import decode_blz, extract, MAX_SIZE

checks = 0


def check(value):
    global checks
    checks += 1
    if not value:
        raise AssertionError('Check '+str(checks))


def reject(call):
    try:
        call()
    except ValueError:
        check(True)
    else:
        check(False)


def make_ncch(code, compressed=False):
    exefs_size = ((len(code)+0x200+0x1ff)//0x200)*0x200
    data = bytearray(0xa00+exefs_size)
    data[0x100:0x104] = b'NCCH'
    struct.pack_into('<I', data, 0x104, len(data)//0x200)
    struct.pack_into('<I', data, 0x180, 0x400)
    data[0x18f] = 4
    data[0x200:0x208] = b'TwlBg\0\0\0'
    data[0x20d] = int(compressed)
    data[0x160:0x180] = hashlib.sha256(data[0x200:0x600]).digest()
    struct.pack_into('<III', data, 0x1a0, 5, exefs_size//0x200, 1)
    struct.pack_into('<8sII', data, 0xa00, b'.code\0\0\0', 0, len(code))
    data[0xbe0:0xc00] = hashlib.sha256(code).digest()
    data[0xc00:0xc00+len(code)] = code
    data[0x1c0:0x1e0] = hashlib.sha256(data[0xa00:0xc00]).digest()
    return bytes(data)


def make_firm(ncch):
    firm = bytearray(0x200)+ncch
    firm[:4] = b'FIRM'
    struct.pack_into('<IIII', firm, 0x40, 0x200, 0x100000, len(ncch), 0)
    firm[0x50:0x70] = hashlib.sha256(ncch).digest()
    return bytes(firm)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ndspy-reference', type=Path)
    args = parser.parse_args()
    code = bytes(range(256))*4
    ncch = make_ncch(code)
    decoded, report = extract(ncch)
    check(decoded == code and not report['deployable'])
    decoded, report = extract(make_firm(ncch))
    check(decoded == code and len(report['firm_sections']) == 1)
    for length in (0, 1, 255, 511, 512, 513):
        reject(lambda length=length: extract(ncch[:length]))
    for position in (0x160, 0x200, 0xa00, 0xbe0, 0xc00):
        changed = bytearray(ncch)
        changed[position] ^= 1
        reject(lambda changed=changed: extract(changed))
    changed = bytearray(ncch);changed[0x18f] = 0
    reject(lambda: extract(changed))
    changed = bytearray(make_firm(ncch));changed[0x50] ^= 1
    reject(lambda: extract(changed))
    changed = bytearray(make_firm(ncch))
    changed[0x70:0xa0] = changed[0x40:0x70]
    reject(lambda: extract(changed))
    for length in range(8):
        reject(lambda length=length: decode_blz(bytes(length)))
    reject(lambda: decode_blz(struct.pack('<II', 0x08000009, MAX_SIZE)))
    reject(lambda: decode_blz(b'\x00\x00\x80'+struct.pack('<II', 0x0800000b, 10)))
    # Hand-built reverse stream: 3 literal A's then 18 bytes at distance 3.
    packed = b'\x00\xf0AAA\x10'+struct.pack('<II', 0x0800000e, 7)
    check(decode_blz(packed) == b'A'*21)
    decoded, report = extract(make_firm(make_ncch(packed, True)))
    check(decoded == b'A'*21 and report['compressed'])
    reference_cases = 0
    if args.ndspy_reference:
        package = types.ModuleType('reference_ndspy')
        package.__path__ = [str(args.ndspy_reference.resolve())]
        sys.modules['reference_ndspy'] = package
        reference = importlib.import_module('reference_ndspy.codeCompression')
        randomizer = random.Random(20261029)
        samples = [b'A'*n for n in (32, 64, 4096, 65536)]
        for length in (32, 127, 1024, 4096, 32768):
            samples += [bytes(randomizer.randrange(256) for _ in range(length)),
                        (bytes(range(64))*(length//64+1))[:length],
                        bytes(randomizer.randrange(4) for _ in range(length))]
        for sample in samples:
            packed = reference.compress(sample)
            expected = reference.decompress(packed)
            check(decode_blz(packed) == expected)
            decoded, _ = extract(make_firm(make_ncch(packed, True)))
            check(decoded == expected)
            reference_cases += 1
    print(json.dumps({'checks': checks, 'reference_cases': reference_cases,
                      'scope': 'Synthetic fixtures; no console dump tested'}))


if __name__ == '__main__':
    main()
