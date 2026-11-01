#!/usr/bin/env python3
"""Package a tested bootstrap and exact-source ARM11 candidate without original firmware."""
import argparse,hashlib,json,shutil
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('bootstrap',type=Path);parser.add_argument('arm11',type=Path);parser.add_argument('output',type=Path)
    args=parser.parse_args()
    build=json.loads((args.arm11/'manifest.json').read_text())
    release=json.loads(Path(str(args.bootstrap)+'.manifest.json').read_text())
    if sha(args.bootstrap)!=release['artifact_sha256']:raise RuntimeError('Bootstrap release hash mismatch')
    if sha(args.arm11/'TwlBg.cxi')!=build['cxi_sha256']:raise RuntimeError('ARM11 build hash mismatch')
    if build['renderer']!='typed-events' or not build.get('source_sha256'):raise RuntimeError('A source-bound typed-events build is required')
    if build.get('compositor')!='in-place-hud-cache-span':raise RuntimeError('Only the HUD cache-span compositor is eligible for the current release; private outputs failed on hardware')
    for name,expected in build['source_sha256'].items():
        if sha(ROOT/name)!=expected:raise RuntimeError('Source changed after ARM11 build: '+name)
    args.output.mkdir(mode=0o700,parents=True,exist_ok=False)
    shutil.copyfile(args.bootstrap,args.output/'nds-bootstrap.nds')
    shutil.copyfile(args.arm11/'TwlBg.cxi',args.output/'TwlBg.cxi')
    (args.output/'nds-bootstrap.nds.manifest.json').write_text(json.dumps(release,indent=2)+'\n')
    source_paths=[
        'retail/common/include/ra_bridge.h','retail/common/include/ra_wifi.h',
        'retail/cardenginei/arm9_ra/source/ra_bridge9.c','retail/cardenginei/arm9_ra/source/ra_rcheevos.c',
        'retail/cardenginei/arm9_ra/source/cardengine.c','retail/cardenginei/arm9_ra/source/ra_overlay.c',
        'retail/cardenginei/arm7/source/clock.c','retail/cardenginei/arm7/source/cardengine.c',
        'retail/arm9/source/ra_cfg.c','retail/arm9/source/ra_wifi.c','retail/arm9/source/ra_patch.c',
        'retail/arm9/source/ra_metadata.c','retail/cardenginei/arm9_igm/source/inGameMenu.c']
    manifest={'renderer':'typed-events','compositor':build['compositor'],'protocol_version':1,'hardware_validated':False,
              'sha256':{name:sha(args.output/name) for name in ('TwlBg.cxi','nds-bootstrap.nds')},
              'bootstrap_sources':{name:sha(ROOT/name) for name in source_paths},
              'arm11_sources':build['source_sha256']}
    (args.output/'package.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(json.dumps({'package':str(args.output),'sha256':manifest['sha256']}))
if __name__=='__main__':main()
