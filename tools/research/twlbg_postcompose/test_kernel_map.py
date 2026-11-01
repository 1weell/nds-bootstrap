#!/usr/bin/env python3
"""Execute the exact legacy kernel's page-table construction, without enabling MMU.

No hardware emulation: inspect descriptors actually written by original ARM/Thumb
instructions. This establishes the stock initial map, not later live state.
"""
import argparse
import hashlib
import json
from pathlib import Path

from unicorn.arm_const import UC_ARM_REG_SP, UC_ARM_REG_PC
from exercise_console import Machine, STACK
from extract import extract
from inspect_kernel import inspect_kernel


def test(firm, output):
    services = inspect_kernel(firm)
    code, metadata = extract(firm)
    section = metadata['firm_sections'][1]
    m = Machine(code)
    m.u.mem_map(0xfff00000, 0x20000)
    m.u.mem_map(0xffff0000, 0x10000)
    m.u.mem_map(0x1ffac000, 0x54000)
    m.u.mem_write(0xfff00000, firm[section['offset']:section['offset'] + section['size']])
    m.u.reg_write(UC_ARM_REG_SP, STACK)
    m.reg(0, 0)
    m.reg(1, 1)
    # Stop after original table construction and user-owned AXI size store,
    # before cache/MMU activation and unrelated scheduler initialization.
    m.u.emu_start(0xfff006d1, 0xfff007ce, count=1000000)
    assert m.u.reg_read(UC_ARM_REG_PC) == 0xfff007ce
    assert m.word(0x1ffac000) == 0x54000

    def mapping(va, executable=True):
        first = m.word(0xffff2000 + (va >> 20) * 4)
        if first & 3 == 2:
            descriptor = first
            pa = (first & 0xfff00000) | (va & 0xfffff)
            ap = ((first >> 10) & 3) | ((first >> 13) & 4)
            xn = bool(first & 0x10)
            kind = 'section'
        elif first & 3 == 1:
            # Original kernel's coarse tables reside in its high AXI alias.
            table = (first & 0xfffffc00) - 0x1ff79000 + 0xffff0000
            descriptor = m.word(table + ((va >> 12) & 255) * 4)
            assert descriptor & 2
            pa = (descriptor & 0xfffff000) | (va & 4095)
            ap = ((descriptor >> 4) & 3) | ((descriptor >> 7) & 4)
            xn = bool(descriptor & 1)
            kind = 'small_page'
        else:
            raise AssertionError('Unmapped address ' + hex(va))
        assert ap == 3 and (not executable or not xn), 'Expected user access at ' + hex(va)
        return {'va': hex(va), 'pa': hex(pa), 'kind': kind,
                'l1_descriptor': hex(first), 'descriptor': hex(descriptor),
                'ap': ap, 'execute_never': xn, 'user_read_write': True}

    probes = [mapping(v) for v in (0x100000, 0x12e160, 0x130000, 0x153fff,
                                   0x300000, 0x4bb6a0, 0x1f000000, 0x1f4fd7ff)]
    assert int(probes[1]['pa'], 16) == 0x1ffda160
    assert int(probes[6]['pa'], 16) == 0x18000000
    # The rest of this coarse range retains the earlier VRAM mapping, not
    # additional AXI ownership. Do not mistake accessibility for free heap.
    boundary = mapping(0x154000)
    assert int(boundary['pa'], 16) == 0x18554000
    # Execute the actual type-4 transition's unmapping operations as well.
    # AXI, VRAM and LCD MMIO must remain accessible after native FCRAM/code
    # aliases disappear. Cache/MMU activation stays outside this CPU fixture.
    m.u.reg_write(UC_ARM_REG_SP, STACK)
    m.u.emu_start(0xfff06c2f, 0xfff06c68, count=1000000)
    assert m.u.reg_read(UC_ARM_REG_PC) == 0xfff06c68
    runtime_probes = [mapping(v) for v in (0x12e160, 0x130000, 0x1f000000, 0x1f4fd7ff)]
    runtime_probes.append(mapping(0x1ed02a04, executable=False))
    assert int(runtime_probes[-1]['pa'], 16) == 0x10202a04
    rtc = mapping(0x1ec47100, executable=False)
    assert int(rtc['pa'],16)==0x10147100
    runtime_probes.append(rtc)
    assert m.word(0xffff2000 + 3 * 4) == 0x80000000
    assert m.word(0xffff2000 + 0x80 * 4) == 0x80000000
    report = {'passed': True, 'hardware_tested': False,
              'firm_sha256': services['firm_sha256'],
              'kernel_initial_user_axi_bytes': m.word(0x1ffac000),
              'execution_begin': '0xfff006d0', 'execution_stop': '0xfff007ce',
              'scope': __doc__, 'probes': probes,
              'first_page_after_owned_axi': boundary,
              'after_kernel_set_state_4': runtime_probes,
              'tool_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'corrected_services': services['services']}
    with output.open('x') as file:
        json.dump(report, file, indent=2)
        file.write('\n')
    print(json.dumps({'passed': True, 'owned_axi_bytes': report['kernel_initial_user_axi_bytes'],
                      'user_rwx_probes': len(probes), 'hardware_tested': False}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('firm', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    test(args.firm.read_bytes(), args.output)
