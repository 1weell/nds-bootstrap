/* Exercise production overlay admission without borrowing real game resources. */
#define _GNU_SOURCE
#include <stdio.h>
#include <string.h>
#include <sys/mman.h>
#include "ra_wifi.h"
#include "locations.h"
#include "../retail/cardenginei/arm9_ra/source/ra_overlay.c"
#define CHECK(x) do { if (!(x)) { fprintf(stderr,"FAIL popup %d: %s\n",__LINE__,#x); return 1; } } while(0)
int main(void) {
    raGfxReady = 1;
    CHECK(mmap((void*)0x04000000,0x2000,PROT_READ|PROT_WRITE,MAP_ANONYMOUS|MAP_PRIVATE|MAP_FIXED,-1,0)!=MAP_FAILED);
    CHECK(mmap((void*)0x0377f000,0x1000,PROT_READ|PROT_WRITE,MAP_ANONYMOUS|MAP_PRIVATE|MAP_FIXED,-1,0)!=MAP_FAILED);
    raSessionBlock* session=(raSessionBlock*)CARDENGINEI_ARM9_RA_SESSION_LOCATION;
    /* Unknown or disabled sessions never acquire graphics resources for a preview. */
    CHECK(ra_overlay_preview()==RA_POPUP_PREVIEW_DISABLED);
    session->magic=RA_SESSION_MAGIC;session->overlay=0;
    CHECK(ra_overlay_preview()==RA_POPUP_PREVIEW_DISABLED);
    session->overlay=1;
    CHECK(ra_overlay_preview()==RA_POPUP_PREVIEW_BUSY);
    ra_overlay_tick(2,NULL); /* initialize, synchronizing the real unlock counter */
    CHECK(lastUnlocks==2);
    CHECK(ra_overlay_preview()==RA_POPUP_PREVIEW_ACCEPTED);
    CHECK(pending==1 && lastUnlocks==2 && raOverlayShows==0);
    CHECK(ra_overlay_preview()==RA_POPUP_PREVIEW_BUSY);
    pending=0;
    CHECK(ra_overlay_startup()==RA_POPUP_PREVIEW_ACCEPTED && pendingStartup==1);
    /* Non-graphics display modes defer safely, without touching unmapped VRAM. */
    for(unsigned mode=0;mode<4;++mode) {
        SUB_DISPCNT=mode<<16;
        CHECK(screenHidden()==(mode!=1));
        if(mode!=1) { ra_overlay_tick(2,NULL);CHECK(pending==1 && raOverlayShows==0); }
    }
    SUB_DISPCNT=(1u<<16)|(1u<<7);CHECK(screenHidden());
    /* Preview never advanced the real counter; future unlock remains observable. */
    pending=0;SUB_DISPCNT=0;
    ra_overlay_tick(3,NULL);CHECK(lastUnlocks==3 && pending==1 && pendingStartup==0);
    session->overlay=0;pending=0;
    CHECK(ra_overlay_preview()==RA_POPUP_PREVIEW_DISABLED && pending==0);
    /* Foreground object coverage must not force a toast behind the top HUD. */
    CHECK(objDimensions(0,0)==0x0101);
    CHECK(objDimensions(1u<<14,2u<<14)==0x0204);
    CHECK(objDimensions(2u<<14,3u<<14)==0x0804);
    CHECK(objDimensions(3u<<14,0)==0x0808);
    u16 oam[128*4]={0};u16 original,selected;
    for(unsigned i=0;i<128;++i)oam[4*i]=0x200;
    CHECK(raOverlayChooseRow(oam,&original,&selected)==1 && !original && !selected);
    oam[0]=8|(1u<<14);oam[1]=3u<<14; /* 64x32, Y=8, priority zero */
    CHECK(raOverlayChooseRow(oam,&original,&selected)>=5 && original==1024 && selected==0);
    oam[2]=1u<<10;CHECK(raOverlayChooseRow(oam,&original,&selected)==1 && original==0);
    oam[2]=0;oam[0]=8|(1u<<14)|(2u<<10); /* object-window is not opaque colour */
    CHECK(raOverlayChooseRow(oam,&original,&selected)==1 && original==0);
    oam[0]=250|(1u<<14);oam[1]=500|(3u<<14);
    CHECK(raOverlayChooseRow(oam,&original,&selected)>=4 && original>0 && selected==0);
    for(unsigned i=0;i<128;++i)oam[4*i]=0x200;
    for(unsigned i=0;i<4;++i) {
        oam[4*i]=(i/2)*128|0x300; /* double-size affine 64x64 gives 128x128 box */
        oam[4*i+1]=(i%2)*128|(3u<<14);oam[4*i+2]=0;
    }
    CHECK(raOverlayChooseRow(oam,&original,&selected)==1 && original==4096 && selected==4096);
    /* A BG notification must not mistake its own BGCNT for a game claim. */
    CHECK(mmap((void*)0x05000000,0x1000,PROT_READ|PROT_WRITE,MAP_ANONYMOUS|MAP_PRIVATE|MAP_FIXED,-1,0)!=MAP_FAILED);
    CHECK(mmap((void*)0x06200000,0x20000,PROT_READ|PROT_WRITE,MAP_ANONYMOUS|MAP_PRIVATE|MAP_FIXED,-1,0)!=MAP_FAILED);
    CHECK(mmap((void*)0x07000000,0x1000,PROT_READ|PROT_WRITE,MAP_ANONYMOUS|MAP_PRIVATE|MAP_FIXED,-1,0)!=MAP_FAILED);
    for(unsigned i=0;i<OAM_ENTRIES;++i)SUB_OAM[i*4]=0x200;
    session->overlay=1;pending=0;pendingStartup=1;SUB_DISPCNT=0x10100;
    for(unsigned i=0;i<4;++i)SUB_BGCNT(i)=0;
    u32 strip[RA_TEXT_WORDS];
    for(unsigned i=0;i<RA_TEXT_WORDS;++i)strip[i]=1;
    for(unsigned i=0;i<8;++i)tilesOf(1)[i]=0xDEADBEEF;
    show(strip);
    CHECK(framesLeft==OVERLAY_SHOW_FRAMES && !usingSprites && raOverlayShows==1);
    for(unsigned i=0;i<8;++i)CHECK(tilesOf(block)[i]==0);
    bool used[CHAR_BLOCKS];
    surveyBlocks(used);CHECK(!used[block] && used[0]);
    /* A different layer still owns its allocation, even when disabled. */
    SUB_BGCNT(1)=bgCntFor(block);
    surveyBlocks(used);CHECK(used[block]);
    SUB_BGCNT(1)=0;
    /* A game replacement of our layer must be respected as well. */
    SUB_BGCNT(layer)=bgCntFor(block)|1;
    surveyBlocks(used);CHECK(used[block]);
    SUB_BGCNT(layer)=bgCntFor(block);
    for(unsigned i=0;i<OVERLAY_SHOW_FRAMES;++i)ra_overlay_tick(3,strip);
    CHECK(framesLeft==0 && raOverlayHeld==OVERLAY_SHOW_FRAMES && raOverlayEvicted==0);
    CHECK(SUB_BGCNT(layer)==0 && SUB_DISPCNT==0x10100);
    /* A real mid-notification claim still evicts on the next tick. */
    show(strip);SUB_BGCNT(1)=bgCntFor(block);
    ra_overlay_tick(3,strip);
    CHECK(framesLeft==0 && raOverlayEvicted==1);
    /* Captured gameplay state: occupied BGs must not be displaced. */
    CHECK(mmap((void*)0x06600000,0x4000,PROT_READ|PROT_WRITE,MAP_ANONYMOUS|MAP_PRIVATE|MAP_FIXED,-1,0)!=MAP_FAILED);
    pendingStartup=0;
    /* Admission must obey the same physical-bank rule as maintenance. An
     * unmapped address or two overlapping banks cannot be borrowed safely. */
    const u8 invalidBanks[][2]={{0,0},{0x84,0x82},{0x82,0x83}};
    u16 originalOam[OAM_ENTRIES*4], originalPalette[256];
    u32 originalObj[0x4000/4];
    memcpy(originalOam,(const void*)SUB_OAM,sizeof(originalOam));
    memcpy(originalPalette,(const void*)SUB_OBJ_PALETTE,sizeof(originalPalette));
    memcpy(originalObj,(const void*)SUB_OBJ_VRAM,sizeof(originalObj));
    SUB_DISPCNT=0xC0211F10;
    for(unsigned i=0;i<sizeof(invalidBanks)/sizeof(invalidBanks[0]);++i) {
        *(vu8*)0x04000243=invalidBanks[i][0];
        *(vu8*)0x04000249=invalidBanks[i][1];
        CHECK(!spriteShow(strip));
        CHECK(!usingSprites && !framesLeft);
        CHECK(!memcmp(originalOam,(const void*)SUB_OAM,sizeof(originalOam)));
        CHECK(!memcmp(originalPalette,(const void*)SUB_OBJ_PALETTE,sizeof(originalPalette)));
        CHECK(!memcmp(originalObj,(const void*)SUB_OBJ_VRAM,sizeof(originalObj)));
    }
    /* Bank I repeats its 16 KiB across the 128 KiB sub-OBJ address space.
     * A high logical tile can own one of the low slots we plan to borrow. */
    bool objUsed[OBJ_SLOTS];
    for(unsigned i=0;i<OAM_ENTRIES;++i)SUB_OAM[i*4+2]=0x40;
    *(vu8*)0x04000243=0x81;*(vu8*)0x04000249=0x82;
    SUB_OAM[2]=0x3c0; /* logical 0x7800 aliases physical 0x3800 */
    surveyObjVram(objUsed,32);CHECK(objUsed[7]);
    *(vu8*)0x04000243=0x84;*(vu8*)0x04000249=0;
    surveyObjVram(objUsed,32);CHECK(!objUsed[7]);
    /* A sprite spanning the physical end also owns the wrapped beginning. */
    *(vu8*)0x04000243=0x81;*(vu8*)0x04000249=0x82;
    SUB_OAM[1]=1u<<14;SUB_OAM[2]=0x1ff; /* 16x16 at 0x3fe0 */
    surveyObjVram(objUsed,32);CHECK(objUsed[7] && objUsed[0]);
    *(vu8*)0x04000243=0x84;*(vu8*)0x04000249=0;
    surveyObjVram(objUsed,32);CHECK(objUsed[7] && !objUsed[0]);
    /* Engine B also wraps tile addresses exceeding its 128 KiB space. */
    SUB_OAM[1]=0;SUB_OAM[2]=0x200;
    surveyObjVram(objUsed,256);CHECK(objUsed[0]);
    memcpy((void*)SUB_OAM,originalOam,sizeof(originalOam));
    *(vu8*)0x04000249=0;
    *(vu8*)0x04000243=0x84;
    SUB_DISPCNT=0xC0211F10;
    const u16 gameBg[4]={0x403,0x503,0x686,0x793};
    for(unsigned i=0;i<4;++i)SUB_BGCNT(i)=gameBg[i];
    for(unsigned i=0;i<8;++i)tilesOf(2)[i]=0xDEADBEEF;
    show(strip);
    CHECK(usingSprites && raOverlaySpriteOam!=0xFF);
    for(unsigned i=0;i<8;++i)CHECK(tilesOf(2)[i]==0xDEADBEEF);
    for(unsigned i=0;i<4;++i)CHECK(SUB_BGCNT(i)==gameBg[i]);
    for(unsigned i=0;i<OVERLAY_SHOW_FRAMES;++i)ra_overlay_tick(3,strip);
    CHECK(framesLeft==0 && raOverlayEvicted==1);
    for(unsigned i=0;i<4;++i)CHECK(SUB_BGCNT(i)==gameBg[i]);
    CHECK(SUB_DISPCNT==0xC0211F10);
    /* In every supported mode the selected BG must understand text maps. */
    for(unsigned mode=0;mode<=5;++mode) {
        SUB_DISPCNT=(0xC0211F10&~7u)|mode;
        for(unsigned i=0;i<4;++i)SUB_BGCNT(i)=3;
        CHECK(chooseLayer(true)>=0 && layerKind(mode,chooseLayer(true))==LAYER_TEXT);
        CHECK(chooseLayer(false)==-1);
    }
    /* Sprite fallback remains available only when all BG blocks are occupied. */
    /* Diagnostic samples surround real sprite writes and never change routing. */
    SUB_DISPCNT=0xC0211F10;
    for(unsigned i=0;i<4;++i)SUB_BGCNT(i)=i<<2;
    *(vu16*)0x04000006=200;*(vu16*)0x04000304=0x020F;
    show(strip);
    CHECK(usingSprites && raOverlayWriteLineMin==200 && raOverlayWriteLineMax==200);
    CHECK(raOverlayLateSamples==0 && raOverlayPanelFlips==0 && raOverlayPowerControl==0x020F);
    SUB_OAM[spriteOam[0]*4]=0x200; /* full disabled shadow entry from game */
    SUB_OAM[spriteOam[0]*4+1]=0;
    SUB_OAM[spriteOam[0]*4+2]=0;
    *(vu32*)(SUB_OBJ_VRAM+spriteBase)=0; /* existing tile probe detects a changed word */
    const u32 repairs=raOverlayRedrawn;
    *(vu16*)0x04000006=12;*(vu16*)0x04000304=0x820F;
    ra_overlay_tick(3,strip);
    CHECK(raOverlayWriteLineMin==12 && raOverlayWriteLineMax==200 && raOverlayLateSamples==2);
    CHECK(raOverlayObjClobbered==1 && raOverlayPanelFlips==1 && raOverlayPowerControl==0x820F);
    CHECK(*(vu16*)0x04000304==0x820F && raOverlayRedrawn==repairs+1);
    *(vu16*)0x04000006=250;
    ra_overlay_tick(3,strip);
    CHECK(raOverlayWriteLineMax==250 && raOverlayLateSamples==2);
    CHECK(raOverlayObjClobbered==1 && raOverlayPanelFlips==1);
    /* Upload refresh never advances the clock or generates a notification. */
    const u32 left = framesLeft, shows = raOverlayShows, unlocks = lastUnlocks;
    const u32 saved = *(vu32*)(SUB_OBJ_VRAM+spriteBase+120);
    *(vu32*)(SUB_OBJ_VRAM+spriteBase+120)=saved^0x10203040;
    ra_overlay_after_upload();
    CHECK(*(vu32*)(SUB_OBJ_VRAM+spriteBase+120)==saved);
    CHECK(framesLeft==left && raOverlayShows==shows && lastUnlocks==unlocks);
    /* A newly mapped physical bank needs the same strip, without another tick. */
    *(vu8*)0x04000243=0x81;*(vu8*)0x04000249=0x82;
    memset((void*)(SUB_OBJ_VRAM+spriteBase),0,2048);
    ra_overlay_after_upload();
    CHECK(framesLeft==left && *(vu32*)(SUB_OBJ_VRAM+spriteBase+120)==saved);
    /* Overlapping banks are transitional: absolutely no writes into either. */
    *(vu8*)0x04000243=0x84;
    *(vu32*)(SUB_OBJ_VRAM+spriteBase+120)=0x12345678;
    ra_overlay_after_upload();
    CHECK(*(vu32*)(SUB_OBJ_VRAM+spriteBase+120)==0x12345678 && framesLeft==left);
    *(vu8*)0x04000243=0x81;
    /* Fresh image readiness prevents stale BSS from drawing before startup. */
    raGfxReady=0;ra_overlay_after_upload();
    CHECK(*(vu32*)(SUB_OBJ_VRAM+spriteBase+120)==0x12345678);
    raGfxReady=1;ra_overlay_after_upload();
    /* Identical attr0 does not confer ownership: preserve reclaimed attr1/2. */
    const int reclaimed = spriteOam[0];
    SUB_OAM[reclaimed*4+1]=37;
    const u16 gameAttr0=SUB_OAM[reclaimed*4], gameAttr2=SUB_OAM[reclaimed*4+2];
    const u32 evictions=raOverlayEvicted;
    ra_overlay_after_upload();
    CHECK(framesLeft==0 && raOverlayEvicted==evictions+1);
    CHECK(SUB_OAM[reclaimed*4]==gameAttr0 && SUB_OAM[reclaimed*4+1]==37
          && SUB_OAM[reclaimed*4+2]==gameAttr2);
    puts("PASSED production popup: admission, BG lifetime, real resource reclamation");
    return 0;
}
