#!/usr/bin/env python3
"""Read saved popup evidence via FTP; no config, credentials or remote writes.
The menu's normal unload saves raPopupLast inside its existing 0xA000 pagefile area.
"""
import argparse
import ctypes
import hashlib
import json
import pathlib
import re
import shutil
import subprocess
from ftplib import FTP
from io import BytesIO

class Popup(ctypes.LittleEndianStructure):
    _fields_ = [(name, ctypes.c_uint32) for name in
                ('magic', 'shows', 'denied', 'evicted', 'dispcnt', 'window', 'liveDispcnt')]
    _fields_ += [('liveBright', ctypes.c_uint16), ('vramEverOn', ctypes.c_uint16),
                ('vramCnt', ctypes.c_uint8 * 9), ('liveVramCnt', ctypes.c_uint8 * 9),
                ('state', ctypes.c_uint8), ('allowed', ctypes.c_uint8),
                ('preview', ctypes.c_uint8), ('startupState', ctypes.c_uint8),
                ('startupQueued', ctypes.c_uint8), ('row', ctypes.c_uint8),
                ('covered', ctypes.c_uint16), ('originalCovered', ctypes.c_uint16),
                ('bgcnt', ctypes.c_uint16 * 4), ('blendControl', ctypes.c_uint16),
                ('blendAlpha', ctypes.c_uint16), ('blendY', ctypes.c_uint16),
                ('stripWords', ctypes.c_uint16), ('heldFrames', ctypes.c_uint16),
                ('powerControl', ctypes.c_uint16), ('panelFlips', ctypes.c_uint16),
                ('writeLineMin', ctypes.c_uint16), ('writeLineMax', ctypes.c_uint16),
                ('lateSamples', ctypes.c_uint16), ('objClobbered', ctypes.c_uint16),
                ('tileRepairs', ctypes.c_uint16)]
    _fields_ += [(name,ctypes.c_uint32) for name in ('bridgeSent','bridgeDropped','bridgeTimeouts')]
    _fields_ += [(name,ctypes.c_uint8) for name in ('bridgeQueued','bridgeStatus','titleSource','coveragePartial')]
    _fields_ += [(name,ctypes.c_uint32) for name in ('arm11Magic','arm11Format','arm11Stride','arm11Shown','arm11Rejected','arm11CacheErrors','arm11MaxTicks')]
    _fields_ += [(name,ctypes.c_uint32) for name in ('arm11BottomCalls','arm11Composited','arm11RejectedFormat','arm11RejectedAddress',
        'arm11AllocationErrors','arm11NoFreeBuffer','arm11PoolBase','arm11LastSource','arm11LastOutput',
        'arm11LastIndex','arm11LastSelect','arm11Mode','arm11SurfaceChanges','arm11GpuBusy','arm11ActiveRejected')]
    _fields_ += [('arm11Surfaces',ctypes.c_uint32*16)]
    _fields_ += [('arm11CompositeMaxTicks',ctypes.c_uint32),('arm11CompositeBins',ctypes.c_uint32*8),
                ('arm11CompositeTotalLow',ctypes.c_uint32),('arm11CompositeTotalHigh',ctypes.c_uint32)]

def composition_timing(p):
    counts=list(p.arm11CompositeBins);total=sum(counts);limits=[0,100,250,500,1000,2000,4000,8000]
    maximum=p.arm11CompositeMaxTicks/268.123480
    def bounds(percent):
        if not total:return None
        rank=(total*percent+99)//100;accumulated=0
        for i,count in enumerate(counts):
            accumulated+=count
            if accumulated>=rank:return [limits[i],limits[i+1] if i<7 else round(maximum,1)]
    ticks=(p.arm11CompositeTotalHigh<<32)|p.arm11CompositeTotalLow
    return {'samples':total,'bins':counts,'max_us':round(maximum,1),
            'mean_us':round(ticks/268.123480/total,1) if total else None,
            'p50_us_bounds':bounds(50),'p95_us_bounds':bounds(95)}

