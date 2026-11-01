#!/usr/bin/env python3
"""Reproduce the static video map for the ONE acquired console TwlBg revision.

Read-only, exact-image gated; no patch output or code-cave selection. Addresses
below identify disassembly evidence, not an executable installation recipe.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct

KNOWN_CODE_SHA256 = '5ae86470a4f00ca102c829928493a94bfae3119bd53c7e1679747ba69dbb958c'
BASE = 0x100000


def sha(data):
    return hashlib.sha256(data).hexdigest()


def thumb_call(data, address):
    offset = address - BASE
    h1, h2 = struct.unpack_from('<HH', data, offset)
    if h1 & 0xf800 != 0xf000 or h2 & 0xf800 not in (0xf800, 0xe800):
        raise ValueError('Expected Thumb BL/BLX at ' + hex(address))
    relative = ((h1 & 0x7ff) << 12) | ((h2 & 0x7ff) << 1)
    if relative & 0x400000:
        relative -= 0x800000
    target = address + 4 + relative
    return target & ~3 if h2 & 0xf800 == 0xe800 else target


def inspect(code, metadata):
    if sha(code) != KNOWN_CODE_SHA256 or metadata['code_sha256'] != sha(code):
        raise ValueError('Unreviewed TwlBg image; no address map generated')
    image_base = int(metadata['declared_code_segments']['text']['address'], 16)
    source_address, length, bss_address, bss_length = struct.unpack_from('<4I', code, 0x1a8)
    source = source_address - image_base
    if (image_base != 0x300000 or source != 0x1f040 or length != 0x281cc or
        bss_address != 0x1281d0 or bss_length != 0x5f90 or
        source + length != metadata['declared_code_segments']['text']['size']):
        raise ValueError('Relocation layout differs from reviewed initializer')
    # Boot initializer sets r4=1<<20 and copies the literal source/length there.
    if struct.unpack_from('<H', code, 0x104)[0] != 0x2401 or \
       struct.unpack_from('<H', code, 0x108)[0] != 0x0524:
        raise ValueError('Relocation destination construction differs')
    runtime = code[source:source+length]

    def half(address):
        return struct.unpack_from('<H', runtime, address-BASE)[0]

    def word(address):
        return struct.unpack_from('<I', runtime, address-BASE)[0]

    expected_calls = {
        0x10417a: 0x105824,  # retire/wait old DMA
        0x104180: 0x105918,  # select previous pointer and advance index
        0x104194: 0x10594c,  # start next DMA
        0x10583c: 0x1043d4,  # optional wait before retirement
        0x1043e2: 0x110920,  # wait wrapper
        0x110924: 0x110a88,  # svcWaitSynchronization1
        0x105984: 0x1103bc,  # DMA-start wrapper
        0x1103d0: 0x108ebc,
        0x108ede: 0x11b30c,  # svcStartInterProcessDma
        0x1059a8: 0x10661a,  # state getter in startup polling loop
        0x10662a: 0x119a04,  # svcGetDmaState
    }
    calls = {}
    for address, wanted in expected_calls.items():
        actual = thumb_call(runtime, address)
        if actual != wanted:
            raise ValueError('Call target differs at ' + hex(address))
        calls[hex(address)] = hex(actual)
    if word(0x110a88) != 0xef000024 or word(0x11b31c) != 0xef000055 or \
       word(0x119a08) != 0xef000057:
        raise ValueError('SVC wrapper differs')
    # cmp r0,#2; bcc back to the state getter. It is NOT cmp r0,#4.
    if half(0x1059ac) != 0x2802 or half(0x1059ae) != 0xd3fa:
        raise ValueError('DMA startup polling condition differs')
    table = struct.unpack_from('<6I', runtime, 0x121008-BASE)
    if table != (0x1ec11000, 0x1ec10000, 0x1ee11000, 0x1ee10000, 14, 13):
        raise ValueError('Legacy video/FIFO/peripheral table differs')
    functions = {'dma_start': (0x10594c, 0x1059c0),
                 'retire_dma': (0x105824, 0x105850),
                 'advance_buffer_index': (0x105918, 0x10594c),
                 'wait_old_dma': (0x1043d4, 0x1043f0),
                 'display_addresses_init': (0x105670, 0x1056b0)}
    fingerprints = {name: {'runtime_address': hex(start), 'size': end-start,
                           'sha256': sha(runtime[start-BASE:end-BASE])}
                    for name, (start, end) in functions.items()}
    return {
        'scope': 'Static analysis of acquired title 0004013820000102 v10962; no runtime observation',
        'code_sha256': sha(code), 'deployable': False,
        'relocation': {'image_base': hex(image_base), 'source_file_offset': hex(source),
                       'runtime_base': hex(BASE), 'length': hex(length),
                       'zeroed_bss_start': hex(bss_address), 'zeroed_bss_length': hex(bss_length),
                       'initializer_sha256': sha(code[0x102:0x17c])},
        'historical_signature_addresses': {'rtc': hex(BASE+0x1fd50-source),
                                            'pxi_log': hex(BASE+0x32900-source),
                                            'dma_start': hex(BASE+0x2498c-source)},
        'verified_thumb_calls': calls, 'function_fingerprints': fingerprints,
        'dma_start_return_condition': {
            'polling_gate': 'The all-disabled-LGY path polls until DMA state >= 2; enabled-LGY path skips this poll',
            'accepted_states_in_polling_path': [2, 3, 4],
            'libctru_state_names': {'2': 'DMASTATE_WFP_SRC', '3': 'DMASTATE_RUNNING', '4': 'DMASTATE_DONE'},
            'whole_frame_completion_guaranteed_by_return': False,
        },
        'buffer_structure_observed': {'per_screen_base': 'state+0x30', 'per_screen_stride': '0x14',
                                      'buffer_list_pointer': '+0x04', 'buffer_count': '+0x08',
                                      'current_index': '+0x0C', 'previous_selected_pointer': '+0x10',
                                      'live_buffer_addresses_known': False},
        'unresolved': ['Runtime DMA/display ordering on every mode and sleep transition',
                       'Final buffer format, pitch, rotation and physical/virtual mapping',
                       'Exclusive ARM11 output allocation and publication',
                       'Event transport, cache contract and real timing budget'],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('extraction_directory', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    code = (args.extraction_directory/'twlbg-code.bin').read_bytes()
    metadata = json.loads((args.extraction_directory/'extraction.json').read_text())
    try:
        report = inspect(code, metadata)
    except ValueError as error:
        parser.error(str(error))
    with args.output.open('x') as file:
        json.dump(report, file, indent=2)
        file.write('\n')
    print(json.dumps({'code_sha256': report['code_sha256'], 'verified_calls': len(report['verified_thumb_calls']),
                      'dma_start_return_is_frame_complete': False, 'deployable': False}))


if __name__ == '__main__':
    main()
