#!/usr/bin/env python3
"""Production popup staging and pure policy; no emulated Wi-Fi success."""
import pathlib, tempfile, subprocess, os
root=pathlib.Path(__file__).resolve().parent.parent
source=(root/'retail/arm9/source/ra_wifi.c').read_text()
a=source.index('static void raWifiStageSession(')
b=source.index('\nvoid raWifiProbe(',a)
probe=source[b:]
assert probe.index('raWifiStageSession(')>probe.index('\ndone:')>probe.index('raWifiIdentify(')
pre=r'''
#define _GNU_SOURCE
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include <stdarg.h>
#include <sys/mman.h>
#include "ra_wifi.h"
#include "locations.h"
static char logs[4096];
static void raWifiLog(const char* fmt,...) {
    va_list args;va_start(args,fmt);vsnprintf(logs+strlen(logs),sizeof(logs)-strlen(logs),fmt,args);va_end(args);
}
static void raWifiEssential(const char* fmt,...) { (void)fmt; }
'''
main=r'''
#define CHECK(x) do { if(!(x)) { fprintf(stderr,"FAIL session: %s\n",#x);return 1; } } while(0)
int main(void) {
    CHECK(mmap((void*)0x02630000,0x9000,PROT_READ|PROT_WRITE,MAP_PRIVATE|MAP_ANONYMOUS|MAP_FIXED,-1,0)!=MAP_FAILED);
    u32 ids[]={9878,0,12345};
    raSessionBlock* block=(raSessionBlock*)CARDENGINEI_ARM9_RA_SESSION_BUFFERED_LOCATION;
    for(unsigned level=0;level<=2;++level) for(unsigned i=0;i<3;++i) {
        logs[0]=0;
        int allowed=raOverlayAllowed(level,"9878",ids[i]);
        raWifiStageSession(0,0,allowed,RA_QUEUE_LEVEL_FULL,level,ids[i],true);
        CHECK(block->magic==RA_SESSION_MAGIC && block->hardcore==0 && block->queue==RA_QUEUE_LEVEL_FULL);
        CHECK(block->overlay==(level==2 || (level==1 && ids[i]==9878)));
        CHECK(block->gameId==ids[i] && block->startupMagic==RA_STARTUP_MAGIC);
        CHECK(block->startupState==(ids[i] ? RA_STARTUP_CONFIRMED : RA_STARTUP_NONE));
        if(level==1 && ids[i]==0) CHECK(strstr(logs,"game not identified"));
        if(level==1 && ids[i]==12345) CHECK(strstr(logs,"overlay_games"));
    }
    *(u32*)CARDENGINEI_ARM9_RA_DEFS_BUFFERED_LOCATION=CARDENGINEI_ARM9_RA_DEFS_MAGIC;
    raPendingBlock* pending=(raPendingBlock*)CARDENGINEI_ARM9_RA_PENDING_BUFFERED_LOCATION;
    pending->magic=RA_PENDING_MAGIC;strcpy(pending->thisTitle,"TETRIS DS");
    raWifiStageSession(0,0,1,RA_QUEUE_LEVEL_FULL,1,9878,false);
    CHECK(block->startupState==RA_STARTUP_OFFLINE);
    CHECK(!strcmp(block->gameTitle,"TETRIS DS"));
    puts("PASSED production session: popup policy and staging; identification precedes decision");return 0;
}
'''
with tempfile.TemporaryDirectory(prefix='ra-session-') as tmp:
    tmp=pathlib.Path(tmp);(tmp/'nds').mkdir()
    (tmp/'nds/ndstypes.h').write_text('#include <stdint.h>\n#include <stdbool.h>\ntypedef uint8_t u8;typedef uint16_t u16;typedef uint32_t u32;typedef int32_t s32;typedef int16_t s16;typedef int8_t s8;')
    (tmp/'test.c').write_text(pre+source[a:b]+main)
    subprocess.run([os.environ.get('CC','cc'),'-std=gnu99','-O1','-DRA_LAUNCHER_WIFI=1','-Dsniprintf=snprintf','-I'+str(tmp),'-I'+str(root/'retail/common/include'),str(tmp/'test.c'),str(root/'retail/arm9/source/ra_cfg.c'),'-o',str(tmp/'test')],check=True)
    subprocess.run([str(tmp/'test')],check=True)
