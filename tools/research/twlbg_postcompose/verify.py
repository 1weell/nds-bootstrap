#!/usr/bin/env python3
"""Verify pure host composition; never runs/patches firmware or changes DS state.

Optional --frames accepts ONLY baseline trace PPM snapshots (256x384 RGB).
This is a pixel/ownership model, not TwlBg, emulated ARM11, or console timing.
"""
import argparse
import ctypes as C
import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess
import tempfile

from probe import inventory, PATTERNS

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
checks = 0


def check(condition):
    global checks
    checks += 1
    if not condition:
        raise AssertionError(f'Check {checks} failed')


def offset(x, y, width, height, layout):
    return ((y * width + x) if layout == 0 else
            (x * height + height - 1 - y)) * 3


def oracle(source, strip, width, height, layout, top, active):
    result = bytearray(source)
    if active:
        for y in range(16):
            for x in range(256):
                index = ((y // 8) * 32 + x // 8) * 8 + y % 8
                colour = (strip[index] >> (4 * (x % 8))) & 15
                p = offset((width - 256) // 2 + x, top + y,
                           width, height, layout)
                result[p:p+3] = bytes([255 if colour == 1 else
                                      0 if colour == 2 else 24]) * 3
    return bytes(result)


def compose(lib, source, strip, width, height, layout, active, top=8):
    original = C.create_string_buffer(source)
    guarded = C.create_string_buffer(b'G' * (len(source) + 32), len(source) + 32)
    output = C.cast(C.byref(guarded, 16), C.c_void_p)
    check(lib.ra_postcompose(original, len(source), output, len(source),
                            width, height, layout, strip, top, active) == 0)
    result = guarded.raw[16:-16]
    check(original.raw[:-1] == source)
    check(guarded.raw[:16] == b'G' * 16 and guarded.raw[-16:] == b'G' * 16)
    check(result == oracle(source, strip, width, height, layout, top, active))
    return result


def test_probe():
    for name, pattern in PATTERNS.items():
        check(inventory(pattern)['signatures'][name]['file_offsets'] == ['0x0'])
        check(inventory(b'\x11\x11' + pattern)['signatures'][name]['file_offsets'] == ['0x2'])
        check(inventory(b'\x11' + pattern)['signatures'][name]['count'] == 0)
        padded = pattern + bytes(len(pattern) % 2)
        check(inventory(padded * 2)['signatures'][name]['status'] == 'ambiguous')
        check(inventory(pattern)['deployable'] is False)
    for container in (b'', b'FIRM' + bytes(512), bytes(256) + b'NCCH'):
        try:
            inventory(container)
        except ValueError:
            check(True)
        else:
            check(False)


def counter_last_counterexample():
    # Producer1 publishes seq=1; reader sees it. Producer2 begins replacing
    # payload before seq=2. Even seq/payload/seq can accept a mixed message.
    shared = {'seq': 1, 'id': 101, 'title': 'FIRST'}
    first_seq = shared['seq']
    shared['id'] = 202
    reader_id, reader_title = shared['id'], shared['title']
    last_seq = shared['seq']
    check(first_seq == last_seq == 1)
    check((reader_id, reader_title) not in ((101, 'FIRST'), (202, 'SECOND')))
    return {'stable_sequence': first_seq, 'mixed_id': reader_id,
            'mixed_title': reader_title,
            'scope': 'Interleaving model of counter-last; not a recorded console failure'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--frames', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    # A fresh directory avoids replacing research evidence.
    args.output.mkdir(parents=True, exist_ok=False)
    with tempfile.TemporaryDirectory(prefix='ra-postcompose-') as temporary:
        binary = Path(temporary) / 'postcompose.so'
        command = shlex.split(os.environ.get('CC', 'cc')) + [
            '-std=c99', '-O2', '-Wall', '-Wextra', '-Werror', '-shared', '-fPIC',
            '-I' + str(ROOT / 'tools/research/tetris_gfx_order/research_include'),
            '-I' + str(ROOT / 'retail/common/include'),
            '-I' + str(ROOT / 'retail/cardenginei/arm9_ra/include'),
            str(HERE / 'postcompose.c'),
            str(ROOT / 'retail/cardenginei/arm9_ra/source/ra_text.c'),
            '-o', str(binary)]
        subprocess.run(command, check=True)
        lib = C.CDLL(str(binary))
        lib.ra_postcompose.argtypes = [C.c_void_p, C.c_size_t, C.c_void_p, C.c_size_t,
                                      C.c_uint, C.c_uint, C.c_int, C.c_void_p,
                                      C.c_uint, C.c_int]
        lib.ra_postcompose.restype = C.c_int
        lib.ra_text_render.argtypes = [C.c_char_p, C.c_char_p]
        lib.ra_text_render.restype = C.POINTER(C.c_uint32)
        strip = (C.c_uint32 * 512)()
        # Reuse production rasterizer. Copy its static strip before re-render.
        C.memmove(strip, lib.ra_text_render(b'POPUP TEST',
                  b'Mario Kart DS - host model'), C.sizeof(strip))
        dimensions = ((256, 192), (320, 240), (384, 240), (400, 240))
        for width, height in dimensions:
            source = bytes((i * 71 + i // 19) & 255 for i in range(width * height * 3))
            for layout in (0, 1):
                for active in (0, 1):
                    compose(lib, source, strip, width, height, layout, active)
                compose(lib, source, strip, width, height, layout, 1, height - 16)
        # Validate coordinates independently of glyph/text: first pixel ink,
        # last pixel shadow, arbitrary nibble 15 receives the backdrop.
        corners = (C.c_uint32 * 512)()
        corners[0] = 1 | (15 << 4)
        corners[511] = 2 << 28
        for layout in (0, 1):
            source = bytes([77] * (320 * 240 * 3))
            result = compose(lib, source, corners, 320, 240, layout, 1)
            p = offset(32, 8, 320, 240, layout)
            q = offset(287, 23, 320, 240, layout)
            check(result[p:p+3] == b'\xff' * 3)
            check(result[q:q+3] == b'\x00' * 3)
        source = C.create_string_buffer(bytes(256 * 192 * 3))
        output = C.create_string_buffer(b'Z' * (256 * 192 * 3))
        rejected = [
            (source, 0, output, len(output)-1, 256, 192, 0, strip, 8, 1),
            (source, len(source)-1, output, 0, 256, 192, 0, strip, 8, 1),
            (source, len(source)-1, output, len(output)-1, 255, 192, 0, strip, 8, 1),
            (source, len(source)-1, output, len(output)-1, 256, 192, 3, strip, 8, 1),
            (source, len(source)-1, output, len(output)-1, 256, 192, 0, strip, 177, 1),
            (source, len(source)-1, output, len(output)-1, 256, 192, 0, None, 8, 1),
            (source, len(source)-1, source, len(source)-1, 256, 192, 0, strip, 8, 1),
            (source, len(source)-1, C.byref(source, 1), len(source)-1,
             256, 192, 0, strip, 8, 1),
            (source, len(source)-1, output, len(output)-1, 256, 192, 0, output, 8, 1),
        ]
        for call in rejected:
            before = output.raw, source.raw
            check(lib.ra_postcompose(*call) == -1)
            check((output.raw, source.raw) == before)
        snapshots = []
        if args.frames:
            files = sorted(args.frames.glob('mario-save-trace-v2-frame-*.ppm'))
            if not files:
                parser.error('No baseline v2 PPM snapshots found')
            for file in files:
                original_file = file.read_bytes()
                header, data = original_file[:15], original_file[15:]
                check(header == b'P6\n256 384\n255\n')
                check(len(data) == 256 * 384 * 3)
                top, bottom = data[:256*192*3], data[256*192*3:]
                active = compose(lib, bottom, strip, 256, 192, 0, 1)
                check(active != bottom)
                # Expiry consumes the next fresh SOURCE, never the decorated output.
                inactive = compose(lib, bottom, strip, 256, 192, 0, 0)
                check(inactive == bottom)
                check(file.read_bytes() == original_file)
                if 'frame-960.' in file.name:
                    (args.output / 'mario-host-model.ppm').write_bytes(header + top + active)
                snapshots.append({'name': file.name,
                                  'sha256': hashlib.sha256(original_file).hexdigest(),
                                  'changed_outside_band': 0,
                                  'changed_after_expiry': 0})
        test_probe()
        counterexample = counter_last_counterexample()
    report = {'scope': 'Host pixel/ownership model only; no TwlBg/ARM11/3DS execution',
              'checks': checks, 'dimensions': dimensions, 'layouts': ['rows RGB', 'CTR rotated BGR'],
              'baseline_snapshots': snapshots, 'counter_last_counterexample': counterexample,
              'hardware_ready': False, 'compiler': command[:8]}
    (args.output / 'summary.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'checks': checks, 'baseline_snapshots': len(snapshots),
                      'hardware_ready': False}))


if __name__ == '__main__':
    main()
