#!/usr/bin/env python3
"""Read-only SVC availability audit of the exact console's TWL_FIRM kernel.

No binary output, patch, memory allocation or console operation. A table entry
and an ExHeader permission are static prerequisites, not a measured live map.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct

from extract import extract, get_ncch

FIRM_SHA256 = '403580f164a346066d8d4d0e33baf50362821fe54164272a34d7593e7c766197'
KERNEL_VA = 0xfff00000
VECTOR_VA = 0xffff0000


def inspect_kernel(firm):
    if hashlib.sha256(firm).hexdigest() != FIRM_SHA256:
        raise ValueError('Unreviewed TWL_FIRM; kernel map refused')
    _, extraction = extract(firm)
    sections = extraction['firm_sections']
    kernel_section, vector_section = sections[1:3]
    kernel = firm[kernel_section['offset']:kernel_section['offset'] + kernel_section['size']]
    vectors = firm[vector_section['offset']:vector_section['offset'] + vector_section['size']]

    def word(address):
        return struct.unpack_from('<I', kernel, address - KERNEL_VA)[0]

    # The vector's actual branch supplies the code VA; the SVC thunk supplies
    # the dispatcher, whose ADR supplies the table. No signature-only guessing.
    branch = struct.unpack_from('<I', vectors, 8)[0]
    if branch & 0xff000000 != 0xea000000:
        raise ValueError('SVC vector branch differs')
    relative = (branch & 0xffffff) << 2
    if relative & 0x2000000:
        relative -= 0x4000000
    thunk = (VECTOR_VA + 8 + 8 + relative) & 0xffffffff
    if (thunk != 0xfff0e5c0 or word(thunk) != 0xf57ff01f or
            word(thunk + 4) != 0xe51ff004):
        raise ValueError('SVC vector thunk differs')
    dispatcher = word(thunk + 8)
    if dispatcher != 0xfff0e784:
        raise ValueError('SVC dispatcher differs')
    adr = word(dispatcher + 0x1c)
    if adr != 0xe28f80f8 or word(dispatcher + 0x60) != 0xe7988109:
        raise ValueError('SVC table lookup differs')
    table = dispatcher + 0x1c + 8 + 0xf8
    ncch, _ = get_ncch(firm)
    ext = ncch[0x200:0x600]
    descriptors = struct.unpack_from('<28I', ext, 0x370)
    permitted = set()
    mappings = []
    for descriptor in descriptors:
        kind = descriptor >> 20
        if descriptor == 0xffffffff:
            continue
        if kind & 0xf80 == 0xf00:
            base = ((descriptor >> 24) & 7) * 24
            permitted.update(base + bit for bit in range(24) if descriptor & (1 << bit))
        if kind & 0xffe == 0xff8 or kind & 0xfff == 0xffe:
            mappings.append(hex(descriptor))
    names = {0x01: 'ControlMemory', 0x02: 'QueryMemory', 0x08: 'CreateThread',
             0x17: 'CreateEvent', 0x23: 'CloseHandle', 0x24: 'WaitSynchronization1',
             0x28: 'GetSystemTick',
             0x50: 'BindInterrupt', 0x51: 'UnbindInterrupt',
             0x52: 'InvalidateProcessDataCache', 0x53: 'StoreProcessDataCache',
             0x54: 'FlushProcessDataCache', 0x55: 'StartInterProcessDma',
             0x56: 'StopDma', 0x57: 'GetDmaState',
             0x69: 'QueryDebugProcessMemory', 0x6a: 'ReadProcessMemory',
             0x70: 'ControlProcessMemory', 0x71: 'MapProcessMemory',
             0x72: 'UnmapProcessMemory', 0x7a: 'LegacyStartupCacheOperation',
             0x7c: 'KernelSetState'}
    calls = {hex(number): {'name': name, 'handler': hex(word(table + 4 * number)),
                          'present': bool(word(table + 4 * number)),
                          'permitted_by_twlbg_exheader': number in permitted}
             for number, name in names.items()}
    if any(calls[hex(number)]['present'] for number in (1, 2)):
        raise ValueError('Reviewed unavailable memory services changed')
    fingerprints = {}
    for name, begin, end in (
            ('svc_dispatch', dispatcher, table),
            ('svc_table', table, table + 0x200),
            ('dma_start_wrapper', 0xfff0ed8c, 0xfff0edb4),
            ('dma_start', 0xfff03514, 0xfff03644)):
        fingerprints[name] = {'address': hex(begin), 'size': end - begin,
                              'sha256': hashlib.sha256(kernel[begin - KERNEL_VA:end - KERNEL_VA]).hexdigest()}
    return {'firm_sha256': FIRM_SHA256, 'deployable': False,
            'scope': 'Exact-image static kernel audit; no live page-table or runtime observation',
            'kernel_section_sha256': kernel_section['sha256'],
            'vector_section_sha256': vector_section['sha256'],
            'kernel_virtual_base': hex(KERNEL_VA), 'svc_vector_virtual_address': hex(VECTOR_VA + 8),
            'svc_vector_target': hex(thunk), 'svc_dispatcher': hex(dispatcher),
            'svc_table': hex(table), 'services': calls,
            'service_name_reference': 'https://github.com/devkitPro/libctru/blob/master/libctru/source/svc.s',
            'historical_erratum': 'First audit mislabeled SVC 0x50..0x52 and 0x69..0x6a. '
                                  'Numeric handlers/masks were unaffected; names corrected, '
                                  '0x53/0x54/0x70..0x72 added. 0x7a is legacy-specific.',
            'twlbg_explicit_mapping_descriptors': mappings,
            'function_fingerprints': fingerprints,
            'conclusion': 'ControlMemory and QueryMemory have null handlers and no TwlBg ExHeader permission. '
                          'The native-homebrew linear allocation and permission-query path cannot be reused as-is.',
            'unresolved': ['Kernel-created mappings and their CPU permissions',
                           'Ownership/free space in the existing firmware allocators',
                           'Private output allocation without unavailable SVCs',
                           'TWL kernel DMA stride semantics and hardware observation']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('firm', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    try:
        report = inspect_kernel(args.firm.read_bytes())
    except ValueError as error:
        parser.error(str(error))
    report['tool_sha256'] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    with args.output.open('x') as file:
        json.dump(report, file, indent=2)
        file.write('\n')
    print(json.dumps({'svc_table': report['svc_table'], 'ControlMemory': False,
                      'QueryMemory': False, 'deployable': False}))


if __name__ == '__main__':
    main()
