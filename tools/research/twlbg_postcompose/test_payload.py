#!/usr/bin/env python3
"""Validate the generated ARM11 candidate on original firmware instructions.

CPU execution only. Cache calls, physical-address translation and LCD registers
are fixtures, never a hardware certification. Original allocator and final
presentation wrappers execute, with full pixel comparison against the host oracle.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess

from unicorn.arm_const import UC_ARM_REG_PC, UC_ARM_REG_CPSR
from exercise_console import Machine, STATE
from extract import extract
from verify import oracle


class PayloadMachine(Machine):
    def __init__(self, code):
        super().__init__(code)
        self.u.mem_map(0x1f000000, 0x600000)
        self.cache_results = {}

    def on_svc(self, u, interrupt, user):
        pc = u.reg_read(UC_ARM_REG_PC)
        if u.reg_read(UC_ARM_REG_CPSR) & 0x20:
            instruction = struct.unpack('<H', u.mem_read(pc - 2, 2))[0]
            assert instruction & 0xff00 == 0xdf00
            svc = instruction & 0xff
        else:
            svc = self.word(pc - 4) & 0xffffff
        if svc in (0x52, 0x53, 0x54, 0x7a):
            self.events.append({'event': 'cache', 'svc': hex(svc),
                                'r0': self.reg(0), 'r1': self.reg(1), 'r2': self.reg(2)})
            self.reg(0, self.cache_results.get(svc, 0))
        else:
            super().on_svc(u, interrupt, user)


def validate(directory, frames, output):
    manifest = json.loads((directory / 'manifest.json').read_text())
    code, _ = extract((directory / 'TwlBg.cxi').read_bytes())
    assert hashlib.sha256(code).hexdigest() == manifest['patched_code_sha256']
    prefix = '/opt/devkitpro/devkitARM/bin/arm-none-eabi-'
    symbols = {}
    for line in subprocess.check_output([prefix + 'nm', '-n', str(directory / 'ra-twlbg.elf')], text=True).splitlines():
        parts = line.split()
        if len(parts) == 3:
            symbols[parts[2]] = int(parts[0], 16)
    m = PayloadMachine(code)
    checks = 0
    def check(condition, reason):
        nonlocal checks
        assert condition, reason
        checks += 1

    loader_source = int(manifest['native_payload_source'], 16)
    m.run(loader_source, 0x100000, 0x281cc)
    binary = (directory / 'ra-twlbg.bin').read_bytes()
    check(bytes(m.u.mem_read(0x12e160, len(binary))) == binary, 'Appended loader copies exact payload')
    check(bytes(m.u.mem_read(symbols['__bss_start'], symbols['__bss_end'] - symbols['__bss_start'])) ==
          bytes(symbols['__bss_end'] - symbols['__bss_start']), 'Own BSS cleared')
    check([e['svc'] for e in m.events] == ['0x7a', '0x7a'], 'Original and payload cache initialization')

    # Run the entire original native relocation initializer through its patched
    # call, not merely the loader in isolation. Only its hardware delay is a
    # stub; MMIO, cache effects and the CPU map remain explicit fixtures.
    m = PayloadMachine(code)
    m.u.mem_map(0x200000, 0x100000)
    m.u.mem_map(0x1ec41000, 0x1000)
    m.u.mem_write(0x100000, b'\xa5' * 0x40000)
    m.word(0x100000, 0x54000)
    m.stubs[0x3053d0] = lambda machine: machine.ret()
    m.run(0x300102, count=7000000)
    check(bytes(m.u.mem_read(0x100000, 0x281cc)) == code[0x1f040:0x4720c],
          'Full startup relocates exact patched runtime')
    check(bytes(m.u.mem_read(0x1281d0, 0x5f90)) == bytes(0x5f90), 'Original BSS cleared')
    check(bytes(m.u.mem_read(0x12e160, len(binary))) == binary, 'Full startup preserves initialized payload')
    check(bytes(m.u.mem_read(symbols['__bss_start'], symbols['__bss_end'] - symbols['__bss_start'])) ==
          bytes(symbols['__bss_end'] - symbols['__bss_start']), 'Full startup clears own BSS')
    check(m.word(0x4aa5ac) == 0x54000, 'Kernel-owned AXI size saved before relocation')
    check([e['svc'] for e in m.events] == ['0x7a', '0x7a'], 'Full startup cache operations preserved')
    check(bytes(m.u.mem_read(0x200000, 0x100000)) == bytes(0x100000), 'Original clear region preserved')
    m.word(0x127358, 0x54000)
    check(m.run(0x101098) == int(manifest['new_heap_start'], 16), 'Original heap base moved')
    check(m.run(0x1010ec) == 0x154000 - int(manifest['new_heap_start'], 16), 'Original available heap reduced')
    m.run(0x102970)

    # Real final presentation conversion helper is replaced by the established
    # VRAM VA/PA relation; actual publication writes execute unmodified.
    def translate(machine):
        p = machine.reg(0)
        assert 0x1f000000 <= p < 0x1f600000
        machine.ret(p - 0x7000000)
    m.stubs[0x10f1b8] = translate
    m.word(0x120ef4, 0xffff8001)
    source, object_address = 0x1f300000, 0x131000
    m.word(0x12cb68, object_address)
    for offset, value in ((4, source), (8, 0x8051), (12, 240), (16, 320)):
        m.word(object_address + offset, value)
    assets = frames.read_bytes()
    assert assets[:8] == b'RAPRF1\0\0'
    pixels = assets[32 + 400 * 240 * 3:32 + (400 + 320) * 240 * 3]
    assert len(pixels) == 320 * 240 * 3
    m.u.mem_write(source, pixels)
    diagnostics = symbols['ra_diagnostics']
    traces = []
    for iteration, frame in enumerate((59, 60, 61, 238, 239, 240, 599, 600, 601, 779, 780)):
        m.word(diagnostics + 12, frame)
        m.events.clear()
        index = iteration % 2
        before = [m.word(0x1ef00568), m.word(0x1ef0056c)]
        m.run(symbols['ra_present'], 1, index, source, 0, 720, 0x301, index, count=2000000)
        active = 60 <= frame < 240 or 600 <= frame < 780
        published = m.word(0x1ef00568 + index * 4) + 0x7000000
        check(published != source if active else published == source, 'Popup schedule and clean expiration')
        check(bytes(m.u.mem_read(source, len(pixels))) == pixels, 'Original GPU output remains immutable')
        if active:
            check(all(not (published - 0x7000000 <= p < published - 0x7000000 + len(pixels)) for p in before),
                  'Written output was not referenced by either LCD slot')
            strip = struct.unpack('<512I', m.u.mem_read(symbols['raTextStrip'], 2048))
            expected = (bytes([255, 0, 255]) * (len(pixels) // 3) if manifest.get('temporary_visual_output') else
                        oracle(pixels, strip, 320, 240, 1, 208, True))
            check(bytes(m.u.mem_read(published, len(pixels))) == expected, 'Every output pixel matches oracle')
            check([e['svc'] for e in m.events if e['event'] == 'cache'] == ['0x52', '0x53'],
                  'Invalidate source, then store private output before publication')
        traces.append({'frame': frame, 'active': active, 'lcd_before': [hex(p) for p in before],
                       'published_va': hex(published), 'events': m.events[:]})

    # Unsupported surfaces and an in-flight GPU queue preserve the original path.
    before_shown = m.word(diagnostics + 20)
    negatives = [(source, 720, 0x302, 0), (source, 768, 0x301, 0),
                 (source + 1, 720, 0x301, 0), (source, 720, 0x301, 1)]
    for pointer, stride, fmt, busy in negatives:
        m.word(diagnostics + 12, 60)
        m.u.mem_write(0x12ca51, bytes([busy]))
        m.events.clear()
        # Translation fixture accepts byte addresses; the original path is
        # still exercised for rejected surface alignment/format.
        m.run(symbols['ra_present'], 1, 0, pointer, 0, stride, fmt, 0, count=2000000)
        check(m.word(diagnostics + 20) == before_shown, 'Negative case does not draw')
        check(not m.events, 'Negative case performs no cache access')
    m.u.mem_write(0x12ca51, b'\0')
    check(m.word(diagnostics + 68) == 3, 'Exactly three owned framebuffer allocations')
    # GPU-owned sources can occupy mapped VRAM beyond the private allocator.
    reserved_source = 0x1f500000
    m.u.mem_write(reserved_source, pixels)
    m.word(object_address + 4, reserved_source)
    m.word(diagnostics + 12, 60)
    m.run(symbols['ra_present'], 1, 0, reserved_source, 0, 720, 0x301, 0, count=2000000)
    check(m.word(diagnostics + 20) == before_shown + 1, 'Readable reserved VRAM source accepted')
    check(bytes(m.u.mem_read(reserved_source, len(pixels))) == pixels, 'Reserved VRAM source unchanged')
    m.word(object_address + 4, source)
    before_shown += 1
    for svc, expected_error in ((0x52, 5), (0x53, 7)):
        m.word(diagnostics + 12, 60)
        m.cache_results[svc] = 0xffffffff
        m.run(symbols['ra_present'], 1, 0, source, 0, 720, 0x301, 0, count=2000000)
        check(m.word(diagnostics + 20) == before_shown, 'Failed cache operation does not publish popup')
        check(m.word(diagnostics + 28) == expected_error, 'Cache failure diagnosed')
        check(m.word(0x1ef00568) + 0x7000000 == source, 'Cache failure publishes original output')
        m.cache_results.clear()
    m.word(diagnostics + 12, 60)
    m.word(0x1279f8, 99)
    m.events.clear()
    m.run(symbols['ra_present'], 1, 0, source, 0, 720, 0x301, 0)
    check(not m.events and m.word(diagnostics + 28) == 2, 'Busy texture allocation tag fails closed')
    m.word(0x1279f8, 0)
    m.word(diagnostics + 12, 1199)
    m.run(symbols['ra_present'], 1, 0, source, 0, 720, 0x301, 0)
    check(m.word(diagnostics + 12) == 0, 'Synthetic schedule repeats across TWiLight/game lifetime')
    # Exercise the actual patched caller: original GL-format/stride/address
    # calculation and buffer-index toggle, through our hook and LCD stores.
    m.word(0x12cb80, 320)
    for index in (0, 1):
        m.word(0x12cb8c, index)
        m.word(diagnostics + 12, 60)
        m.run(0x105f78, 0x401, count=2000000)
        published = m.word(0x1ef00568 + index * 4) + 0x7000000
        check(published != source, 'Patched original caller presents private output')
        check(m.word(diagnostics + 44) == source, 'Original caller computes validated source')
        check(m.word(diagnostics + 52) == 0x301 and m.word(diagnostics + 56) == 720,
              'Original caller computes RGB8 and physical stride')
        check(m.word(0x12cb8c) == 1 - index, 'Original caller retains index toggle')
    if manifest.get('temporary_color_diagnostic'):
        m.u.mem_map(0x1ed02000, 0x1000)
        blank = 0x1ed02a04
        def signal(frame):
            m.word(symbols['diagnostic_frames'], frame)
            m.events.clear()
            result = m.run(symbols['ra_signal_frame'], 0x123)
            check(result == 0 and m.events == [{'event': 'signal_event', 'handle': 0x123}],
                  'Diagnostic preserves original event signal and result')
        m.word(blank, 0x4321)
        signal(60)
        check(m.word(blank) == 0x01ff0000, 'Blue callback marker')
        signal(120)
        check(m.word(blank) == 0x4321, 'Marker restores exact original blank value')
        for source_value, shown, error, color in (
                (0, 0, 0, 0x01ffffff), (source, 1, 0, 0x0100ff00),
                (source, 0, 1, 0x010080ff), (source, 0, 8, 0x01ffff00),
                (source, 0, 5, 0x01ff00ff), (source, 0, 3, 0x010000ff),
                (source, 0, 0, 0x0100ffff)):
            m.word(diagnostics + 44, source_value)
            m.word(diagnostics + 20, shown)
            m.word(diagnostics + 28, error)
            signal(180)
            check(m.word(blank) == color, 'Diagnostic maps observed state to documented color')
            signal(300)
            check(m.word(blank) == 0x4321, 'Status expires and restores blank value')
        m.word(diagnostics + 44, source)
        m.word(diagnostics + 20, 0)
        m.word(diagnostics + 28, 1)
        m.word(diagnostics + 52, 0x302)
        for reason, color in ((1, 0x010000ff), (2, 0x010000ff), (3, 0x01ffff00),
                              (4, 0x0100ffff), (5, 0x01ff00ff), (6, 0x01ffffff)):
            m.word(symbols['surface_reason'], reason)
            signal(180)
            check(m.word(blank) == color, 'Distinct surface rejection color')
            signal(300)
        m.word(symbols['surface_reason'], 0)
        m.word(symbols['surface_reason'], 1)
        signal(180)
        m.word(symbols['surface_reason'], 2)
        signal(181)
        check(m.word(blank) == 0x010000ff, 'Diagnostic color stays latched during status window')
        signal(300)
        m.word(symbols['surface_reason'], 0)
        m.word(diagnostics + 20, 1)
        m.word(diagnostics + 28, 0)
        m.word(symbols['diagnostic_calls'], m.word(diagnostics + 8))
        m.word(symbols['diagnostic_idle_frames'], 120)
        signal(180)
        check(m.word(blank) == 0x01ffffff, 'Stale presentation detected')
        signal(300)
        m.word(blank, 0x01010203)
        signal(60)
        check(m.word(blank) == 0x01010203, 'Existing firmware blanking remains untouched')
        m.word(blank, 0)
        signal(60)
        m.word(blank, 0x010a0b0c)
        signal(61)
        check(m.word(blank) == 0x010a0b0c, 'Concurrent firmware blanking supersedes diagnostic')
        signal(300)
        check(m.word(blank) == 0x010a0b0c, 'Expiration does not restore over a newer firmware value')
        signal(1199)
        check(m.word(symbols['diagnostic_frames']) == 0, 'Diagnostic repeats across game launches')
    report = {'checks': checks, 'passed': True, 'hardware_tested': False,
              'cxi_sha256': manifest['cxi_sha256'], 'scope': __doc__, 'traces': traces,
              'source_frame_sha256': hashlib.sha256(pixels).hexdigest(),
              'diagnostics_words': list(struct.unpack('<19I', m.u.mem_read(diagnostics, 76))),
              'tool_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    with output.open('x') as file:
        json.dump(report, file, indent=2)
        file.write('\n')
    print(json.dumps({'checks': checks, 'passed': True, 'hardware_tested': False}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('build', type=Path)
    parser.add_argument('native_test_frames', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    validate(args.build, args.native_test_frames, args.output)


if __name__ == '__main__':
    main()
