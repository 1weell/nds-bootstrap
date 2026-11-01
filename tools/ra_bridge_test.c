/* GPL-3.0. End-to-end notification semantics using production producer/parser/protocol. */
#define _GNU_SOURCE
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/mman.h>
#include <unistd.h>
#include "ra_wifi.h"
#include "locations.h"
#include "ra_metadata.h"
#include "ra_bridge9.h"
#include "notify.h"

static void parser(void) {
    const char *json="{\"PatchData\" : {\"ID\":42,\"Title\":\"Kirby: Squeak Squad\",\"Achievements\":["
        "{\"ID\":1,\"Title\":\"Caf\\u00e9 \\ud83c\\udfc6\\tFirst \\\"Star\\\"\",\"MemAddr\":\"0xH1=1\",\"Flags\":3},"
        "{\"ID\":2,\"MemAddr\":\"0xH2=1\",\"Flags\":3}]}}";
    char expected[]="1:0xH1=1\tCaf\xc3\xa9 \xf0\x9f\x8f\x86 First \"Star\"\n2:0xH2=1\n";
    for(size_t split=0;split<=strlen(json);split++) {
        raPatch p;char block[1024];raPatchReset(&p,block,sizeof(block)-1);
        raPatchFeed(&p,json,(int)split);raPatchFeed(&p,json+split,(int)(strlen(json)-split));raPatchFinish(&p);
        assert(!strcmp(p.gameTitle,"Kirby: Squeak Squad"));assert(!strcmp(block,expected));
        assert(p.kept==2 && p.withId==2);
    }
    char long_title[90];memset(long_title,'x',sizeof(long_title)-1);long_title[89]=0;
    char document[512];snprintf(document,sizeof(document),"{\"Achievements\":[{\"ID\":1,\"Title\":\"%s\",\"MemAddr\":\"0xH1=1\",\"Flags\":3}]}",long_title);
    raPatch p;char block[512];raPatchReset(&p,block,sizeof(block)-1);
    for(size_t i=0;i<strlen(document);i++)raPatchFeed(&p,document+i,1);
    raPatchFinish(&p);assert(strstr(block,long_title));assert(!p.titleCut);
}
static void cache(void) {
    const char *hash="0123456789abcdef0123456789abcdef";
    char directory[]="/tmp/ra-title-cache-XXXXXX";assert(mkdtemp(directory));
    char path[160],title[RA_BRIDGE_TEXT];snprintf(path,sizeof(path),"%s/title.meta",directory);
    assert(raMetadataSave(path,hash,42,1,"Kirby: Squeak Squad"));
    assert(raMetadataLoad(path,hash,42,title) && !strcmp(title,"Kirby: Squeak Squad"));
    assert(!raMetadataLoad(path,hash,43,title));
    assert(!raMetadataLoad(path,"1123456789abcdef0123456789abcdef",42,title));
    assert(raMetadataSave(path,hash,42,2,"Kirby: Squeak Squad (Updated)"));
    FILE *f=fopen(path,"wb");assert(f);fputs("partial",f);assert(!fclose(f));
    assert(raMetadataLoad(path,hash,42,title) && !strcmp(title,"Kirby: Squeak Squad"));
    assert(raMetadataSave(path,hash,42,3,"Recovered title"));
    assert(raMetadataLoad(path,hash,42,title) && !strcmp(title,"Recovered title"));
    unlink(path);char backup[170];snprintf(backup,sizeof(backup),"%s.bak",path);unlink(backup);
    snprintf(backup,sizeof(backup),"%s.bad",path);unlink(backup);rmdir(directory);
}
static void protocol(void) {
    RaBridgeEvent e={0},decoded;e.session=7;e.sequence=1;e.type=RA_EVENT_BEGIN;e.flags=RA_EVENT_ENABLED;
    uint8_t wire[RA_BRIDGE_WIRE_MAX];size_t size=ra_bridge_encode(wire,&e);assert(size);
    assert(ra_bridge_decode(&decoded,wire,size));
    for(size_t i=0;i<size;i++){wire[i]^=1;assert(!ra_bridge_decode(&decoded,wire,size));wire[i]^=1;}
    char cut[4];assert(ra_bridge_text(cut,sizeof(cut),"ab\xc3\xa9"));assert(!strcmp(cut,"ab"));
    RaNotify n={0};assert(ra_notify_accept(&n,&e)==1);
    e.type=RA_EVENT_UNLOCK;e.sequence=2;e.achievement_id=10;strcpy(e.title,"Spark");
    assert(ra_notify_accept(&n,&e)==1);assert(ra_notify_accept(&n,&e)==1);assert(n.duplicates==1);
    e.sequence=3;e.achievement_id=11;strcpy(e.title,"Fire");assert(ra_notify_accept(&n,&e)==1);
    ra_notify_tick(&n,100);assert(!strcmp(n.current.title,"Spark"));
    ra_notify_tick(&n,RA_TICKS_SECOND*4+100);assert(!strcmp(n.current.title,"Fire"));
    e.sequence=4;e.achievement_id=12;assert(ra_notify_accept(&n,&e)==1); /* equal title, distinct ID */
    e.type=RA_EVENT_BEGIN;e.session=8;e.sequence=1;assert(ra_notify_accept(&n,&e)==1);
    assert(!n.active && !n.count);e.session=7;e.sequence=5;e.type=RA_EVENT_UNLOCK;assert(ra_notify_accept(&n,&e)==-1);
    RaBridgeTx absent={0};volatile uint32_t word=0;e.session=9;e.sequence=1;e.type=RA_EVENT_BEGIN;
    assert(ra_bridge_enqueue(&absent,&e));for(unsigned i=0;i<400;i++)ra_bridge_transmit(&absent,&word);
    assert(absent.disabled && absent.timeouts==3 && absent.count==1);
    RaBridgeTx full={0};for(unsigned i=0;i<RA_BRIDGE_QUEUE;i++)assert(ra_bridge_enqueue(&full,&e));
    assert(!ra_bridge_enqueue(&full,&e) && full.dropped==1);
    const char *utf="A\xc3\xa7\xc3\xa3o";assert(ra_display_char(&utf)=='A');assert(ra_display_char(&utf)=='c');assert(ra_display_char(&utf)=='a');
}
static void producer(void) {
    assert(mmap((void*)0x03740000,0x40000,PROT_READ|PROT_WRITE,MAP_ANONYMOUS|MAP_PRIVATE|MAP_FIXED,-1,0)!=MAP_FAILED);
    assert(mmap((void*)0x027ff000,0x1000,PROT_READ|PROT_WRITE,MAP_ANONYMOUS|MAP_PRIVATE|MAP_FIXED,-1,0)!=MAP_FAILED);
    raSessionBlock *s=(raSessionBlock*)CARDENGINEI_ARM9_RA_SESSION_LOCATION;
    s->magic=RA_SESSION_MAGIC;s->bridgeMagic=RA_BRIDGE_EXTENSION;s->bridgeSession=27;
    s->renderer=RA_RENDERER_ARM11;s->overlay=1;s->hardcore=1;s->gameId=42;
    s->startupState=RA_STARTUP_CONFIRMED;
    strcpy(s->displayTitle,"Kirby: Squeak Squad");
    raSnapshot snapshot={0};snapshot.shared=CARDENGINE_SHARED_ADDRESS_SDK1;snapshot.rcStage=RA_RC_ACTIVE;
    *(volatile uint32_t*)(snapshot.shared+RA_BRIDGE_SHARED_SLOT*4)=0xdeadbeef;
    raBridge9Tick(&snapshot);raBridge9Unlock(10,"Spark");raBridge9Unlock(11,"Fire");
    assert(raBridgeSender.count==4);
    volatile uint32_t *shared=(volatile uint32_t*)snapshot.shared;
    shared[9]=123;shared[10]=456;shared[11]=789;
    RaBridgeRx rx={0};RaNotify n={0};RaBridgeEvent event;int complete;unsigned accepted=0;
    /* The endpoint/producer are real. Serial timing/MMIO are deliberately a fixture. */
    uint8_t stats[RA_BRIDGE_STATS_BYTES]={0};
    RaBridgeStats sample={0};sample.format=0x301;sample.stride=720;sample.shown=3;sample.max_ticks=1000;
    sample.composited=180;sample.surfaces[3]=(RaBridgeSurface){0x1f345001,720,0x301,8};
    ra_bridge_stats_pack(stats,&sample);
    RaBridgeStats copy={0};assert(ra_bridge_stats_unpack(&copy,stats));assert(!memcmp(&copy,&sample,sizeof(copy)));
    for(size_t i=0;i<sizeof(stats);i++) {
        stats[i]^=1;assert(!ra_bridge_stats_unpack(&copy,stats));stats[i]^=1;
    }
    for(unsigned frame=0;frame<2000 && (raBridgeSender.count || !raBridgeTelemetryMagic);frame++) {
        snapshot.ticks=frame;
        raBridge9Tick(&snapshot);
        uint32_t request=shared[RA_BRIDGE_SHARED_SLOT];
        if((request&RA_BRIDGE_TAG_MASK)==RA_BRIDGE_REQUEST) {
            uint8_t command=(uint8_t)(request>>8);
            if(command==RA_RTC_STATS) {
                assert((uint8_t)request<sizeof(stats));
                shared[RA_BRIDGE_SHARED_SLOT]=RA_BRIDGE_RESPONSE|((uint32_t)RA_RTC_STATS_ACK<<8)|stats[(uint8_t)request];
                continue;
            }
            uint8_t ack=ra_bridge_receive_byte(&rx,command,(uint8_t)request,&event,&complete);
            if(complete){assert(ra_notify_accept(&n,&event)==1);accepted++;}
            shared[RA_BRIDGE_SHARED_SLOT]=RA_BRIDGE_RESPONSE|((uint32_t)ack<<8);
        }
    }
    assert(!raBridgeSender.count && raBridgeSender.sent==4 && accepted==4);
    assert(raBridgeTelemetryMagic==RA_BRIDGE_STATS_MAGIC && raBridgeTelemetry.format==0x301);
    assert(raBridgeTelemetry.stride==720 && raBridgeTelemetry.shown==3 && raBridgeTelemetry.max_ticks==1000);
    assert(raBridgeTelemetry.composited==180 && raBridgeTelemetry.surfaces[3].address==0x1f345001);
    assert(shared[9]==123 && shared[10]==456 && shared[11]==789);
    assert(n.count==3 && n.queue[0].type==RA_EVENT_READY);
    assert(!strcmp(n.queue[0].title,"Kirby: Squeak Squad"));
    assert(n.queue[1].achievement_id==10 && !strcmp(n.queue[1].title,"Spark"));
    assert(n.queue[2].achievement_id==11 && !strcmp(n.queue[2].title,"Fire"));
    assert(n.queue[2].flags&RA_EVENT_HARDCORE);
    s->overlay=0;unsigned count=raBridgeSender.count;raBridge9Unlock(12,"Disabled");assert(raBridgeSender.count==count);
}
int main(void) {
    parser();cache();protocol();producer();
    puts("PASSED bridge: UTF-8, canonical game scope, long titles, recoverable cache, CRC, ordered events, deduplication, timeout, policy and shared-slot isolation");
    return 0;
}
