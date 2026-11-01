#!/usr/bin/env python3
"""Install a verified bootstrap/TwlBg pair. Backups and staged bytes are read back before promotion."""
import argparse
from datetime import datetime,timezone
from ftplib import FTP
import hashlib
from io import BytesIO
import json
import os
from pathlib import Path
import re
import secrets

CXI='/luma/sysmodules/TwlBg.cxi'
BOOTSTRAP='/_nds/nds-bootstrap-release.nds'
CONFIG='/_nds/nds-bootstrap/ra.cfg'
BASELINE='7c7af9a5dbb6d69b63e0fa7f3248b7736626a53c32fea8e4daf655ccbc931628'

def digest(data):return hashlib.sha256(data).hexdigest()
def download(ftp,path):
    out=BytesIO();ftp.retrbinary('RETR '+path,out.write);return out.getvalue()
def upload(ftp,path,data):
    ftp.storbinary('STOR '+path,BytesIO(data))
    if digest(download(ftp,path))!=digest(data):raise RuntimeError('FTP readback mismatch: '+path)
def arm11_config(data):
    # Preserve every other byte/setting, including credentials and popup allowlist.
    newline=b'\r\n' if b'\r\n' in data else b'\n'
    pattern=rb'(?im)^[ \t]*renderer[ \t]*=[^\r\n]*'
    if re.search(pattern,data):return re.sub(pattern,b'renderer=arm11',data)
    return data+(newline if data and not data.endswith(b'\n') else b'')+b'renderer=arm11'+newline

def install(ftp,files,backup_dir,expected_cxi=BASELINE):
    backup_dir.mkdir(parents=True,exist_ok=False,mode=0o700)
    nonce=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+secrets.token_hex(3)
    originals={path:download(ftp,path) for path in (CXI,BOOTSTRAP,CONFIG)}
    if expected_cxi and digest(originals[CXI])!=expected_cxi:
        raise RuntimeError('Existing TwlBg differs from the reviewed baseline; no remote files changed')
    files=dict(files);files[CONFIG]=arm11_config(originals[CONFIG])
    record={'timestamp_utc':datetime.now(timezone.utc).isoformat(),'files':[],
            'readback_verified':False,'hardware_validated':False}
    promoted=[];staged={}
    try:
        for index,(path,data) in enumerate(files.items()):
            local=backup_dir/('original-'+str(index)+'.bin')
            fd=os.open(local,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
            with os.fdopen(fd,'wb') as output:output.write(originals[path])
            backup=path+'.before-antigravity-v7-'+nonce
            stage=path+'.antigravity-v7-'+nonce+'.part'
            # Unique names; never overwrite another backup.
            upload(ftp,backup,originals[path]);upload(ftp,stage,data)
            staged[path]=stage
            record['files'].append({'target':path,'backup':backup,
                'previous_sha256':digest(originals[path]),'candidate_sha256':digest(data)})
        for path,data in files.items():
            # FTP servers need not implement replacement-by-rename. Keep a verified
            # second remote copy plus local original while removing only this target.
            ftp.delete(path)
            promoted.append(path)
            ftp.rename(staged[path],path)
            if digest(download(ftp,path))!=digest(data):raise RuntimeError('Promotion verification failed: '+path)
        record['readback_verified']=True
    except Exception:
        failures=[]
        for path in reversed(promoted):
            try:upload(ftp,path,originals[path])
            except Exception:failures.append(path)
        record['rolled_back']=not failures;record['rollback_failed']=failures
        (backup_dir/'installation.json').write_text(json.dumps(record,indent=2)+'\n')
        if failures:raise RuntimeError('Rollback failed for '+', '.join(failures)) from None
        raise
    finally:
        for stage in staged.values():
            try:ftp.delete(stage)
            except Exception:pass
    (backup_dir/'installation.json').write_text(json.dumps(record,indent=2)+'\n')
    return record

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('host');parser.add_argument('package',type=Path)
    parser.add_argument('--port',type=int,default=5000)
    parser.add_argument('--backup-dir',type=Path,required=True)
    parser.add_argument('--expected-cxi-sha256',default=BASELINE)
    args=parser.parse_args()
    manifest=json.loads((args.package/'package.json').read_text())
    files={}
    for name,target in (('TwlBg.cxi',CXI),('nds-bootstrap.nds',BOOTSTRAP)):
        data=(args.package/name).read_bytes()
        if digest(data)!=manifest['sha256'][name]:raise RuntimeError('Package hash mismatch: '+name)
        files[target]=data
    if manifest['renderer']!='typed-events':raise RuntimeError('Paired deployment requires typed-events renderer')
    with FTP() as ftp:
        ftp.connect(args.host,args.port,timeout=15);ftp.login()
        result=install(ftp,files,args.backup_dir,args.expected_cxi_sha256)
    print(json.dumps({'readback_verified':result['readback_verified'],
                      'hardware_validated':False,'record':str(args.backup_dir/'installation.json')}))
if __name__=='__main__':main()
