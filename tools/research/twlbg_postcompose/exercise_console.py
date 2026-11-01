#!/usr/bin/env python3
"""Execute original, hash-gated TwlBg routines with synthetic peripherals.

This is instruction-level contract research, NOT a 3DS emulator. Memory maps,
SVC results, DMA state and GPU calls are fixtures. No firmware is emitted and
no cache, permission, scheduling or hardware timing claim follows from a pass.
Requires unicorn==2.1.4; firmware stays outside the repository.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct

from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM, UC_HOOK_CODE, UC_HOOK_INTR
from unicorn.arm_const import (UC_CPU_ARM_11MPCORE, UC_ARM_REG_R0,
                               UC_ARM_REG_SP, UC_ARM_REG_LR, UC_ARM_REG_PC)
from inspect_console import inspect

BASE = 0x100000
IMAGE = 0x300000
STATE = 0x800100
LISTS = 0x801000
STACK = 0xa08000
RETURN = 0xa0f000
LGY = (0x1ec11000, 0x1ec10000)


class Machine:
    def __init__(self, code):
        self.u = Uc(UC_ARCH_ARM, UC_MODE_ARM)
        self.u.ctl_set_cpu_model(UC_CPU_ARM_11MPCORE)
        for address, size in ((BASE, 0x40000), (IMAGE, 0x200000),
                              (0x800000, 0x20000), (0xa00000, 0x10000),
                              (0x1ec10000, 0x2000), (0x1ef00000, 0x1000)):
            self.u.mem_map(address, size)
        self.u.mem_write(IMAGE, code)
        self.u.mem_write(BASE, code[0x1f040:0x4720c])
        self.events = []
        self.stubs = {}
        self.states = [4]
        self.handle = 0x500
        self.wait_result = 0
        self.reached_return = False
        self.u.hook_add(UC_HOOK_CODE, self.on_code)
        self.u.hook_add(UC_HOOK_INTR, self.on_svc)

    def word(self, address, value=None):
        if value is None:
            return struct.unpack('<I', self.u.mem_read(address, 4))[0]
        self.u.mem_write(address, struct.pack('<I', value & 0xffffffff))

    def reg(self, number, value=None):
        if value is None:
            return self.u.reg_read(UC_ARM_REG_R0 + number)
        self.u.reg_write(UC_ARM_REG_R0 + number, value & 0xffffffff)

    def ret(self, value=0):
        self.reg(0, value)
        self.u.reg_write(UC_ARM_REG_PC, self.u.reg_read(UC_ARM_REG_LR))

    def on_code(self, u, address, size, _):
        if address == RETURN:
            self.reached_return = True
            u.emu_stop()
        elif address in (0x1136b4, 0x113864):
            raise AssertionError('Original firmware panic at ' + hex(address))
        elif address in self.stubs:
            self.stubs[address](self)

    def on_svc(self, u, interrupt, _):
        pc = u.reg_read(UC_ARM_REG_PC)
        instruction = self.word(pc - 4)
        assert instruction & 0xff000000 == 0xef000000, hex(pc)
        svc = instruction & 0xffffff
        if svc == 0x17:
            self.events.append({'event': 'create_event', 'reset_type': self.reg(0)})
            self.reg(0, 0)
            self.reg(1, self.handle)
            self.handle += 1
        elif svc == 0x18:
            self.events.append({'event': 'signal_event', 'handle': self.reg(0)})
            self.reg(0, 0)
        elif svc == 0x24:
            self.events.append({'event': 'wait', 'handle': self.reg(0),
                                'timeout': (self.reg(3) << 32) | self.reg(2)})
            self.reg(0, self.wait_result)
        elif svc in (0x56, 0x23):
            self.events.append({'event': 'stop' if svc == 0x56 else 'close',
                                'handle': self.reg(0)})
            self.reg(0, 0)
        elif svc == 0x55:
            config = self.reg(5)
            self.events.append({'event': 'start', 'source': self.reg(0),
                                'destination_process': self.reg(1),
                                'destination': self.reg(2),
                                'source_process': self.reg(3),
                                'size': self.reg(4),
                                'config_hex': bytes(u.mem_read(config, 24)).hex()})
            self.reg(0, 0)
            self.reg(1, self.handle)
            self.handle += 1
        elif svc == 0x57:
            state = self.states.pop(0) if len(self.states) > 1 else self.states[0]
            self.events.append({'event': 'state', 'handle': self.reg(1), 'state': state})
            self.reg(0, 0)
            self.reg(1, state)
        else:
            raise AssertionError('Unexpected SVC ' + hex(svc))

    def run(self, address, *args, count=100000):
        for number in range(13):
            self.reg(number, 0)
        preserved = {number: 0xcca00000 + number * 0x111 for number in range(4, 12)}
        for number, value in preserved.items():
            self.reg(number, value)
        self.u.reg_write(UC_ARM_REG_SP, STACK)
        self.u.reg_write(UC_ARM_REG_LR, RETURN | 1)
        for number, value in enumerate(args[:4]):
            self.reg(number, value)
        for number, value in enumerate(args[4:]):
            self.word(STACK + number * 4, value)
        self.reached_return = False
        self.u.emu_start(address | 1, RETURN + 2, count=count)
        assert self.reached_return, 'Instruction limit at ' + hex(self.u.reg_read(UC_ARM_REG_PC))
        assert self.u.reg_read(UC_ARM_REG_SP) == STACK, 'Stack not restored'
        assert all(self.reg(number) == value for number, value in preserved.items()), 'Callee-saved register changed'
        return self.reg(0)

    def ring(self, counts=(2, 2), indices=(0, 0), handles=(0x101, 0x102)):
        self.word(STATE + 0x10, len(counts))
        self.word(STATE + 0x58, 256 * 192 * 3)
        self.word(0x120ee8, 0xffff8001)  # synthetic current-process handle
        for screen, (count, index, handle) in enumerate(zip(counts, indices, handles)):
            screen_state = STATE + 0x30 + screen * 0x14
            self.word(screen_state, handle)
            self.word(screen_state + 4, LISTS + screen * 0x100 if count else 0)
            self.word(screen_state + 8, count)
            self.word(screen_state + 12, index)
            self.word(screen_state + 16, 0xdead0000 + screen)
            for slot in range(count):
                self.word(LISTS + screen * 0x100 + slot * 4,
                          0x900000 + screen * 0x100000 + slot * 0x20000)


def exercise(code, metadata):
    static = inspect(code, metadata)
    checks = 0
    traces = {}

    def check(condition, message):
        nonlocal checks
        if not condition:
            raise AssertionError(message)
        checks += 1

    # Unknown images must be rejected before any original instruction executes.
    changed = bytearray(code)
    changed[0x2498c] ^= 1
    try:
        inspect(bytes(changed), metadata)
    except ValueError:
        check(True, 'Mutated image rejected')
    else:
        check(False, 'Mutated image accepted')

    # Execute registration, including negative contracts and an empty screen.
    for count, pointer, entries, accepted in (
            (2, LISTS, [0x900000, 0x920000], True),
            (1, LISTS, [0x900000], True),
            (0, 0, [], True), (2, 0, [], False),
            (2, LISTS, [0x900000, 0], False),
            (0xffffffff, LISTS, [0x900000], False)):
        m = Machine(code)
        for slot, entry in enumerate(entries):
            m.word(LISTS + 4 * slot, entry)
        m.word(STATE + 0x3c, 99)
        m.word(STATE + 0x40, 0x12345678)
        result = m.run(0x301b30, STATE, 0, pointer, count)
        check(bool(result) == accepted, 'Registration acceptance')
        check(m.word(STATE + 0x40) == 0x12345678, 'Registration preserves previous pointer')
        if accepted:
            check(m.word(STATE + 0x3c) == 0, 'Registration resets index')
            check(m.word(STATE + 0x34) == pointer, 'Registration list pointer')

    # Run original index/division code with one to three entries, both screens.
    for count in (1, 2, 3):
        for index in range(count):
            m = Machine(code)
            m.ring((count, count), (index, index))
            for iteration in range(8):
                expected = (index + iteration) % count
                m.run(0x105918, STATE)
                for screen in range(2):
                    obj = STATE + 0x30 + 0x14 * screen
                    check(m.word(obj + 16) == m.word(LISTS + 0x100 * screen + 4 * expected),
                          'Completed pointer selected before advancement')
                    check(m.word(obj + 12) == (expected + 1) % count, 'Index modulo')

    # Waiting is separate from stop/close. Cancellation explicitly skips wait.
    for cancel in (0, 1):
        for handles in ((0x101, 0x102), (0, 0x102), (0, 0)):
            m = Machine(code)
            m.ring(handles=handles)
            m.run(0x105824, STATE, cancel)
            expected = []
            for handle in handles:
                if handle:
                    if not cancel:
                        expected.append({'event': 'wait', 'handle': handle, 'timeout': 0xffffffffffffffff})
                    expected.extend(({'event': 'stop', 'handle': handle},
                                     {'event': 'close', 'handle': handle}))
            check(m.events == expected, 'Wait/stop/close order')
            check(m.word(STATE + 0x30) == m.word(STATE + 0x44) == 0, 'Retired handles cleared')
            if all(handles):
                traces['cancel' if cancel else 'retire'] = expected

    # The real DMA wrapper and SVC ABI run here. Kernel/device effects are mocks.
    for enabled in (False, True):
        for next_state in (2, 3, 4):
            m = Machine(code)
            m.ring()
            m.run(0x105824, STATE, 0)
            m.run(0x105918, STATE)
            m.events.clear()
            for address in LGY:
                m.word(address, int(enabled))
            m.states = [0, 1, next_state, next_state]
            m.run(0x10594c, STATE)
            starts = [e for e in m.events if e['event'] == 'start']
            polls = [e for e in m.events if e['event'] == 'state']
            check(len(starts) == 2, 'One start per screen')
            check([e['destination'] for e in starts] == [0x920000, 0xa20000], 'Next slot is DMA destination')
            check([e['source'] for e in starts] == [0x1ee11000, 0x1ee10000], 'FIFO is source, not CPU-readable frame')
            check(all(e['size'] == 256 * 192 * 3 for e in starts), 'DMA size from state+0x58')
            check([int(e['config_hex'][8:10], 16) for e in starts] == [14, 13], 'Peripheral config')
            check(not polls if enabled else [e['state'] for e in polls] == [0, 1, next_state, next_state],
                  'Start returns at state >=2 or skips polling')
            traces[f'start_enabled_{int(enabled)}_state_{next_state}'] = m.events

    # Original bit2 path: retire, select previous, advance, start next.
    m = Machine(code)
    m.ring()
    m.word(STATE + 8, 20000)
    for address in LGY:
        m.word(address, 1)
    m.stubs[0x112760] = lambda x: (x.word(x.reg(0), 100000), x.word(x.reg(0) + 4, 0), x.ret())
    # state time starts at zero, so unrelated 64-bit time conversion is skipped.
    m.run(0x1040c8, STATE, 4)
    check([e['event'] for e in m.events] == ['wait', 'stop', 'close'] * 2 + ['start'] * 2,
          'Frame path uses completed slot and starts alternate slot')
    check(m.word(STATE + 0x40) == 0x900000 and m.word(STATE + 0x54) == 0xa00000,
          'Previous pointers survive new start')
    traces['frame_path'] = m.events

    # Continue through the real per-frame callback, which publishes each old
    # pointer as a texture slot and signals the rendering side. That event is
    # publication, not a demonstrated GPU retirement fence.
    publication = []
    for slot in (0, 1):
        m = Machine(code)
        m.ring(indices=(slot, slot))
        for address in LGY:
            m.word(address, 1)
        m.word(0x127318, 1)
        m.word(0x127190 + 12, STATE)
        m.word(0x127190 + 16, 0x700)
        for screen in (0, 1):
            for index in (0, 1):
                m.word(0x12be68 + (1 + screen * 2 + index) * 4,
                       m.word(LISTS + screen * 0x100 + index * 4))
        m.run(0x105824, STATE, 0)
        m.run(0x105918, STATE)
        m.run(0x10594c, STATE)
        m.run(0x101768)
        check(m.word(0x12a540 + 0xb4) == slot, 'Top completed texture index published')
        check(m.word(0x12a540 + 0xb8) == slot, 'Bottom completed texture index published')
        check(m.events[-1] == {'event': 'signal_event', 'handle': 0x700}, 'Render event follows publication')
        check(all(e['destination'] != m.word(STATE + 0x40 + screen * 0x14)
                  for screen, e in enumerate(event for event in m.events if event['event'] == 'start')),
              'Published old slot differs from new DMA target')
        publication.append({'completed_slot': slot, 'events': m.events})
        previous_selector = m.word(0x12a540 + 0xb4)
        check(m.run(0x11276c, 0x400, 0xabcdef00) == 0, 'Unknown pointer cannot publish a texture slot')
        check(m.word(0x12a540 + 0xb4) == previous_selector, 'Rejected publication keeps selector')

    # Derive pitch and transfer size from actual LGY format/dimension readers.
    formats = []
    for width, height in ((256, 192), (320, 240)):
        for format_number, bpp in ((0, 4), (1, 3), (2, 2), (3, 2)):
            m = Machine(code)
            m.word(LGY[0], 0x1000 | (format_number << 8))
            m.word(LGY[0] + 4, (width - 1) | ((height - 1) << 16))
            m.run(0x301502, STATE)
            check(m.word(STATE + 0x58) == width * height * bpp, 'Transfer size by format')
            check(struct.unpack('<H', m.u.mem_read(STATE + 0x20, 2))[0] == width * 8 * bpp,
                  'Eight-line block pitch')
            formats.append({'width': width, 'height': height, 'format': format_number,
                            'bytes_per_pixel': bpp, 'transfer_size': m.word(STATE + 0x58)})

    # Execute the real DS mode setup, including Morton and padded destination.
    modes = []
    for mode, width, height, pitch in ((0, 256, 200, 256), (1, 320, 240, 512),
                                       (2, 384, 288, 512)):
        m = Machine(code)
        # Interrupt binding and thread creation are mocked; all config writes
        # and format setters in the original constructor still execute.
        m.stubs[0x1105ac] = lambda x: x.ret()
        m.stubs[0x10fd76] = lambda x: x.ret()
        check(m.run(0x30161e, STATE, 2) == 1, 'Video constructor accepted')
        check(m.run(0x300c8a, STATE, mode) == 1, 'DS mode setup accepted')
        control = m.word(LGY[0])
        check((control & 0x1f00) == 0x1100, 'Morton RGB8, no rotation')
        check(m.word(LGY[0] + 4) == ((width - 1) | ((height - 1) << 16)), 'DS dimensions')
        check(m.word(STATE + 0x14) == pitch, 'Destination pixel pitch')
        check(m.word(STATE + 0x58) == width * height * 3, 'DS transfer size')
        cfg = bytes(m.u.mem_read(STATE + 0x18, 24))
        block_size = struct.unpack_from('<h', cfg, 8)[0]
        block_stride = struct.unpack_from('<h', cfg, 12)[0]
        check(block_size == width * 8 * 3 and block_stride == pitch * 8 * 3,
              'DMA block and pitch-derived configuration fields')
        modes.append({'mode_argument': mode, 'output_width': width, 'output_height': height,
                      'destination_pitch_pixels': pitch, 'transfer_size': m.word(STATE + 0x58),
                      'config_hex': cfg.hex(), 'morton': True, 'rotation': 0,
                      'src_config_transfer_size': block_size,
                      'src_config_transfer_stride': block_stride,
                      'candidate_span_if_stride_applies_to_destination':
                      (height // 8 - 1) * block_stride + block_size,
                      'stride_semantics_verified_in_twl_kernel': False})

    # Observe original texture binding with distinct screen/slot fixtures.
    bindings = []
    for screen in (0, 1):
        for slot in (0, 1):
            m = Machine(code)
            gpu = 0x12a540
            m.u.mem_write(gpu + 0x84, struct.pack('<H', 256))
            m.word(gpu + 0xb4 + 4 * screen, slot)
            for pane in (0, 1):
                for entry in (0, 1):
                    m.word(gpu + 0xdc + pane * 8 + entry * 4, 0xb00000 + pane * 0x100000 + entry * 0x20000)
            m.word(gpu + 0xd4 + 4 * screen, 0xd00000 + 0x100000 * screen)
            observed = []
            def bind(x):
                observed.append({'unit': x.reg(1), 'pointer': x.reg(2), 'r3': x.reg(3)})
                x.ret()
            m.stubs[0x110d38] = bind
            for address in (0x110d7c, 0x1129ac, 0x118538, 0x11857c,
                            0x110cf8, 0x11855c, 0x11837c, 0x1184b8):
                m.stubs[address] = lambda x: x.ret(1)
            m.run(0x103b24, gpu, 0x400 + screen)
            check(observed[0]['pointer'] == 0xb00000 + screen * 0x100000 + slot * 0x20000,
                  'Texture unit0 consumes selected DMA ring slot')
            check(observed[1]['pointer'] == 0xd00000 + screen * 0x100000,
                  'Texture unit1 is separate')
            bindings.append({'screen': screen, 'slot': slot, 'bindings': observed})

    # Original VRAM heap initialization/allocation, on explicitly synthetic
    # RW mappings. This proves allocator behavior, not live free space/access.
    allocations = []
    for allocation_type, lower, upper in ((0x10000, 0x1f300000, 0x1f4fd800),
                                          (0x20000, 0x1f000000, 0x1f300000),
                                          (0x30000, 0x1f300000, 0x1f4fd800)):
        m = Machine(code)
        m.u.mem_map(0x1f000000, 0x500000)
        m.run(0x102970)
        first = m.run(0x1055bc, allocation_type, 0x100, 0, 0x20000)
        denied = m.run(0x1055bc, allocation_type, 0x100, 0, 0x600000)
        second = m.run(0x1055bc, allocation_type, 0x100, 0, 0x20000)
        check(lower <= first and first + 0x20000 <= upper, 'Allocation within selected heap')
        check(denied == 0, 'Oversized allocation fails')
        check(first + 0x20000 <= second and second + 0x20000 <= upper,
              'Failure leaves heap usable and successful outputs disjoint')
        check(not m.events, 'Existing allocator needs no SVC')
        allocations.append({'type': hex(allocation_type), 'size': 0x20000,
                            'first': hex(first), 'oversize_return': denied, 'second': hex(second),
                            'mapping': 'Synthetic RW VRAM; not observed on console'})

    return {'scope': __doc__, 'code_sha256': static['code_sha256'],
            'checks': checks, 'passed': True, 'deployable': False,
            'cpu_model': 'Unicorn ARM11 MPCore; synthetic memory/peripherals',
            'unicorn_required_version': '2.1.4', 'traces': traces,
            'format_cases': formats, 'ds_mode_cases': modes, 'texture_binding_cases': bindings,
            'allocator_cases': allocations, 'publication_cases': publication,
            'unproven': ['Live buffer addresses and memory permissions',
                         'GPU completion versus reuse on the video thread',
                         'Actual LGY configuration in every selected mode',
                         'Physical mapping, cache maintenance and coherency',
                         'Private output allocation, publication and hardware cost']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('extraction_directory', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    code = (args.extraction_directory / 'twlbg-code.bin').read_bytes()
    metadata = json.loads((args.extraction_directory / 'extraction.json').read_text())
    report = exercise(code, metadata)
    report['tool_sha256'] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    with args.output.open('x') as file:
        json.dump(report, file, indent=2)
        file.write('\n')
    print(json.dumps({key: report[key] for key in ('checks', 'passed', 'deployable')}))


if __name__ == '__main__':
    main()
