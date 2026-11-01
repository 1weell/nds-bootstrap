#!/usr/bin/env python3
"""FTP transaction tests; never opens a network connection."""
from io import BytesIO
from pathlib import Path
import tempfile
from deploy_package import install,CXI,BOOTSTRAP,CONFIG,arm11_config,digest

class FTPFixture:
    def __init__(self,fail=False):
        self.files={CXI:b'old-cxi',BOOTSTRAP:b'old-bootstrap',CONFIG:b'overlay=1\noverlay_games=42\npassword=PRIVATE_TEST_SENTINEL\n'}
        self.fail=fail
    def retrbinary(self,command,write):write(self.files[command[5:]])
    def storbinary(self,command,source):self.files[command[5:]]=source.read()
    def delete(self,path):del self.files[path]
    def rename(self,source,target):
        if self.fail and target==BOOTSTRAP:self.fail=False;raise OSError('injected promotion failure')
        self.files[target]=self.files.pop(source)

def main():
    for fail in (False,True):
        ftp=FTPFixture(fail);originals=dict(ftp.files)
        with tempfile.TemporaryDirectory() as folder:
            try:
                result=install(ftp,{CXI:b'new-cxi',BOOTSTRAP:b'new-bootstrap'},Path(folder)/'backup',digest(originals[CXI]))
                assert not fail and result['readback_verified']
                assert ftp.files[CONFIG]==originals[CONFIG]+b'renderer=arm11\n'
                assert ftp.files[CXI]==b'new-cxi'
            except OSError:
                assert fail and all(ftp.files[k]==v for k,v in originals.items())
    assert arm11_config(b'renderer=legacy\r\noverlay=0\r\n')==b'renderer=arm11\r\noverlay=0\r\n'
    print('PASSED deployment: staged readback, unique backups, paired promotion, rollback and preservation of credentials/policy')
if __name__=='__main__':main()
