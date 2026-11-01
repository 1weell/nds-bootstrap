#!/usr/bin/env python3
"""Compile actual ARM7 queue functions with fault-injected card I/O, both paths."""
import pathlib, subprocess, tempfile, os
root = pathlib.Path(__file__).resolve().parent.parent
source = (root/'retail/cardenginei/arm7/source/cardengine.c').read_text()
append = source[source.index('static __attribute__((optimize("Os"))) bool raUnlockAppend('):source.index('\nvoid dumpRam(', source.index('static __attribute__((optimize("Os"))) bool raUnlockAppend('))]
service = source[source.index('static void raUnlockService(void) {'):source.index('\nstatic bool start_cardRead_arm9(', source.index('static void raUnlockService(void) {'))]
prelude = r'''
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include "ra_wifi.h"
#define RA_UNLOCK_STATE_MAGIC 0x314C5541
#define RA_UNLOCK_PENDING_MAX RA_QUEUE_MAX
#define RA_UNLOCK_HARDCORE_BIT 0x80000000u
static u32 raUnlocksCluster=1, raUnlockStateMagic, raUnlockPending[RA_UNLOCK_PENDING_MAX], sharedAddr[32];
static u8 raUnlockSlot, raUnlockPendingCount;
static int prevSect[2], raUnlocksFile, readOngoing, calls, failWrite, failRead, critical;
static char raStampCache[14]="20261029120000", raGameCode[4]="AMCE", raGameTitle[12]="TETRIS DS";
static char card[RA_QUEUE_BYTES];
#define tonccpy memcpy
#define toncset memset
static int enterCriticalSection(void) { ++critical; return 1; }
static void leaveCriticalSection(int value) { (void)value; --critical; }
static u32 fileRead(char* out, void* file,u32 offset,u32 n) {
    (void)file;
    if(failRead) return 0;
    if(offset+n>sizeof(card)) abort();
    memcpy(out,card+offset,n);return n;
}
static u32 fileWrite(const char* bytes,void* file,u32 offset,u32 n) {
    (void)file;
    if(++calls==failWrite) return 0;
    if(offset+n>sizeof(card)) abort();
    memcpy(card+offset,bytes,n);return n;
}
#define CHECK(x) do { if(!(x)) { fprintf(stderr,"FAIL ARM7 line %d: %s\n",__LINE__,#x); exit(1); } } while(0)
'''
main = r'''
int main(void) {
    /* Size, absent queue, read fault, retry, last slot, never overflow. */
    raUnlocksCluster=0; CHECK(!raUnlockAppend(230047,0));raUnlocksCluster=1;
    failRead=1; CHECK(!raUnlockAppend(230047,0)); CHECK(raUnlockStateMagic!=RA_UNLOCK_STATE_MAGIC);
    failRead=0; CHECK(raUnlockAppend(230047,1));CHECK(raUnlockSlot==1);
    CHECK(!memcmp(card,"230047\t20261029120000\tAMCE\tTETRIS DS",34));
    CHECK(card[40]=='1');
    raUnlockSlot=RA_QUEUE_MAX-1;CHECK(raUnlockAppend(230048,0));
    CHECK(raUnlockSlot==RA_QUEUE_MAX);CHECK(!raUnlockAppend(230049,0));
    sharedAddr[RA_SHARED_UNLOCK_ID]=230050;
    sharedAddr[RA_SHARED_UNLOCK_REQ]=RA_SHARED_UNLOCK_MAGIC;
#ifdef TWLSDK
    raUnlockService();CHECK(sharedAddr[RA_SHARED_UNLOCK_REQ]==RA_SHARED_UNLOCK_MAGIC);
    raUnlockSlot=1;failWrite=calls+1;
    raUnlockService();CHECK(sharedAddr[RA_SHARED_UNLOCK_REQ]==RA_SHARED_UNLOCK_MAGIC);
    failWrite=0;raUnlockService();CHECK(!sharedAddr[RA_SHARED_UNLOCK_REQ]);
#else
    raUnlockService();CHECK(!sharedAddr[RA_SHARED_UNLOCK_REQ]); CHECK(raUnlockPendingCount==1);
    raUnlockDrain();CHECK(raUnlockPendingCount==1); /* full disk queue */
    raUnlockSlot=1;raUnlockPending[0]=230047|RA_UNLOCK_HARDCORE_BIT;
    raUnlockPending[1]=230048;raUnlockPending[2]=230049;raUnlockPendingCount=3;
    failWrite=calls+2;raUnlockDrain();
    CHECK(raUnlockPendingCount==2);CHECK(raUnlockPending[0]==230048);CHECK(raUnlockPending[1]==230049);
    CHECK(raUnlockSlot==2); failWrite=0;raUnlockDrain();CHECK(!raUnlockPendingCount);CHECK(raUnlockSlot==4);
    /* Full RAM buffer backpressures, drain then acknowledge exactly once. */
    raUnlockPendingCount=RA_UNLOCK_PENDING_MAX;sharedAddr[RA_SHARED_UNLOCK_REQ]=RA_SHARED_UNLOCK_MAGIC;
    raUnlockService();CHECK(sharedAddr[RA_SHARED_UNLOCK_REQ]==RA_SHARED_UNLOCK_MAGIC);
    raUnlockPendingCount=0;raUnlockService();CHECK(!sharedAddr[RA_SHARED_UNLOCK_REQ]);
#endif
    CHECK(critical==0);puts("PASSED ARM7 production queue functions");return 0;
}
'''
with tempfile.TemporaryDirectory(prefix='ra-unlock-') as tmp:
    tmp=pathlib.Path(tmp); (tmp/'nds').mkdir()
    (tmp/'nds/ndstypes.h').write_text('#include <stdint.h>\n#include <stdbool.h>\ntypedef uint8_t u8;typedef uint16_t u16;typedef uint32_t u32;typedef int32_t s32;typedef int16_t s16;typedef int8_t s8;')
    (tmp/'test.c').write_text(prelude+append+service+main)
    for flags in ([],['-DTWLSDK']):
        subprocess.run([os.environ.get('CC','cc'),'-std=gnu99','-O1','-I'+str(tmp),'-I'+str(root/'retail/common/include'),*flags,str(tmp/'test.c'),'-o',str(tmp/'test')],check=True)
        subprocess.run([str(tmp/'test')],check=True)
