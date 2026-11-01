#!/usr/bin/env python3
"""Run the actual app's controls/compositor against modeled libctru backbuffers.

Pixels outside the two footer rectangles and active popup must match the fresh
source on every frame. This is host QA, never console timing/API certification.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]

HEADER = r'''
#include <stdint.h>
#include <stdbool.h>
typedef uint8_t u8;typedef uint16_t u16;typedef uint32_t u32;typedef uint64_t u64;
typedef int32_t Result;typedef int gfxScreen_t;typedef int APT_HookType;
typedef struct {int dummy;} aptHookCookie;
typedef struct {u32 base_addr,size,perm,state;} MemInfo;
typedef struct {u32 flags;} PageInfo;
#define GFX_TOP 0
#define GFX_BOTTOM 1
#define GFX_LEFT 0
#define GSP_BGR8_OES 1
#define SYSCLOCK_ARM11 268123480u
#define APTHOOK_ONSUSPEND 0
#define KEY_A 1
#define KEY_B 2
#define KEY_X 4
#define KEY_START 8
#define R_SUCCEEDED(r) ((r)>=0)
#define R_FAILED(r) ((r)<0)
#define MEMPERM_WRITE 2
#define MEMPERM_READWRITE 3
void osSetSpeedupEnable(bool);void gfxInit(int,int,bool);void gfxSet3D(bool);
void gfxSetWide(bool);void gfxExit(void);void gfxFlushBuffers(void);
void gfxSwapBuffers(void);void gspWaitForVBlank(void);void consoleInit(int,void*);
bool aptMainLoop(void);void hidScanInput(void);u32 hidKeysDown(void);
u64 svcGetSystemTick(void);u8 *gfxGetFramebuffer(int,int,u16*,u16*);
void aptHook(aptHookCookie*,void (*)(int,void*),void*);void aptUnhook(aptHookCookie*);
Result cfguInit(void);Result CFGU_GetSystemModel(u8*);void cfguExit(void);
Result svcQueryMemory(MemInfo*,PageInfo*,u32);
'''

STUBS = r'''
#include "3ds.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
static u8 *buffers[2][2],*assets;
static unsigned next_buffer,display_buffer,frame,checks;
static u64 tick;
static bool deny,in_error;
static size_t length(int screen){return (screen==GFX_TOP?400u:320u)*240u*3u;}
void osSetSpeedupEnable(bool enabled){assert(!enabled);}
void gfxInit(int top,int bottom,bool vram){
 assert(top==GSP_BGR8_OES && bottom==GSP_BGR8_OES && !vram);
 deny=getenv("RA_MODEL_DENY_FB")!=NULL;
 for(int s=0;s<2;++s)for(int b=0;b<2;++b){
  buffers[s][b]=mmap(NULL,length(s)+32,PROT_READ|PROT_WRITE,
                    MAP_PRIVATE|MAP_ANONYMOUS|MAP_32BIT,-1,0);
  assert(buffers[s][b]!=MAP_FAILED && (uintptr_t)buffers[s][b]<=UINT32_MAX);
  memset(buffers[s][b],0xa5,length(s)+32);
  if(deny)assert(!mprotect(buffers[s][b],length(s)+32,PROT_READ));
 }
 FILE *f=fopen(APP_ROOT "/frames.bin","rb");assert(f);
 assert(!fseek(f,0,SEEK_END));long n=ftell(f);assert(n>32);rewind(f);
 assets=malloc((size_t)n);assert(assets);assert(fread(assets,1,n,f)==(size_t)n);fclose(f);
}
void gfxSet3D(bool enable){assert(!enable);}void gfxSetWide(bool enable){assert(!enable);}
void gfxFlushBuffers(void){}void gfxSwapBuffers(void){display_buffer=next_buffer;next_buffer^=1;}
void gspWaitForVBlank(void){
 unsigned image=(frame/90)%4;
 bool active=frame<180 || (frame>=200 && frame<240) || (frame>=250 && frame<430);
 unsigned panel=frame<230?GFX_BOTTOM:GFX_TOP;
 for(unsigned s=0;s<2;++s){
  unsigned width=s==GFX_TOP?400:320,changed=0;
  u8 *actual=buffers[s][display_buffer]+16;
  const u8 *source=assets+32+image*(400*240+320*240)*3+(s==GFX_BOTTOM?400*240*3:0);
  for(unsigned x=0;x<width;++x)for(unsigned y=0;y<240;++y){
   bool horizontal=x>=(width-256)/2 && x<(width-256)/2+256;
   bool footer=horizontal && y>=220 && y<236;
   bool popup=active && s==panel && horizontal && y>=12 && y<28;
   size_t i=(x*240+239-y)*3;
   if(memcmp(actual+i,source+i,3)){
    assert(footer||popup);if(popup)++changed;
   }
  }
  if(active && s==panel)assert(changed>0);
  for(unsigned i=0;i<16;++i){assert(buffers[s][display_buffer][i]==0xa5);assert(actual[length(s)+i]==0xa5);}
  ++checks;
 }
 ++frame;tick+=4468725;
}
void consoleInit(int screen,void *x){(void)screen;(void)x;assert(deny);in_error=true;}
bool aptMainLoop(void){assert(frame<=450);return true;}void hidScanInput(void){}
u32 hidKeysDown(void){
 if(deny && in_error)return KEY_START;
 if(frame==200 || frame==250)return KEY_A;
 if(frame==230)return KEY_X;
 if(frame==240)return KEY_B;
 return frame==450?KEY_START:0;
}
u64 svcGetSystemTick(void){return tick+=100;}
u8 *gfxGetFramebuffer(int screen,int side,u16 *w,u16 *h){
 assert(side==GFX_LEFT);*w=240;*h=screen==GFX_TOP?400:320;
 return buffers[screen][next_buffer]+16;
}
void aptHook(aptHookCookie *c,void (*f)(int,void*),void *p){(void)c;(void)f;(void)p;}
void aptUnhook(aptHookCookie *c){(void)c;}
Result svcQueryMemory(MemInfo *info,PageInfo *page,u32 address){
 (void)page;
 for(int s=0;s<2;++s)for(int b=0;b<2;++b){
  uintptr_t start=(uintptr_t)buffers[s][b];
  if(address>=start && address-start<length(s)+32){
   info->base_addr=(u32)start;info->size=(u32)length(s)+32;
   info->perm=deny?1:3;return 0;
  }
 }
 return -1;
}
Result cfguInit(void){return 0;}Result CFGU_GetSystemModel(u8 *m){*m=5;return 0;}void cfguExit(void){}
void gfxExit(void){
 assert(deny?(frame==0 && checks==0):(frame==450 && checks==900));
 for(int s=0;s<2;++s)for(int b=0;b<2;++b)assert(!munmap(buffers[s][b],length(s)+32));
 free(assets);
 puts(deny?"Denied framebuffer path completed without writes":"450 modeled frames, 900 panel pixel/canary checks: PASS");
}
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('asset_file', type=Path)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='ra-arm11-app-test-') as temporary:
        directory = Path(temporary)
        (directory/'3ds.h').write_text(HEADER)
        (directory/'stubs.c').write_text(STUBS)
        (directory/'frames.bin').write_bytes(args.asset_file.read_bytes())
        flags = ['-std=gnu11', '-O1', '-g', '-Wall', '-Wextra', '-Werror',
                 '-fsanitize=address,undefined', '-I'+str(directory),
                 '-I'+str(ROOT/'tools/research/twlbg_postcompose'),
                 '-I'+str(ROOT/'retail/cardenginei/arm9_ra/include'),
                 '-I'+str(ROOT/'retail/common/include'),
                 '-I'+str(ROOT/'tools/research/tetris_gfx_order/research_include'),
                 '-DAPP_ROOT="'+str(directory)+'"']
        command = ['cc', *flags, str(HERE/'source/main.c'), str(directory/'stubs.c'),
                   str(ROOT/'tools/research/twlbg_postcompose/postcompose.c'),
                   str(ROOT/'retail/cardenginei/arm9_ra/source/ra_text.c'),
                   '-o', str(directory/'test')]
        subprocess.run(command, check=True)
        subprocess.run([str(directory/'test')], check=True,
                       env={**os.environ,'ASAN_OPTIONS':'detect_leaks=0'})
        report = json.loads((directory/'reports/000/report.json').read_text())
        assert report['frames'] == 450 and report['previews'] == 2 and report['panel_moves'] == 1
        assert report['manual_closes'] == 1 and report['render_error'] == 0
        assert [(e['drawn_frames'],e['end_reason']) for e in report['events']] == [
            (180,'expired'),(40,'manual'),(180,'expired')]
        assert (directory/'reports/000/top.bgr').stat().st_size == 400*240*3
        assert (directory/'reports/000/bottom.bgr').stat().st_size == 320*240*3
        assert report['memory_permission_checks'] == 4
        print('Actual app controls, event lifetimes, clean expiry and report: PASS (host model)')
        result = subprocess.run([str(directory/'test')],
                                env={**os.environ,'ASAN_OPTIONS':'detect_leaks=0','RA_MODEL_DENY_FB':'1'})
        assert result.returncode == 1
        rejected = json.loads((directory/'reports/001/report.json').read_text())
        assert rejected['frames'] == 0 and rejected['render_error'] == -4
        assert rejected['memory_permission_checks'] == 1
        print('Read-only protected framebuffer rejected before compositor writes: PASS')


if __name__ == '__main__':
    main()
