/* Host adapter only: production C has zero emulated CPU cost. */
#include <stdint.h>
#include <sys/mman.h>
#include <stdio.h>
#include <stdlib.h>
#include "ra_wifi.h"
#include "locations.h"
#include "ra_text.h"
#include RA_OVERLAY_SOURCE

static const void* strip;
unsigned ResearchAdmissionFlags, ResearchDisabledOam, ResearchUsedSlots;
void ResearchOverlayInit(void) {
    const uintptr_t pages[][2]={{0x0377F000,0x1000},{0x04000000,0x3000},
        {0x05000000,0x1000},{0x06200000,0x20000},{0x06600000,0x4000},{0x07000000,0x1000}};
    for(unsigned i=0;i<sizeof(pages)/sizeof(*pages);++i)
        if(mmap((void*)pages[i][0],pages[i][1],PROT_READ|PROT_WRITE,
            MAP_PRIVATE|MAP_ANONYMOUS|MAP_FIXED,-1,0)==MAP_FAILED){perror("mmap");abort();}
    raSessionBlock* s=(raSessionBlock*)CARDENGINEI_ARM9_RA_SESSION_LOCATION;
    s->magic=RA_SESSION_MAGIC;s->overlay=1;
    strip=ra_text_render("RETROACHIEVEMENTS","Ready: Mario Kart DS");
}
void ResearchOverlayTick(int request) {
    u8 entries[RA_SPRITES];
    bool used[OBJ_SLOTS];
    unsigned flags=0;
    if(SUB_DISPCNT&(1u<<12))flags|=1;
    if(SUB_DISPCNT&(1u<<4))flags|=2;
    if(((*(vu8*)0x04000243==0x84)+(*(vu8*)0x04000249==0x82))==1)flags|=4;
    ResearchDisabledOam=0;
    for(unsigned i=0;i<OAM_ENTRIES;++i)
        if((SUB_OAM[4*i]&0x300)==0x200)++ResearchDisabledOam;
    if(chooseSprites(entries)==RA_SPRITES)flags|=8;
    surveyObjVram(used,32u<<((SUB_DISPCNT>>20)&3));
    ResearchUsedSlots=0;
    for(unsigned i=0;i<OBJ_SLOTS;++i) {
        if(used[i])ResearchUsedSlots|=1u<<i;else flags|=16;
    }
    ResearchAdmissionFlags=flags;
    ra_overlay_tick(0,strip);
    raGfxReady=1;
    if(request) {
        unsigned result=request==1?ra_overlay_startup():ra_overlay_preview();
        fprintf(stderr,"request %d admission %u\n",request,result);
        if(result==RA_POPUP_PREVIEW_ACCEPTED)
            strip=ra_text_render(request==1?"RETROACHIEVEMENTS":"POPUP TEST",
                request==1?"Ready: Mario Kart DS":"No achievement awarded");
    }
}
unsigned ResearchFramesLeft(void) { return framesLeft; }
unsigned ResearchSprites(void) { return usingSprites; }
unsigned ResearchLayer(void) { return layer; }
void ResearchOverlayRefresh(void) { ra_overlay_after_upload(); }
unsigned ResearchOwnedObjects(void) {
    unsigned n=0;
    if(usingSprites&&framesLeft)for(int k=0;k<RA_SPRITES;++k)if(spriteOwn(k))++n;
    return n;
}
