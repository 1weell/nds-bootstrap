#!/usr/bin/env python3
"""Production cache reader: boundary, interrupted read, publication and fallback."""
import pathlib, tempfile, subprocess, os
root=pathlib.Path(__file__).resolve().parent.parent
source=(root/'retail/arm9/source/ra_wifi.c').read_text()
a=source.index('static bool raWifiCacheLoad(bool sdFound) {')
b=source.index('\nstatic void raWifiDumpDefinitions(',a)
pre=r'''
#define _GNU_SOURCE
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include <sys/mman.h>
#include "ra_wifi.h"
#include "locations.h"
static char romHash[33]="test-hash", fixture[128];
static int shortRead, restored;
static void raWifiCachePath(char* out,size_t n,bool sd) { (void)sd;snprintf(out,n,"%s",fixture); }
static void raWifiLog(const char* fmt,...) { (void)fmt; }
static void loadRaDefinitions(void) { ++restored;*(u32*)CARDENGINEI_ARM9_RA_DEFS_BUFFERED_LOCATION=0; }
static size_t testRead(void* out,size_t n,size_t c,FILE* f) {
    if(shortRead) c/=2;
    return fread(out,n,c,f);
}
#define fread testRead
'''
main=r'''
#undef fread
#define CHECK(x) do { if(!(x)) { fprintf(stderr,"FAIL cache %d: %s\n",__LINE__,#x);return 1; } } while(0)
int main(int argc,char** argv) {
    (void)argc;snprintf(fixture,sizeof(fixture),"%s",argv[1]);
    CHECK(mmap((void*)CARDENGINEI_ARM9_RA_DEFS_BUFFERED_LOCATION,0x8000,PROT_READ|PROT_WRITE,MAP_PRIVATE|MAP_ANONYMOUS|MAP_FIXED,-1,0)!=MAP_FAILED);
    const size_t limit=CARDENGINEI_ARM9_RA_DEFS_MAX-CARDENGINEI_ARM9_RA_PENDING_MAX-CARDENGINEI_ARM9_RA_VIEWER_MAX-CARDENGINEI_ARM9_RA_SESSION_MAX-CARDENGINEI_ARM9_RA_DEFS_HEADER-1;
    size_t sizes[]={0,1,limit-1,limit,limit+1,0x7ff0};
    char text[0x8000];memset(text,'a',sizeof(text));
    for(unsigned i=0;i<sizeof(sizes)/sizeof(*sizes);++i) {
        memset((void*)CARDENGINEI_ARM9_RA_DEFS_BUFFERED_LOCATION,0x5a,0x8000);
        FILE* f=fopen(fixture,"wb");fwrite(text,1,sizes[i],f);fclose(f);
        int expected=sizes[i]>0 && sizes[i]<limit;
        CHECK(raWifiCacheLoad(1)==expected);
        if(expected) CHECK(*(u32*)CARDENGINEI_ARM9_RA_DEFS_BUFFERED_LOCATION==CARDENGINEI_ARM9_RA_DEFS_MAGIC);
        else CHECK(*(u32*)CARDENGINEI_ARM9_RA_DEFS_BUFFERED_LOCATION==0x5a5a5a5a);
        for(size_t j=limit+CARDENGINEI_ARM9_RA_DEFS_HEADER;j<0x8000;++j)
            CHECK(*((u8*)CARDENGINEI_ARM9_RA_DEFS_BUFFERED_LOCATION+j)==0x5a);
    }
    FILE* f=fopen(fixture,"wb");fwrite(text,1,100,f);fclose(f);
    shortRead=1;CHECK(!raWifiCacheLoad(1));CHECK(restored==1);
    CHECK(*(u32*)CARDENGINEI_ARM9_RA_DEFS_BUFFERED_LOCATION==0);
    puts("PASSED production cache: size bounds, reserved memory, partial read fallback");return 0;
}
'''
with tempfile.TemporaryDirectory(prefix='ra-cache-') as tmp:
    tmp=pathlib.Path(tmp);(tmp/'nds').mkdir()
    (tmp/'nds/ndstypes.h').write_text('#include <stdint.h>\n#include <stdbool.h>\ntypedef uint8_t u8;typedef uint16_t u16;typedef uint32_t u32;typedef int32_t s32;typedef int16_t s16;typedef int8_t s8;')
    (tmp/'test.c').write_text(pre+source[a:b]+main)
    subprocess.run([os.environ.get('CC','cc'),'-std=gnu99','-O1','-I'+str(tmp),'-I'+str(root/'retail/common/include'),str(tmp/'test.c'),'-o',str(tmp/'test')],check=True)
    subprocess.run([str(tmp/'test'),str(tmp/'cache')],check=True)
