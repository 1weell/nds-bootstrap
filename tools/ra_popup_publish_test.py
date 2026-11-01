#!/usr/bin/env python3
"""Production welcome/preview publisher with a controlled graphics admission port."""
from pathlib import Path
import os, subprocess, tempfile
root=Path(__file__).resolve().parent.parent
source=(root/'retail/cardenginei/arm9_ra/source/cardengine.c').read_text()
a=source.index('static u8 startupQueued;');b=source.index('\nvoid ra_wram_tick(',a)
pre=r'''
#define _GNU_SOURCE
#include <stdio.h>
#include <string.h>
#include <sys/mman.h>
#include "ra_wifi.h"
#include "locations.h"
static RaBridgeTx raBridgeSender;
static RaBridgeStats raBridgeTelemetry;
static u32 raBridgeTelemetryMagic;
static int raBridge9Selected(void) { return 0; }
static void raBridge9Tick(raSnapshot* snapshot) { (void)snapshot; }
static u8 raBridge9Preview(void) { return RA_POPUP_PREVIEW_DISABLED; }
static int admission, calls, welcomes, previews, stateSeen;
u8 raOverlayRow;
u16 raOverlayCovered, raOverlayOriginalCovered;
/* Owned by ra_overlay.c in the real link; defined here because only the publisher is
 * extracted. Their values are asserted through v->popup below. */
u16 raOverlayStripWords, raOverlayHeld;
u16 raOverlayPowerControl, raOverlayPanelFlips;
u16 raOverlayWriteLineMin, raOverlayWriteLineMax, raOverlayLateSamples;
u16 raOverlayObjClobbered;
static u8 ra_overlay_preview(void) {
    ++calls;int result=admission;
    if(result==RA_POPUP_PREVIEW_ACCEPTED)admission=RA_POPUP_PREVIEW_BUSY;
    return result;
}
static void ra_rc_preview_text(void) { ++previews; }
static u8 ra_overlay_startup(void) { return ra_overlay_preview(); }
static void ra_rc_startup_text(u8 state,const char* title) { stateSeen=state;++welcomes;(void)title; }
'''
main=r'''
#define CHECK(x) do { if(!(x)) { fprintf(stderr,"FAIL popup publisher: %s\n",#x);return 1; } } while(0)
int main(void) {
 CHECK(mmap((void*)0x04000000,0x2000,PROT_READ|PROT_WRITE,MAP_ANONYMOUS|MAP_PRIVATE|MAP_FIXED,-1,0)!=MAP_FAILED);
 CHECK(mmap((void*)0x0377e000,0x2000,PROT_READ|PROT_WRITE,MAP_ANONYMOUS|MAP_PRIVATE|MAP_FIXED,-1,0)!=MAP_FAILED);
 raViewerBlock* v=(raViewerBlock*)CARDENGINEI_ARM9_RA_VIEWER_LOCATION;
 raSessionBlock* s=(raSessionBlock*)CARDENGINEI_ARM9_RA_SESSION_LOCATION;
 raSnapshot snapshot={0};snapshot.rcTriggered=7;
 v->magic=RA_VIEWER_MAGIC;s->magic=RA_SESSION_MAGIC;s->overlay=1;
 s->startupMagic=RA_STARTUP_MAGIC;s->startupState=RA_STARTUP_CONFIRMED;
 admission=RA_POPUP_PREVIEW_ACCEPTED;
 snapshot.rcStage=RA_RC_LOADING;ra_popup_publish(&snapshot);CHECK(calls==0);
 snapshot.rcStage=RA_RC_FRAME;ra_popup_publish(&snapshot);
 CHECK(startupHandled && startupQueued && welcomes==1 && stateSeen==RA_STARTUP_CONFIRMED);
 ra_popup_publish(&snapshot);CHECK(welcomes==1 && calls==1);
 startupHandled=startupQueued=0;admission=RA_POPUP_PREVIEW_BUSY;
 ra_popup_publish(&snapshot);CHECK(!startupHandled && welcomes==1);
 admission=RA_POPUP_PREVIEW_ACCEPTED;s->startupState=RA_STARTUP_OFFLINE;
 ra_popup_publish(&snapshot);CHECK(startupQueued && welcomes==2 && stateSeen==RA_STARTUP_OFFLINE);
 startupHandled=startupQueued=0;admission=RA_POPUP_PREVIEW_DISABLED;
 ra_popup_publish(&snapshot);CHECK(startupHandled && !startupQueued && welcomes==2);
 startupHandled=startupQueued=0;s->startupMagic=0;calls=0;
 ra_popup_publish(&snapshot);CHECK(calls==0 && !startupHandled);
 s->startupMagic=RA_STARTUP_MAGIC;s->startupState=RA_STARTUP_NONE;
 ra_popup_publish(&snapshot);CHECK(calls==0);
 s->startupState=RA_STARTUP_CONFIRMED;admission=RA_POPUP_PREVIEW_ACCEPTED;
 v->popup.preview=RA_POPUP_PREVIEW_REQUEST;ra_popup_publish(&snapshot);
 CHECK(previews==1 && !startupHandled && v->popup.preview==RA_POPUP_PREVIEW_ACCEPTED);
 CHECK(snapshot.rcTriggered==7); /* graphics requests cannot invent runtime events */
 CHECK(v->popup.magic==RA_POPUP_DIAG_MAGIC && v->popup.allowed==1);
 /* Published from the overlay's globals, so the reader sees the real values. */
 raOverlayStripWords=17;raOverlayHeld=42;ra_popup_publish(&snapshot);
 CHECK(v->popup.stripWords==17 && v->popup.heldFrames==42);
 raOverlayPowerControl=0x820F;raOverlayPanelFlips=3;
 raOverlayWriteLineMin=12;raOverlayWriteLineMax=260;raOverlayLateSamples=4;
 raOverlayObjClobbered=9;snapshot.overlayRedrawn=7;ra_popup_publish(&snapshot);
 CHECK(v->popup.powerControl==0x820F && v->popup.panelFlips==3);
 CHECK(v->popup.writeLineMin==12 && v->popup.writeLineMax==260 && v->popup.lateSamples==4);
 CHECK(v->popup.objClobbered==9 && v->popup.tileRepairs==7);
 puts("PASSED production popup publisher: startup once, retry, offline, disabled, preview priority");
 return 0;
}
'''
with tempfile.TemporaryDirectory(prefix='ra-publish-') as directory:
 p=Path(directory);(p/'nds').mkdir()
 (p/'nds/ndstypes.h').write_text('#include <stdint.h>\n#include <stdbool.h>\ntypedef uint8_t u8;typedef uint16_t u16;typedef uint32_t u32;typedef int32_t s32;typedef int16_t s16;typedef int8_t s8;typedef volatile uint8_t vu8;typedef volatile uint16_t vu16;typedef volatile uint32_t vu32;')
 (p/'test.c').write_text(pre+source[a:b]+main)
 subprocess.run([os.environ.get('CC','cc'),'-std=gnu99','-O1','-Wno-int-to-pointer-cast','-I'+str(p),'-I'+str(root/'retail/common/include'),str(p/'test.c'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True)