def decode(data):
    minimum={0x32445052:92,0x33445052:108,0x34445052:136,0x35445052:304}.get(int.from_bytes(data[:4],'little'),92)
    if len(data)<minimum:
        raise ValueError('Truncated popup diagnostic record')
    p = Popup.from_buffer_copy(bytes(data).ljust(ctypes.sizeof(Popup),b'\0'))
    if p.magic not in (0x32445052,0x33445052,0x34445052,0x35445052):
        raise ValueError('No current popup evidence: open the RA menu, close with B, then HOME')
    mode = (p.liveDispcnt >> 16) & 3
    if not p.allowed:
        reason = 'disabled by session policy'
    elif p.state & 0x80 and (mode != 1 or p.liveDispcnt & 0x80):
        reason = 'pending: screen not in visible graphics mode'
    elif p.state & 0x80:
        reason = 'pending: waiting to draw (inspect brightness and resources)'
    elif p.denied:
        reason = 'draw denied: inspect graphics resources/text'
    elif p.shows:
        reason = 'draw attempted; inspect windows/VRAM/eviction if not visible'
    else:
        reason = 'no draw attempt recorded'
    bridge=None
    if p.magic in (0x33445052,0x34445052,0x35445052) and p.bridgeStatus!=3:
        bridge={'status':{0:'pending',1:'connected',2:'unavailable'}.get(p.bridgeStatus,'unknown'),
                'queued':p.bridgeQueued,'delivered':p.bridgeSent,'dropped':p.bridgeDropped,
                'timeouts':p.bridgeTimeouts,'title_source':{0:'ROM header',1:'RA',2:'cached RA'}.get(p.titleSource,'unknown'),
                'coverage_partial':bool(p.coveragePartial)}
        reason='ARM11 '+bridge['status']+'; delivery acknowledgement is not a server award'
        if (p.magic==0x34445052 and p.arm11Magic==0x31545341) or (p.magic==0x35445052 and p.arm11Magic==0x32545341):
            bridge['arm11']={'format':hex(p.arm11Format),'stride':p.arm11Stride,'shown':p.arm11Shown,
                'rejected_frames':p.arm11Rejected,'cache_errors':p.arm11CacheErrors,
                'max_hook_us':round(p.arm11MaxTicks/268.123480,1)}
            if p.magic==0x35445052:
                bridge['arm11'].update({'bottom_calls':p.arm11BottomCalls,'composited_frames':p.arm11Composited,
                    'rejected_format':p.arm11RejectedFormat,'rejected_address_or_object':p.arm11RejectedAddress,
                    'allocation_errors':p.arm11AllocationErrors,'no_free_output':p.arm11NoFreeBuffer,
                    'pool_base':hex(p.arm11PoolBase),'last_source':hex(p.arm11LastSource),'last_output':hex(p.arm11LastOutput),
                    'last_index':p.arm11LastIndex,'last_select':hex(p.arm11LastSelect),'private_output':p.arm11Mode==1,
                    'composition_mode':{1:'experimental-private',2:'in-place-hud-cache-span'}.get(p.arm11Mode,'unknown'),
                    'surface_changes':p.arm11SurfaceChanges,'gpu_busy':p.arm11GpuBusy,'active_rejected':p.arm11ActiveRejected,
                    'composition_timing':composition_timing(p),
                    'recent_surfaces':[{'address':hex(p.arm11Surfaces[i]),'stride':p.arm11Surfaces[i+1],
                        'format':hex(p.arm11Surfaces[i+2]),'samples':p.arm11Surfaces[i+3]&0xffffff,
                        'reason_bits':hex(p.arm11Surfaces[i+3]>>24)} for i in range(0,16,4) if p.arm11Surfaces[i+3]]})
    return {'enabled': bool(p.allowed), 'shows': p.shows, 'denied': p.denied,
            'evicted': p.evicted, 'state': hex(p.state),
            'last_display': hex(p.dispcnt), 'last_windows': hex(p.window),
            'live_display': hex(p.liveDispcnt), 'live_brightness': hex(p.liveBright),
            'vram_ever_on': hex(p.vramEverOn),
            'last_vram': [hex(i) for i in p.vramCnt],
            'live_vram': [hex(i) for i in p.liveVramCnt],
            'preview_status': p.preview, 'startup_state': p.startupState,
            'startup_queued': bool(p.startupQueued), 'row': p.row,
            'covered_area': p.covered, 'original_covered_area': p.originalCovered,
            'bg_control': [hex(i) for i in p.bgcnt],
            'blend_control': hex(p.blendControl), 'blend_alpha': hex(p.blendAlpha),
            'blend_y': hex(p.blendY), 'strip_ink_words': p.stripWords,
            'held_frames': p.heldFrames, 'power_control': hex(p.powerControl),
            'panel_flips': p.panelFlips, 'write_line_min': p.writeLineMin,
            'write_line_max': p.writeLineMax, 'late_write_samples': p.lateSamples,
            'oam_overwritten_frames': p.objClobbered, 'tile_repairs': p.tileRepairs,
            'bridge':bridge,'interpretation': reason}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('host')
    parser.add_argument('--port', type=int, default=5000)
    parser.add_argument('--artifact', default='nds-bootstrap-3ds-ra-reconcile.nds')
    parser.add_argument('--menu-elf', type=pathlib.Path,
                        help='Matching retained menu ELF when reading an older installed release')
    parser.add_argument('--output', type=pathlib.Path)
    args = parser.parse_args()
    root = pathlib.Path(__file__).resolve().parent.parent
    elf = args.menu_elf or root / 'retail/cardenginei/arm9_igm/build/cardenginei_arm9_igm.elf'
    nm = [shutil.which('arm-none-eabi-nm') or '/path/to/projects/dkp-image/dkp.sh']
    if nm[0].endswith('dkp.sh'): nm.append('arm-none-eabi-nm')
    symbols = subprocess.check_output([*nm, '-S', str(elf)], text=True)
    match = re.search(r'^([0-9a-fA-F]+) ([0-9a-fA-F]+) [bBdD] raPopupLast$', symbols, re.M)
    if not match: raise RuntimeError('Build lacks raPopupLast; rebuild first')
    diagnostic_bytes=int(match[2],16)
    if diagnostic_bytes not in (92,108,136,ctypes.sizeof(Popup)):
        raise RuntimeError('Unsupported diagnostic layout in menu ELF')
    offset = int(match[1], 16) - 0x02F88000
    if not 0 <= offset <= 0xA000 - diagnostic_bytes:
        raise RuntimeError('Diagnostic lies outside the saved menu image')
    artifact = pathlib.Path(args.artifact)
    if not artifact.is_absolute(): artifact = root / artifact
    expected = hashlib.sha256(artifact.read_bytes()).digest()
    manifest = json.loads(pathlib.Path(str(artifact) + '.manifest.json').read_text())
    if (manifest.get('artifact_sha256') != expected.hex()
        or manifest.get('igm_elf_sha256') != hashlib.sha256(elf.read_bytes()).hexdigest()
        or manifest.get('popup_pagefile_offset') != offset):
        raise RuntimeError('Artifact/menu layout differs from release manifest; rebuild first')
    ftp = FTP(); ftp.connect(args.host, args.port, timeout=15); ftp.login()
    try:
        remote = BytesIO(); ftp.retrbinary('RETR /_nds/nds-bootstrap-release.nds', remote.write)
        if hashlib.sha256(remote.getvalue()).digest() != expected:
            raise RuntimeError('Installed bootstrap differs from the chosen artifact; offset unsafe')
        ftp.voidcmd('TYPE I')
        data = bytearray()
        connection = ftp.transfercmd('RETR /_nds/pagefile.sys', rest=offset)
        try:
            while len(data) < diagnostic_bytes:
                chunk = connection.recv(diagnostic_bytes - len(data))
                if not chunk: raise RuntimeError('Short pagefile read')
                data.extend(chunk)
        finally:
            connection.close()
    finally:
        # A deliberately bounded RETR may leave a transfer-completion reply;
        # close this read-only session instead of issuing another command.
        ftp.close()
    report = {'pagefile_offset': hex(offset), **decode(data)}
    text = json.dumps(report, indent=2) + '\n'
    if args.output: args.output.write_text(text)
    print(text, end='')

if __name__ == '__main__': main()
