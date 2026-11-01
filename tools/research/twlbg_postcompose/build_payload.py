#!/usr/bin/env python3
"""Build a reversible, exact-image TwlBg synthetic-popup CXI in a private folder.

Does not install anything. Refuses unknown firmware, existing output directories,
unexpected instruction/layout contracts, or an oversized payload reservation.
Hardware acceptance is a separate step; RA transport is not in this candidate.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess

from extract import extract, get_ncch
from inspect_console import inspect, thumb_call
from inspect_kernel import inspect_kernel, FIRM_SHA256

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
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


def build(firm_path, output, diagnostic=False, visual_output=False):
    firm = firm_path.read_bytes()
    if digest(firm) != FIRM_SHA256:
        raise ValueError('Unknown firmware; no candidate generated')
    code, metadata = extract(firm)
    inspect(code, metadata)
    inspect_kernel(firm)
    ncch, _ = get_ncch(firm)
    native_end = 0x300000 + len(code)
    native_bss = metadata['declared_bss_size']
    native_source = align(native_end + native_bss, 32)
    output.mkdir(parents=True, exist_ok=False)
    dkp = Path(os.environ.get('DEVKITPRO', '/opt/devkitpro'))
    prefix = dkp / 'devkitARM/bin/arm-none-eabi-'
    font = ROOT / 'retail/cardenginei/arm9_ra'
    sources = [HERE / 'payload/loader.S', HERE / 'payload/payload.c',
               HERE / 'postcompose.c', font / 'source/ra_text.c']
    flags = ['-mcpu=mpcore', '-mthumb', '-mfloat-abi=soft', '-Os', '-g',
             '-ffreestanding', '-fno-builtin', '-fno-unwind-tables',
             '-fno-jump-tables',
             '-fno-asynchronous-unwind-tables', '-ffunction-sections', '-fdata-sections',
             '-fstack-usage', '-Wall', '-Wextra', '-Werror', '-std=gnu11',
             f'-DRA_NATIVE_SOURCE={native_source}', '-I' + str(HERE),
             '-I' + str(font / 'include'),
             '-I' + str(ROOT / 'retail/common/include'),
             '-I' + str(ROOT / 'tools/research/tetris_gfx_order/research_include')]
    if diagnostic:
        flags.append('-DRA_DIAGNOSTIC=1')
    if visual_output:
        flags.append('-DRA_VISUAL_OUTPUT=1')
    commands, objects = [], []
    for number, source in enumerate(sources):
        obj = output / f'payload-{number}.o'
        command = [str(prefix) + 'gcc', *flags, '-c', str(source), '-o', str(obj)]
        subprocess.run(command, check=True)
        commands.append(command)
        objects.append(obj)
    elf, binary = output / 'ra-twlbg.elf', output / 'ra-twlbg.bin'
    command = [str(prefix) + 'gcc', '-mcpu=mpcore', '-mthumb', '-mfloat-abi=soft',
               '-nostdlib', '-Wl,--gc-sections', '-Wl,-u,ra_present',
               '-Wl,-Map,' + str(output / 'ra-twlbg.map'),
               '-T', str(HERE / 'payload/payload.ld'), *map(str, objects), '-o', str(elf)]
    if diagnostic:
        command.insert(1, '-Wl,-u,ra_signal_frame')
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

    # Runtime source is relocated verbatim; native heap helpers remain outside it.
    source_offset = 0x1f040
    for address in (0x10109c, 0x10110c):
        edit(source_offset + address - 0x100000, struct.pack('<I', BASE),
             struct.pack('<I', reserved_end), 'Move original ARM11 heap start/size together')
    edit(0x180, struct.pack('<I', BASE), struct.pack('<I', reserved_end),
         'Update native startup declared runtime end')
    # Original BLX cache operation becomes a BL to the appended loader, which
    # preserves it and initializes a disjoint, explicitly reserved AXI payload.
    original_init_call = code[0x166:0x16a]
    if thumb_call(code, 0x100166) != 0x1053e0:
        # thumb_call's BASE is 0x100000; native target differs by 0x200000.
        raise ValueError('Native cache call differs')
    edit(0x166, original_init_call, thumb_bl(0x300166, native_source), 'Initialize reserved payload')
    call_offset = source_offset + 0x106090 - 0x100000
    runtime = code[source_offset:source_offset + 0x281cc]
    if thumb_call(runtime, 0x106090) != 0x1088c0:
        raise ValueError('Presentation call differs')
    edit(call_offset, code[call_offset:call_offset + 4],
         thumb_bl(0x106090, symbols['ra_present']), 'Compose private output immediately before LCD publication')
    if diagnostic:
        address = 0x1017a8
        offset = source_offset + address - 0x100000
        if thumb_call(runtime, address) != 0x1182e4:
            raise ValueError('Frame signal call differs')
        edit(offset, code[offset:offset + 4], thumb_bl(address, symbols['ra_signal_frame']),
             'Bounded LCD color diagnostic; preserve original event signal')
    # Preserve all original native BSS addresses by materializing their zeros;
    # the appended loader is beyond that range, not inside an assumed cave.
    patched.extend(bytes(native_source - native_end))
    patched.extend(payload)
    new_code = bytes(patched)
    ext = bytearray(ncch[0x200:0x600])
    ext[0x0d] &= ~1  # generated ExeFS .code is uncompressed
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
    decoded, roundtrip = extract(cxi)
    if decoded != new_code:
        raise ValueError('Generated CXI failed integrity roundtrip')
    (output / 'TwlBg.cxi').write_bytes(cxi)
    (output / 'twlbg-code-patched.bin').write_bytes(new_code)
    (output / 'TwlBg.original.cxi').write_bytes(ncch)
    report = {'status': 'candidate_built_requires_validation', 'hardware_tested': False,
              'production_ra_transport': False, 'input_firm_sha256': digest(firm),
              'temporary_color_diagnostic': diagnostic,
              'temporary_visual_output': visual_output,
              'original_code_sha256': digest(code), 'patched_code_sha256': digest(new_code),
              'cxi_sha256': digest(cxi), 'original_cxi_sha256': digest(ncch),
              'native_payload_source': hex(native_source), 'payload_runtime': hex(BASE),
              'payload_file_bytes': len(payload), 'payload_bss_end': hex(symbols['__bss_end']),
              'original_heap_start': hex(BASE), 'new_heap_start': hex(reserved_end),
              'heap_bytes_reserved': reserved_end - BASE, 'kernel_owned_axi_end': '0x154000',
              'symbols': {k: hex(v) for k, v in symbols.items() if k.startswith(('ra_', '__'))},
              'edits': edits, 'commands': commands,
              'source_sha256': {str(p): digest(p.read_bytes()) for p in [*sources, HERE / 'payload/payload.ld', Path(__file__)]},
              'roundtrip_code_size': roundtrip['code_size'],
              'signature_authentication': False,
              'scope': 'Synthetic bottom-screen popup only. Exact image. No console mutation.'}
    (output / 'manifest.json').write_text(json.dumps(report, indent=2) + '\n')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('firm', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--diagnostic', action='store_true')
    parser.add_argument('--visual-output', action='store_true')
    args = parser.parse_args()
    report = build(args.firm, args.output.resolve(), args.diagnostic, args.visual_output)
    print(json.dumps({k: report[k] for k in ('status', 'cxi_sha256', 'payload_file_bytes', 'heap_bytes_reserved')}))


if __name__ == '__main__':
    main()
