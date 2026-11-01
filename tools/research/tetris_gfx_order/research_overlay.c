#include <stdint.h>
#include <sys/mman.h>
#include <stdio.h>
#include <stdlib.h>
#include "ra_wifi.h"
#include "locations.h"
#include "ra_overlay.h"
#include "ra_text.h"
#include "research_overlay_impl.c"
static const void* strip;
int ResearchRepairTiles;
void ResearchOverlayInit(void) {
 uintptr_t pages[][2]={{0x0377F000,0x1000},{0x04000000,0x3000},{0x05000000,0x1000},
 {0x06200000,0x20000},{0x06600000,0x20000},{0x07000000,0x1000}};
 for(unsigned i=0;i<sizeof(pages)/sizeof(*pages);i++)
  if(mmap((void*)pages[i][0],pages[i][1],PROT_READ|PROT_WRITE,MAP_PRIVATE|MAP_ANONYMOUS|MAP_FIXED,-1,0)==MAP_FAILED){perror("mmap");abort();}
 raSessionBlock* s=(raSessionBlock*)CARDENGINEI_ARM9_RA_SESSION_LOCATION;
 s->magic=RA_SESSION_MAGIC;s->overlay=1;
 strip=ra_text_render("POPUP TEST","No achievement awarded");
}
void ResearchOverlayTick(int first) {
 ra_overlay_tick(0,strip);
 if(first)fprintf(stderr,"preview admission %u\n",first==2?ra_overlay_startup():ra_overlay_preview());
}
/* Phase prototype: refresh only, never advances the VBlank lifetime clock. */
void ResearchOverlayRefresh(void) {
 if(stateMagic!=STATE_MAGIC||!framesLeft||!usingSprites)return;
 const u32 d=SUB_DISPCNT;
 if(screenHidden()||!(d&(1u<<4))||!(d&(1u<<12)))return;
 const u32 boundary=32u<<((d>>20)&3);
 bool used[OBJ_SLOTS];
 for(unsigned k=0;k<RA_SPRITES;k++) {
  u16 a=SUB_OAM[spriteOam[k]*4];
  if((a&0x300)!=0x200 && a!=(u16)((raOverlayRow*8)|(1<<14))) {
   raOverlayEvicted++;framesLeft=0;shownText=0;usingSprites=0;return;
  }
 }
 surveyObjVram(used,boundary);
 if(used[spriteSlot]) { raOverlayEvicted++;framesLeft=0;shownText=0;usingSprites=0;return; }
 if(ResearchRepairTiles) {
  unsigned banks=(*(volatile unsigned char*)0x04000243==0x84)+(*(volatile unsigned char*)0x04000249==0x82);
  if(banks!=1)return;
  if(shownText)spriteBlit(spriteBase,shownText);
 }
 spriteTile=spriteBase/boundary;
 SUB_OBJ_PALETTE[OBJ_PAL_ENTRY]=OVERLAY_INK_COLOUR;
 SUB_OBJ_PALETTE[OBJ_PAL_SHADOW]=OVERLAY_SHADOW_COLOUR;
 for(unsigned k=0;k<RA_SPRITES;k++)spriteWrite(k,spriteTile+k*RA_SPRITE_BYTES/boundary);
}
