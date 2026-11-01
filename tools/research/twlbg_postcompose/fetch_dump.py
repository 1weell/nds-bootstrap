#!/usr/bin/env python3
"""Download ONLY a completed collector dump via read-only anonymous local FTP.

Private output contains copyrighted console firmware. Never commit/share it.
No remote mutation, key access or execution. Exit 3 means collector not ready.
"""
import argparse
from ftplib import FTP, error_perm
import hashlib
from io import BytesIO
import json
from pathlib import Path
import re

ROOT = '/3ds/ra-twlbg-dump/dumps'
MAX_FIRM = 0x400000


def retrieve(ftp, path, limit):
    buffer = BytesIO()

    def accept(data):
        if buffer.tell() + len(data) > limit:
            # The caller closes FTP on this exception: no stale completion reply.
            raise ValueError('Collector file exceeds expected size limit')
        buffer.write(data)

    ftp.retrbinary('RETR ' + path, accept)
    return buffer.getvalue()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('host')
    parser.add_argument('output', type=Path)
    parser.add_argument('--port', type=int, default=5000)
    args = parser.parse_args()
    if args.output.exists():
        parser.error('Output directory must be new')
    ftp = FTP()
    chosen = None
    try:
        ftp.connect(args.host, args.port, timeout=8)
        ftp.login()
        try:
            listing = ftp.nlst(ROOT)
        except error_perm as error:
            if str(error).startswith(('450', '550', '553')) and 'No such' in str(error):
                print('Collector has not created a dump directory yet')
                return 3
            raise
        directories = sorted(p for p in listing if re.fullmatch(re.escape(ROOT) + r'/\d{3}', p))
        for directory in reversed(directories):
            try:
                raw_report = retrieve(ftp, directory + '/report.txt', 16384)
            except error_perm as error:
                if str(error).startswith(('450', '550', '553')) and 'No such' in str(error):
                    continue
                raise
            fields = dict(line.split('=', 1) for line in raw_report.decode('ascii').splitlines()
                          if '=' in line)
            if fields.get('format') != 'RA_TWL_DUMP_1' or fields.get('status') != 'complete':
                continue
            if fields.get('readback') != 'identical':
                raise ValueError('Completed report lacks identical SD readback')
            size = int(fields['firm_size'])
            if not 512 <= size <= MAX_FIRM:
                raise ValueError('Invalid reported FIRM size')
            data = retrieve(ftp, directory + '/twl.firm', size)
            if len(data) != size or data[:4] != b'FIRM':
                raise ValueError('Downloaded FIRM is truncated or wrong type')
            sha256 = hashlib.sha256(data).hexdigest()
            expected = fields.get('firm_sha256')
            if expected and (not re.fullmatch(r'[0-9a-f]{64}', expected) or expected != sha256):
                raise ValueError('Download differs from collector FIRM SHA256')
            chosen = data, raw_report, directory, sha256, fields
            break
    finally:
        ftp.close()
    if not chosen:
        print('No completed collector dump yet')
        return 3
    data, raw_report, directory, sha256, fields = chosen
    args.output.mkdir(mode=0o700, parents=True, exist_ok=False)
    (args.output / 'twl.firm').write_bytes(data)
    (args.output / 'report.txt').write_bytes(raw_report)
    metadata = {'host': args.host, 'remote_directory': directory, 'firm_size': len(data),
                'firm_sha256': sha256, 'collector_hash_matched': bool(fields.get('firm_sha256')),
                'model': fields.get('model'), 'new3ds': fields.get('new3ds'),
                'title_id': fields.get('title_id'), 'title_version': fields.get('title_version'),
                'system_version': fields.get('system_version'), 'remote_writes': False,
                'status': 'acquired_not_yet_extracted_or_hardware_compatible'}
    (args.output / 'acquisition.json').write_text(json.dumps(metadata, indent=2) + '\n')
    print(json.dumps(metadata, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
