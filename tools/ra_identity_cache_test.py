#!/usr/bin/env python3
"""Production hash/GameID persistence and offline popup policy."""
import os
from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parent.parent
source = (root / 'retail/arm9/source/ra_wifi.c').read_text()
begin = source.index('static void raWifiIdentityPath(')
end = source.index('static void raWifiCachePath(', begin)
pre = r'''
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include <sys/stat.h>
#include "ra_wifi.h"
#undef RA_CACHE_DIR
#undef RA_CACHE_DIR_FAT
#define RA_CACHE_DIR directory
#define RA_CACHE_DIR_FAT directory
#define sniprintf snprintf
static char directory[128], romHash[33]="9dbd0337235cd8acf032c0fbfd649d70";
static bool raWifiIdentityRejected;
static struct { u32 gameId; } verdict;
static void raWifiLog(const char* fmt, ...) { (void)fmt; }
'''
main = r'''
#define CHECK(x) do { if (!(x)) { fprintf(stderr,"FAIL identity cache %d: %s\n",__LINE__,#x);return 1; } } while(0)
int main(int argc,char** argv) {
    (void)argc;snprintf(directory,sizeof(directory),"%s",argv[1]);
    char path[96];raWifiIdentityPath(path,sizeof(path),true);
    CHECK(!raWifiPopupGameId(true));
    raWifiIdentityWrite(true,9878);
    CHECK(raWifiIdentityLoad(true)==9878 && raWifiPopupGameId(true)==9878);
    CHECK(verdict.gameId==0); /* local identity cannot invent a network verdict */
    raWifiIdentityRejected=true;CHECK(raWifiPopupGameId(true)==0);
    verdict.gameId=12345;CHECK(raWifiPopupGameId(true)==12345);
    verdict.gameId=0;raWifiIdentityRejected=false;
    const char* invalid[]={
        "", "RAID1 9dbd0337235cd8acf032c0fbfd649d70 9878",
        "RAID1 00000000000000000000000000000000 9878\n",
        "RAID1 9dbd0337235cd8acf032c0fbfd649d70 -1\n",
        "RAID1 9dbd0337235cd8acf032c0fbfd649d70 4294967296\n",
        "RAID1 9dbd0337235cd8acf032c0fbfd649d70 9878 garbage\n",
        "RAID1 9dbd0337235cd8acf032c0fbfd649d70 12345678901\n",
        "RAID1 9dbd0337235cd8acf032c0fbfd649d70 0\n"
    };
    for(unsigned i=0;i<sizeof(invalid)/sizeof(*invalid);++i) {
        FILE* f=fopen(path,"wb");CHECK(f);fputs(invalid[i],f);fclose(f);
        CHECK(raWifiIdentityLoad(true)==0);
    }
    FILE* f=fopen(path,"wb");CHECK(f);
    const char nul[]="RAID1 9dbd0337235cd8acf032c0fbfd649d70 9878\0\n";
    fwrite(nul,1,sizeof(nul)-1,f);fclose(f);CHECK(!raWifiIdentityLoad(true));
    raWifiIdentityWrite(true,0xFFFFFFFFu);CHECK(raWifiIdentityLoad(true)==0xFFFFFFFFu);
    raWifiIdentityWrite(true,0);CHECK(!raWifiIdentityLoad(true));
    raWifiIdentityWrite(true,9878);
    romHash[0]='0';CHECK(!raWifiIdentityLoad(true));romHash[0]='9';
    CHECK(raWifiIdentityLoad(true)==9878);
    puts("PASSED production identity cache: hash binding, truncation, overflow, rejection, offline-only policy");
    return 0;
}
'''
with tempfile.TemporaryDirectory(prefix='ra-identity-') as directory:
    out = Path(directory)
    (out / 'nds').mkdir()
    (out / 'nds/ndstypes.h').write_text(
        '#include <stdint.h>\n#include <stdbool.h>\n'
        'typedef uint8_t u8;typedef uint16_t u16;typedef uint32_t u32;'
        'typedef int8_t s8;typedef int16_t s16;typedef int32_t s32;')
    (out / 'test.c').write_text(pre + source[begin:end] + main)
    subprocess.run([os.environ.get('CC', 'cc'), '-std=gnu99', '-O1',
                    '-I' + str(out), '-I' + str(root / 'retail/common/include'),
                    str(out / 'test.c'), '-o', str(out / 'test')], check=True)
    subprocess.run([str(out / 'test'), str(out / 'cache')], check=True)
