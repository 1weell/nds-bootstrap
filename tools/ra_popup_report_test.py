#!/usr/bin/env python3
"""Read-only report CLI regression: bind old/new layouts to their own artifact/ELF."""
import contextlib,hashlib,io,json,sys,tempfile
from pathlib import Path
from unittest.mock import patch
import ra_popup_report as report

def main():
    with tempfile.TemporaryDirectory() as folder:
        root=Path(folder);artifact=root/'release.nds';elf=root/'menu.elf'
        artifact.write_bytes(b'artifact');elf.write_bytes(b'elf')
        offset=0x100
        manifest={'artifact_sha256':hashlib.sha256(artifact.read_bytes()).hexdigest(),
                  'igm_elf_sha256':hashlib.sha256(elf.read_bytes()).hexdigest(),
                  'popup_pagefile_offset':offset}
        Path(str(artifact)+'.manifest.json').write_text(json.dumps(manifest))
        for size,magic in ((92,0x32445052),(108,0x33445052),(136,0x34445052),(304,0x35445052)):
            record=report.Popup();record.magic=magic;record.allowed=1;record.bridgeStatus=1;record.bridgeSent=2
            data=bytes(record)[:size];reads=[]
            class Connection:
                def __init__(self):self.position=0
                def recv(self,n):
                    count=min(n,17);part=data[self.position:self.position+count];self.position+=len(part);return part
                def close(self):pass
            class FTP:
                def connect(self,*args,**kwargs):pass
                def login(self):pass
                def retrbinary(self,command,write):write(artifact.read_bytes())
                def voidcmd(self,command):pass
                def transfercmd(self,command,rest):reads.append(rest);return Connection()
                def close(self):pass
            symbols=f'02f88100 {size:08x} b raPopupLast\n'
            argv=['report','fixture','--artifact',str(artifact),'--menu-elf',str(elf)]
            output=io.StringIO()
            with patch.object(sys,'argv',argv),patch.object(report,'FTP',FTP),\
                 patch.object(report.subprocess,'check_output',return_value=symbols),contextlib.redirect_stdout(output):
                report.main()
            decoded=json.loads(output.getvalue());assert reads==[offset] and decoded['enabled']
            if size>=108:assert decoded['bridge']['delivered']==2
        # A mismatched artifact/ELF manifest must fail before any network read.
        elf.write_bytes(b'changed')
        with patch.object(sys,'argv',argv),patch.object(report,'FTP',side_effect=AssertionError('network reached')),\
             patch.object(report.subprocess,'check_output',return_value=symbols):
            try:report.main();raise AssertionError('mismatch accepted')
            except RuntimeError as error:assert 'layout differs' in str(error)
    print('PASSED report CLI: RPD2/3/4/5, retained ELF, bounded reads and pre-network mismatch refusal')

if __name__=='__main__':main()
