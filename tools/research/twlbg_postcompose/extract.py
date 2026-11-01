#!/usr/bin/env python3
"""Extract locally dumped, decrypted TwlBg. No keys, network, patches or uploads.

Verify FIRM section, NCCH extended-header and ExeFS/code SHA256 before decoding.
These are integrity checks, not RSA authentication or hardware compatibility.
Input must come from the user's own console. Keep binary outputs private.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct

from probe import inventory

MAX_SIZE = 0x400000


def word(data, offset):
    if offset < 0 or offset + 4 > len(data):
        raise ValueError('Truncated integer')
    return struct.unpack_from('<I', data, offset)[0]


def span(data, start, size):
    if start < 0 or size < 0 or start > len(data) or size > len(data) - start:
        raise ValueError('Section extends outside input')
    return data[start:start+size]


def digest(data):
    return hashlib.sha256(data).hexdigest()


def matches_hash(data, expected, name):
    if hashlib.sha256(data).digest() != expected:
        raise ValueError(name + ' SHA256 mismatch')


def decode_blz(data):
    """Bounded backwards LZ, distance biased by 3. No appended-data guessing."""
    if len(data) < 8:
        raise ValueError('Truncated BLZ footer')
    footer, extra = struct.unpack_from('<II', data, len(data)-8)
    if not extra:
        return data
    header, compressed = footer >> 24, footer & 0xffffff
    if not 8 <= header <= compressed <= len(data):
        raise ValueError('Invalid BLZ footer sizes')
    if any(b != 255 for b in data[len(data)-header:len(data)-8]):
        raise ValueError('Invalid BLZ header padding')
    total = len(data) + extra
    if total > MAX_SIZE:
        raise ValueError('BLZ expansion exceeds 4 MiB')
    prefix = len(data) - compressed
    source, target = len(data) - header, total
    output = bytearray(total)
    output[:prefix] = data[:prefix]

    def take():
        nonlocal source
        if source <= prefix:
            raise ValueError('BLZ compressed stream exhausted')
        source -= 1
        return data[source]

    while target > prefix:
        flags = take()
        for bit in range(7, -1, -1):
            if target == prefix:
                break
            if flags & (1 << bit):
                token = (take() << 8) | take()
                length, distance = (token >> 12) + 3, (token & 4095) + 3
                if length > target - prefix or target + distance > total:
                    raise ValueError('Invalid BLZ backreference')
                for _ in range(length):
                    target -= 1
                    output[target] = output[target + distance]
            else:
                target -= 1
                output[target] = take()
    if source != prefix:
        raise ValueError('Unconsumed BLZ compressed bytes')
    return bytes(output)


def get_ncch(data):
    if not 0x200 <= len(data) <= MAX_SIZE:
        raise ValueError('Expected 512 bytes..4 MiB FIRM/NCCH')
    sections = []
    if data[:4] == b'FIRM':
        occupied = []
        for i in range(4):
            position = 0x40 + i * 0x30
            start, address, size, method = struct.unpack_from('<IIII', data, position)
            if not size:
                continue
            if start < 0x200 or start % 0x200:
                raise ValueError('Invalid FIRM section alignment')
            section = span(data, start, size)
            if any(start < end and begin < start + size for begin, end in occupied):
                raise ValueError('Overlapping FIRM sections')
            occupied.append((start, start + size))
            matches_hash(section, data[position+16:position+48], 'FIRM section')
            sections.append({'offset': start, 'size': size, 'load_address': hex(address),
                             'copy_method': method, 'sha256': digest(section)})
        candidates = []
        for section in sections:
            start, end = section['offset'], section['offset'] + section['size']
            for offset in range(start, end - 0x208 + 1, 0x200):
                if (data[offset+0x100:offset+0x104] == b'NCCH' and
                    data[offset+0x200:offset+0x208] == b'TwlBg\0\0\0'):
                    size = word(data, offset+0x104) * 0x200
                    if size < 0x600 or size > end - offset:
                        raise ValueError('TwlBg NCCH exceeds FIRM section')
                    candidates.append((offset, data[offset:offset+size]))
        if len(candidates) != 1:
            raise ValueError('Expected exactly one TwlBg NCCH in verified sections')
        offset, ncch = candidates[0]
    elif data[0x100:0x104] == b'NCCH':
        offset, ncch = 0, data
    else:
        raise ValueError('Expected FIRM or NCCH container')
    return ncch, {'firm_sections': sections, 'ncch_file_offset': hex(offset)}


def extract(data):
    ncch, report = get_ncch(data)
    if word(ncch, 0x104) * 0x200 != len(ncch):
        raise ValueError('NCCH declared size differs from container')
    if not ncch[0x18f] & 4:
        raise ValueError('NCCH still marked encrypted; use a decrypted local dump')
    if ncch[0x18e]:
        raise ValueError('Unsupported NCCH media-unit size')
    ext_size = word(ncch, 0x180)
    if ext_size != 0x400:
        raise ValueError('Unexpected TwlBg extended-header size')
    ext = span(ncch, 0x200, ext_size)
    if ext[:8] != b'TwlBg\0\0\0':
        raise ValueError('Module is not TwlBg')
    matches_hash(ext, ncch[0x160:0x180], 'NCCH extended header')
    exefs_start, exefs_size = word(ncch, 0x1a0)*0x200, word(ncch, 0x1a4)*0x200
    if exefs_start < 0x200 + ext_size or exefs_start % 0x200 or exefs_size < 0x200:
        raise ValueError('Invalid ExeFS location')
    exefs = span(ncch, exefs_start, exefs_size)
    hash_size = word(ncch, 0x1a8)*0x200
    if not 0x200 <= hash_size <= len(exefs):
        raise ValueError('Invalid ExeFS hash region')
    matches_hash(exefs[:hash_size], ncch[0x1c0:0x1e0], 'ExeFS header region')
    codes, occupied = [], []
    for i in range(10):
        name, start, size = struct.unpack_from('<8sII', exefs, i*16)
        if name == bytes(8) and not start and not size:
            continue
        if not name.rstrip(b'\0') or not size:
            raise ValueError('Malformed ExeFS entry')
        start += 0x200
        file = span(exefs, start, size)
        if any(start < end and begin < start + size for begin, end in occupied):
            raise ValueError('Overlapping ExeFS files')
        occupied.append((start, start+size))
        matches_hash(file, exefs[0x200-(i+1)*32:0x200-i*32], 'ExeFS file')
        if name == b'.code\0\0\0':
            codes.append(file)
    if len(codes) != 1:
        raise ValueError('Expected exactly one .code entry')
    packed = codes[0]
    compressed = bool(ext[0x0d] & 1)
    code = decode_blz(packed) if compressed else packed
    if not code or len(code) > MAX_SIZE:
        raise ValueError('Invalid decoded code size')
    report.update({'input_sha256': digest(data), 'ncch_sha256': digest(ncch),
                   'code_stored_sha256': digest(packed), 'code_sha256': digest(code),
                   'compressed': compressed, 'code_size': len(code),
                   'remaster_version': struct.unpack_from('<H', ext, 0x0e)[0],
                   'integrity_checks': 'FIRM sections, extended header, ExeFS region and every file',
                   'signature_authentication': False, 'deployable': False})
    report['declared_code_segments'] = {
        name: {'address': hex(word(ext, offset)), 'pages': word(ext, offset+4),
               'size': word(ext, offset+8)}
        for name, offset in [('text', 0x10), ('rodata', 0x20), ('data', 0x30)]}
    report['declared_stack_size'] = word(ext, 0x1c)
    report['declared_bss_size'] = word(ext, 0x3c)
    return code, report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', type=Path)
    parser.add_argument('output_directory', type=Path)
    args = parser.parse_args()
    if args.input.stat().st_size > MAX_SIZE:
        parser.error('Input exceeds 4 MiB')
    try:
        code, report = extract(args.input.read_bytes())
    except ValueError as error:
        parser.error(str(error))
    args.output_directory.mkdir(parents=True, exist_ok=False)
    (args.output_directory/'twlbg-code.bin').write_bytes(code)
    (args.output_directory/'extraction.json').write_text(json.dumps(report, indent=2)+'\n')
    (args.output_directory/'inventory.json').write_text(json.dumps(inventory(code), indent=2)+'\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
