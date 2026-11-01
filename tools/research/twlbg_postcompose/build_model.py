#!/usr/bin/env python3
"""Link a NEW host-only runner against an already-built pinned research core.

Does not reconfigure/rebuild melonDS or overwrite the previous research binary.
Follow the Mario Kart research README to create that instrumented core first.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
PIN = '1e654443e4c0a54b40709c0208aa0eeba41e6142'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('research', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    research, output = args.research.resolve(), args.output.resolve()
    source, build = research / 'melonds', research / 'build'
    head = subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD'],
                                   text=True).strip()
    if head != PIN:
        parser.error('melonDS HEAD differs from the pinned research commit')
    cache = (build / 'CMakeCache.txt').read_text()
    for option in ('ENABLE_JIT', 'ENABLE_OGLRENDERER', 'ENABLE_GDBSTUB', 'BUILD_QT_SDL'):
        if option + ':BOOL=OFF' not in cache:
            parser.error('Expected ' + option + '=OFF')
    output.mkdir(parents=True, exist_ok=False)
    commands = []

    def run(command):
        commands.append(command)
        subprocess.run(command, check=True)

    includes = ['-I' + str(ROOT / 'tools/research/tetris_gfx_order/research_include'),
                '-I' + str(ROOT / 'retail/common/include'),
                '-I' + str(ROOT / 'retail/cardenginei/arm9_ra/include')]
    for name, file in [('postcompose', HERE / 'postcompose.c'),
                       ('ra_text', ROOT / 'retail/cardenginei/arm9_ra/source/ra_text.c')]:
        run(['cc', '-std=c99', '-O2', '-Wall', '-Wextra', '-Werror', *includes,
             '-c', str(file), '-o', str(output / (name + '.o'))])
    core, teakra = build / 'src/libcore.a', build / 'src/teakra/src/libteakra.a'
    run(['c++', '-std=gnu++17', '-O3', '-DNDEBUG', '-fwrapv', '-DARCHITECTURE_x86_64=1',
         '-I' + str(source / 'src'), '-I' + str(build / 'src'), '-I' + str(HERE),
         str(HERE / 'melonds_model.cpp'),
         str(ROOT / 'tools/research/tetris_gfx_order/research_platform.cpp'),
         str(output / 'postcompose.o'), str(output / 'ra_text.o'),
         str(core), str(teakra), '-lpthread', '-lrt', '-o', str(output / 'model')])
    inputs = [core, teakra, HERE / 'postcompose.c', HERE / 'postcompose.h',
              HERE / 'melonds_model.cpp', ROOT / 'retail/cardenginei/arm9_ra/source/ra_text.c']
    report = {'melonDS_head': head, 'scope': 'Host model; no ARM11 or TwlBg execution',
              'inputs': {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs},
              'commands': commands,
              'binary_sha256': hashlib.sha256((output / 'model').read_bytes()).hexdigest()}
    (output / 'build.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'binary': str(output / 'model'), 'sha256': report['binary_sha256']}))


if __name__ == '__main__':
    main()
