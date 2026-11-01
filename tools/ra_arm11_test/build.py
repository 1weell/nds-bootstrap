#!/usr/bin/env python3
"""Build native ARM11 visual/timing test from private baseline snapshots.

Produces standalone homebrew, NOT a TwlBg or nds-bootstrap replacement.
Captured images stay in the private output package, never in the repository.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
FRAMES = (360, 380, 480, 960)
TOP_BYTES, BOTTOM_BYTES = 400*240*3, 320*240*3


def fnv(data):
    value = 2166136261
    for byte in data:
        value = ((value ^ byte) * 16777619) & 0xffffffff
    return value


def convert_panel(rgb, width):
    """Nearest 5:4 scale, centered on physical 400/320x240, native rotated BGR."""
    if len(rgb) != 256*192*3 or width not in (320, 400):
        raise ValueError('Expected one 256x192 RGB panel')
    output = bytearray(width*240*3)
    margin = (width-320)//2
    for x in range(320):
        for y in range(240):
            source = ((y*192//240)*256+x*256//320)*3
            target = ((x+margin)*240+239-y)*3
            output[target:target+3] = rgb[source:source+3][::-1]
    return bytes(output)


def prepare_frames(directory):
    result = bytearray()
    inputs = {}
    for frame in FRAMES:
        path = directory/f'mario-save-trace-v2-frame-{frame}.ppm'
        data = path.read_bytes()
        if not data.startswith(b'P6\n256 384\n255\n') or len(data) != 15+256*384*3:
            raise ValueError('Unexpected baseline PPM: '+str(path))
        pixels = data[15:]
        inputs[path.name] = hashlib.sha256(data).hexdigest()
        result += convert_panel(pixels[:256*192*3], 400)
        result += convert_panel(pixels[256*192*3:], 320)
    checksum = fnv(result)
    header = struct.pack('<8s6I', b'RAPRF1\0\0', len(FRAMES), 400, 320, 240,
                         len(result), checksum)
    return header + result, inputs


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('baseline_directory', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    dkp = Path(os.environ.get('DEVKITPRO', '/opt/devkitpro'))
    arm, ctru, tools = dkp/'devkitARM', dkp/'libctru', dkp/'tools/bin'
    assets, snapshots = prepare_frames(args.baseline_directory)
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    (output/'frames.bin').write_bytes(assets)
    target = output/'ra-arm11-test'
    compositor = ROOT/'tools/research/twlbg_postcompose'
    font = ROOT/'retail/cardenginei/arm9_ra'
    sources = [HERE/'source/main.c', compositor/'postcompose.c', font/'source/ra_text.c']
    command = [str(arm/'bin/arm-none-eabi-gcc'), '-std=gnu11', '-O2', '-g', '-Wall', '-Wextra',
               '-Werror', '-Wframe-larger-than=4096', '-fstack-usage', '-march=armv6k',
               '-mtune=mpcore', '-mfloat-abi=hard', '-mtp=soft', '-D__3DS__',
               '-ffunction-sections', '-fdata-sections', '-specs=3dsx.specs',
               '-I'+str(ctru/'include'), '-I'+str(compositor), '-I'+str(font/'include'),
               '-I'+str(ROOT/'retail/common/include'),
               '-I'+str(ROOT/'tools/research/tetris_gfx_order/research_include'),
               *map(str, sources), '-L'+str(ctru/'lib'), '-lctru', '-lm',
               '-Wl,-Map,'+str(target)+'.map', '-o', str(target)+'.elf']
    subprocess.run(command, cwd=output, check=True)
    subprocess.run([tools/'smdhtool', '--create', 'RA ARM11 Test',
                    'Teste visual ARM11 - capturas DS, fora do jogo',
                    'RA DS research', ctru/'default_icon.png', str(target)+'.smdh'], check=True)
    subprocess.run([tools/'3dsxtool', str(target)+'.elf', str(target)+'.3dsx',
                    '--smdh='+str(target)+'.smdh'], check=True)
    files = [*sources, HERE/'build.py', compositor/'postcompose.h',
             Path(str(target)+'.elf'), Path(str(target)+'.3dsx'),
             Path(str(target)+'.smdh'), output/'frames.bin']
    report = {'status': 'native_homebrew_built_not_hardware_tested',
              'scope': 'Native ARM11 visual/timing test; captured DS images; no DS/TwlBg integration',
              'snapshots': snapshots, 'asset_fnv1a': hex(fnv(assets[32:])),
              'build_command': command,
              'sha256': {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in files},
              'remote_target': '/3ds/ra-arm11-test/', 'bootstrap_firmware_changes': False}
    (output/'manifest.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps({'artifact':str(target)+'.3dsx',
                      'sha256':report['sha256'][str(target)+'.3dsx'], 'asset_size':len(assets)}))


if __name__ == '__main__':
    main()
