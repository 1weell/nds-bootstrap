#!/usr/bin/env python3
"""Test actual submit function and JSON parser without sockets or account data."""
import pathlib, tempfile, subprocess, os
root=pathlib.Path(__file__).resolve().parent.parent
source=(root/'retail/arm9/source/ra_wifi.c').read_text()
a=source.index('static void raWifiRememberConfirmed(')
b=source.index('\n/*',source.index('static void raWifiSubmitOne('))
merge_start=source.index('static void raWifiMergeConfirmed(void) {')
merge_end=source.index('\nstatic void raWifiSubmitQueue(',merge_start)
prelude=r'''
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include <time.h>
#include "ra_wifi.h"
#include "ra_confirmed.h"
#define RA_WIFI_UNLOCKS_MAX 128
static raConfirmed confirmed;
static int earnedCount;
static u32 earnedId[128], earnedWhen[128];
static s32 clockOffset;
static bool confirmedDirty;
static u32 unlockedIds[128];
static u16 unlockCount;
static raWifiVerdict verdict;
#define sniprintf snprintf
static char raUser[64]="test",raToken[64]="not-a-real-token";
static const char* reply;
static int result;
static void raWifiLog(const char* format,...) { (void)format; }
static void raWifiLogBody(const char* title,const char* body) { (void)title;(void)body; }
static void raWifiReportAttempts(const char* title,const raNetProgress* p) { (void)title;(void)p; }
int raNetHttpGet(const char* host,const char* path,char* out,int size,raNetProgress* p) {
    (void)host;(void)path;(void)p;
    snprintf(out,size,"%s",reply);return result;
}
#define CHECK(x) do { if(!(x)) { fprintf(stderr,"FAIL submit: %s\n",#x);exit(1); } } while(0)
'''
main=r'''
int main(void) {
    raQueue q;
    const char* failures[]={"{}","{\"Success\":false,\"Error\":\"signature\"}","{\"Success\":\"true\"}",""};
    result=20;reply="{\"Success\":true,\"AchievementID\":230047}";
    memset(&q,0,sizeof(q));raWifiSubmitOne(230047,0,0,&q);
    CHECK(q.accepted==1 && q.kept==0 && q.refused==0);
    CHECK(confirmed.count==1 && confirmed.ids[0]==230047 && confirmedDirty);
    /* Reproduce the real boot: award accepted, then a stale lookup omits it. */
    unlockedIds[0]=230041;unlockCount=1;raWifiMergeConfirmed();
    CHECK(unlockCount==2 && unlockedIds[1]==230047 && verdict.unlocksKnown);
    unsigned char proof[RA_CONFIRMED_BYTES];int proofSize=raConfirmedEncode(&confirmed,raUser,proof,sizeof(proof));
    memset(&confirmed,0,sizeof(confirmed));earnedCount=0;unlockCount=1;
    CHECK(raConfirmedDecode(&confirmed,raUser,proof,proofSize));raWifiMergeConfirmed();
    CHECK(unlockCount==2 && unlockedIds[1]==230047);
    raPatch patch;char block[1024];
    const char* json="{\"Achievements\":[{\"ID\":230047,\"MemAddr\":\"0xH1=1\",\"Title\":\"Tetris Time\",\"Description\":\"Clear four\",\"Points\":5,\"Flags\":3}]}";
    raPatchReset(&patch,block,sizeof(block));patch.skipIds=unlockedIds;patch.skipCount=unlockCount;
    raPatchFeed(&patch,json,strlen(json));raPatchFinish(&patch);
    CHECK(patch.earned==1 && patch.kept==0 && strstr(block,"#!230047"));
    for(unsigned i=0;i<sizeof(failures)/sizeof(*failures);++i) {
        reply=failures[i];memset(&q,0,sizeof(q));raWifiSubmitOne(230047,0,0,&q);
        CHECK(q.accepted==0 && q.refused==1 && q.kept==1);
    }
    reply="{\"Success\":true,\"AchievementID\":230045}";
    memset(&q,0,sizeof(q));raWifiSubmitOne(230047,0,0,&q);
    CHECK(q.accepted==0 && q.kept==1 && confirmed.count==1);
    result=-3;reply="";memset(&q,0,sizeof(q));raWifiSubmitOne(230047,0,0,&q);
    CHECK(q.accepted==0 && q.kept==1 && q.sent==0);
    puts("PASSED production submission: success, refusal, ID mismatch, stale lookup, persisted confirmation and earned viewer record");return 0;
}
'''
with tempfile.TemporaryDirectory(prefix='ra-submit-') as tmp:
    tmp=pathlib.Path(tmp);(tmp/'nds').mkdir()
    (tmp/'nds/ndstypes.h').write_text('#include <stdint.h>\n#include <stdbool.h>\ntypedef uint8_t u8;typedef uint16_t u16;typedef uint32_t u32;typedef int32_t s32;typedef int16_t s16;typedef int8_t s8;')
    (tmp/'test.c').write_text(prelude+source[a:b]+source[merge_start:merge_end]+main)
    rc=root/'retail/cardenginei/arm9_ra/rcheevos'
    subprocess.run([os.environ.get('CC','cc'),'-std=gnu99','-O1','-DRA_LAUNCHER_WIFI=1','-DRA_NET_HOST_TEST','-Dsniprintf=snprintf','-I'+str(tmp),'-I'+str(root/'retail/common/include'),'-I'+str(rc/'src'),str(tmp/'test.c'),str(root/'retail/arm9/source/ra_net.c'),str(root/'retail/arm9/source/ra_queue.c'),str(root/'retail/arm9/source/ra_confirmed.c'),str(root/'retail/arm9/source/ra_patch.c'),str(rc/'src/rhash/md5.c'),'-o',str(tmp/'test')],check=True)
    subprocess.run([str(tmp/'test')],check=True)
