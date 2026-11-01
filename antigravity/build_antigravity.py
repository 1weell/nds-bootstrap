#!/usr/bin/env python3
"""Antigravity TwlBg Builder.
Builds TwlBg.cxi with live on-screen telemetry banner.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent

# Use helper modules from twlbg_postcompose
sys.path.insert(0, str(ROOT / 'tools/research/twlbg_postcompose'))
from extract import extract, get_ncch
from inspect_console import inspect, thumb_call
from inspect_kernel import inspect_kernel, FIRM_SHA256

BASE = 0x12e160


def digest(data):
    return hashlib.sha256(data).hexdigest()


def align(value, unit):
    return (value + unit - 1) & -unit


def thumb_bl(address, target):
    delta = target - address - 4
    if delta & 1 or not -0x400000 <= delta < 0x400000:
        raise ValueError('Thumb BL outside ARMv6 range')
    return struct.pack('<HH', 0xf000 | ((delta >> 12) & 0x7ff),
                       0xf800 | ((delta >> 1) & 0x7ff))


def build(firm_path, output, ocr=False, private=False):
    private = private or ocr
    firm = firm_path.read_bytes()
    if digest(firm) != FIRM_SHA256:
        raise ValueError('Unknown firmware; no candidate generated')
    code, metadata = extract(firm)
    inspect(code, metadata)
    kernel = inspect_kernel(firm)
    if not (kernel['services']['0x28']['present'] and
            kernel['services']['0x28']['permitted_by_twlbg_exheader']):
        raise ValueError('GetSystemTick is unavailable in this firmware')
    ncch, _ = get_ncch(firm)
    native_end = 0x300000 + len(code)
    native_bss = metadata['declared_bss_size']
    native_source = align(native_end + native_bss, 32)
    output.mkdir(parents=True, exist_ok=True, mode=0o700)
    output.chmod(0o700)  # Contains extracted firmware; never a public build directory.

    dkp = Path(os.environ.get('DEVKITPRO', '/opt/devkitpro'))
    prefix = dkp / 'devkitARM/bin/arm-none-eabi-'
    font = ROOT / 'retail/cardenginei/arm9_ra'
    sources = [
        HERE / 'payload/loader.S',
        HERE / 'payload/payload.c',
        HERE / 'payload/runtime.c',
        HERE / 'postcompose.c',
        font / 'source/ra_text.c'
    ]
    flags = [
        '-mcpu=mpcore', '-mthumb', '-mfloat-abi=soft', '-Os', '-g',
        '-ffreestanding', '-fno-builtin', '-fno-unwind-tables',
        '-fno-jump-tables', '-fno-asynchronous-unwind-tables',
        '-ffunction-sections', '-fdata-sections',
        '-fstack-usage', '-Wall', '-Wextra', '-Werror', '-std=gnu11',
        f'-DRA_NATIVE_SOURCE={native_source}',
        '-DRA_OCR_FALLBACK=' + ('1' if ocr else '0'),
        '-DRA_PRIVATE_OUTPUT=' + ('1' if private else '0'),
        '-I' + str(HERE),
        '-I' + str(font / 'include'),
        '-I' + str(ROOT / 'retail/common/include'),
        '-I' + str(ROOT / 'tools/research/tetris_gfx_order/research_include')
    ]

    commands, objects = [], []
    for number, source in enumerate(sources):
        obj = output / f'payload-{number}.o'
        command = [str(prefix) + 'gcc', *flags, '-c', str(source), '-o', str(obj)]
        subprocess.run(command, check=True)
        commands.append(command)
        objects.append(obj)

    elf, binary = output / 'ra-twlbg.elf', output / 'ra-twlbg.bin'
    command = [
        str(prefix) + 'gcc', '-mcpu=mpcore', '-mthumb', '-mfloat-abi=soft',
        '-nostdlib', '-Wl,--gc-sections', '-Wl,-u,ra_present',
        '-Wl,-Map,' + str(output / 'ra-twlbg.map'),
        '-T', str(HERE / 'payload/payload.ld'), *map(str, objects), '-lgcc', '-o', str(elf)
    ]
    if private:
        command.insert(1, '-Wl,-u,ra_heap_initialize')
    subprocess.run(command, check=True)
    commands.append(command)
    subprocess.run([str(prefix) + 'objcopy', '-O', 'binary', str(elf), str(binary)], check=True)

    symbols = {}
    nm = subprocess.check_output([str(prefix) + 'nm', '-n', str(elf)], text=True)
    for line in nm.splitlines():
        parts = line.split()
        if len(parts) == 3:
            symbols[parts[2]] = int(parts[0], 16)

    payload = binary.read_bytes()
    expected_size = symbols['__payload_file_end'] - BASE
    if len(payload) > expected_size:
        raise ValueError('Binary exceeds declared file extent')
    payload = payload.ljust(expected_size, b'\0')
    binary.write_bytes(payload)
    reserved_end = symbols['__reserved_end']

    if (symbols['__payload_start'] != BASE or len(payload) % 4 or
            symbols['__bss_end'] > reserved_end or reserved_end > 0x132000):
        raise ValueError('Payload reservation contract failed')

    patched = bytearray(code)
    edits = []

    def edit(offset, wanted, replacement, reason):
        if bytes(patched[offset:offset + len(wanted)]) != wanted or len(wanted) != len(replacement):
            raise ValueError('Unexpected bytes at ' + hex(offset))
        patched[offset:offset + len(wanted)] = replacement
        edits.append({'file_offset': hex(offset), 'before': wanted.hex(),
                      'after': replacement.hex(), 'purpose': reason})

    source_offset = 0x1f040
    for address in (0x10109c, 0x10110c):
        edit(source_offset + address - 0x100000, struct.pack('<I', BASE),
             struct.pack('<I', reserved_end), 'Move original ARM11 heap start/size together')
    edit(0x180, struct.pack('<I', BASE), struct.pack('<I', reserved_end),
         'Update native startup declared runtime end')

    original_init_call = code[0x166:0x16a]
    if thumb_call(code, 0x100166) != 0x1053e0:
        raise ValueError('Native cache call differs')
    edit(0x166, original_init_call, thumb_bl(0x300166, native_source), 'Initialize reserved payload')

    call_offset = source_offset + 0x106090 - 0x100000
    runtime = code[source_offset:source_offset + 0x281cc]
    if thumb_call(runtime, 0x106090) != 0x1088c0:
        raise ValueError('Presentation call differs')
    if thumb_call(runtime, 0x10560c) != 0x11045c:
        raise ValueError('VRAM allocator call differs')
    edit(call_offset, code[call_offset:call_offset + 4],
         thumb_bl(0x106090, symbols['ra_present']), 'Compose private output immediately before LCD publication')
    if private:
        heap_call = source_offset + 0x102994 - 0x100000
        if thumb_call(runtime, 0x102994) != 0x104332:
            raise ValueError('VRAM heap initialization call differs')
        edit(heap_call, code[heap_call:heap_call + 4],
             thumb_bl(0x102994, symbols['ra_heap_initialize']),
             'Invalidate owned output allocation epoch before native VRAM heap initialization')

    patched.extend(bytes(native_source - native_end))
    patched.extend(payload)
    new_code = bytes(patched)

    ext = bytearray(ncch[0x200:0x600])
    ext[0x0d] &= ~1  # uncompressed ExeFS .code
    old_data_size = struct.unpack_from('<I', ext, 0x38)[0]
    new_data_size = old_data_size + len(new_code) - len(code)
    struct.pack_into('<I', ext, 0x34, align(new_data_size, 4096) // 4096)
    struct.pack_into('<I', ext, 0x38, new_data_size)
    struct.pack_into('<I', ext, 0x3c, 0)

    exefs = bytearray(0x200 + align(len(new_code), 0x200))
    struct.pack_into('<8sII', exefs, 0, b'.code\0\0\0', 0, len(new_code))
    exefs[0x1e0:0x200] = hashlib.sha256(new_code).digest()
    exefs[0x200:0x200 + len(new_code)] = new_code

    header = bytearray(ncch[:0xa00])
    header[0x200:0x600] = ext
    struct.pack_into('<I', header, 0x104, (len(header) + len(exefs)) // 0x200)
    struct.pack_into('<III', header, 0x1a0, 5, len(exefs) // 0x200, 1)
    header[0x160:0x180] = hashlib.sha256(ext).digest()
    header[0x1c0:0x1e0] = hashlib.sha256(exefs[:0x200]).digest()

    cxi = bytes(header + exefs)
    decoded, _ = extract(cxi)
    if decoded != new_code:
        raise ValueError('Generated CXI failed integrity roundtrip')

    (output / 'TwlBg.cxi').write_bytes(cxi)
    (output / 'twlbg-code-patched.bin').write_bytes(new_code)
    (output / 'TwlBg.original.cxi').write_bytes(ncch)

    report = {
        'status': 'antigravity_candidate_built',
        'renderer': 'ocr-compatibility' if ocr else 'typed-events',
        'compositor': 'experimental-private' if private else 'in-place-hud-cache-span',
        'hardware_validated': False,
        'source_sha256': {
            str(path.relative_to(ROOT)): digest(path.read_bytes())
            for path in sorted(set(sources + [
                HERE / 'build_antigravity.py', HERE / 'payload/font.h',
                HERE / 'payload/notify.h', HERE / 'payload/payload.ld',
                ROOT / 'retail/common/include/ra_bridge.h'
            ]))
        },
        'cxi_sha256': digest(cxi),
        'patched_code_sha256': digest(new_code),
        'native_payload_source': hex(native_source),
        'payload_runtime': hex(BASE),
        'symbols': {k: hex(v) for k, v in symbols.items()},
        'edits': edits
    }
    (output / 'manifest.json').write_text(json.dumps(report, indent=2))
    print(f"Build SUCCESS! CXI SHA256: {digest(cxi)}")
    print(f"Output saved to: {output / 'TwlBg.cxi'}")
    return cxi


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('firm', type=Path, nargs='?',
                        default=Path('/path/to/projects/ra-overlay-research-20261029/twlbg-console-dump-000/twl.firm'))
    parser.add_argument('output', type=Path, nargs='?',
                        default=HERE / 'build')
    parser.add_argument('--ocr', action='store_true', help='Experimental legacy banner compatibility; requires DS overlay')
    parser.add_argument('--private-output', action='store_true', help='Experimental VRAM pool; failed allocation on the tested console')
    args = parser.parse_args()
    build(args.firm, args.output, args.ocr, args.private_output)


if __name__ == '__main__':
    main()
