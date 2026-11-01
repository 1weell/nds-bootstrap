/* GPL-3.0. Events are copied at trigger time, including multiple triggers per tick. */
#include "ra_bridge9.h"
#include "ra_wifi.h"
#include "locations.h"

RaBridgeTx raBridgeSender;
RaBridgeStats raBridgeTelemetry;
u32 raBridgeTelemetryMagic;
static u32 bridgeSession,bridgeSequence;
static u8 bridgeReady,bridgeEnding,bridgeSharedInitialized;
static u8 telemetry[RA_BRIDGE_STATS_BYTES],telemetryIndex,telemetryPending;
static u16 telemetryWait;
static u32 telemetryNext;

static const raSessionBlock *session(void) {
    return (const raSessionBlock *)CARDENGINEI_ARM9_RA_SESSION_LOCATION;
}
int raBridge9Selected(void) {
    const raSessionBlock *s=session();
    return s->magic==RA_SESSION_MAGIC && s->bridgeMagic==RA_BRIDGE_EXTENSION && s->renderer==RA_RENDERER_ARM11;
}
static int ensure(void) {
    const raSessionBlock *s=session();
    if(!raBridge9Selected() || !s->overlay || !s->bridgeSession)return 0;
    if(bridgeSession!=s->bridgeSession) {
        memset(&raBridgeSender,0,sizeof(raBridgeSender));
        bridgeSession=s->bridgeSession;bridgeSequence=0;bridgeReady=0;bridgeEnding=0;bridgeSharedInitialized=0;
        raBridgeTelemetryMagic=0;telemetryIndex=telemetryPending=0;telemetryWait=0;telemetryNext=0;
        RaBridgeEvent e={0};e.type=RA_EVENT_BEGIN;e.flags=RA_EVENT_ENABLED;
        e.session=bridgeSession;e.sequence=++bridgeSequence;e.game_id=s->gameId;
        ra_bridge_enqueue(&raBridgeSender,&e);
    }
    return 1;
}
static int emit(u8 type,u32 id,const char *title) {
    if(!ensure())return 0;
    const raSessionBlock *s=session();
    RaBridgeEvent e={0};e.type=type;e.session=bridgeSession;e.sequence=bridgeSequence+1;
    e.game_id=s->gameId;e.achievement_id=id;e.flags=RA_EVENT_ENABLED|RA_EVENT_ACTIVE;
    if(s->hardcore)e.flags|=RA_EVENT_HARDCORE;
    if(s->startupState==RA_STARTUP_OFFLINE)e.flags|=RA_EVENT_OFFLINE;
    if(ra_bridge_text(e.title,sizeof(e.title),title))e.flags|=RA_EVENT_TRUNCATED;
    if(!ra_bridge_enqueue(&raBridgeSender,&e))return 0;
    bridgeSequence++;return 1;
}
void raBridge9Unlock(u32 id,const char *title) {
    if(!id || id>=RA_SYNTHETIC_ID_BASE)return;
    if(!bridgeEnding)emit(RA_EVENT_UNLOCK,id,title);
}
void raBridge9End(void) {
    if(!bridgeEnding && emit(RA_EVENT_END,0,""))bridgeEnding=1;
}
u8 raBridge9Preview(void) {
    if(!ensure())return RA_POPUP_PREVIEW_DISABLED;
    return emit(RA_EVENT_PREVIEW,0,"Nenhuma conquista concedida")?RA_POPUP_PREVIEW_ACCEPTED:RA_POPUP_PREVIEW_BUSY;
}

/* Diagnostic traffic yields immediately to real events. One bounded byte request
 * at a time, with an immutable CRC-protected snapshot from ARM11. */
static int telemetry_step(volatile u32 *word,u32 now) {
    if(telemetryPending) {
        u32 value=*word;
        if((value&RA_BRIDGE_TAG_MASK)==RA_BRIDGE_RESPONSE) {
            *word=0;telemetryPending=0;telemetryWait=0;
            if((u8)(value>>8)!=RA_RTC_STATS_ACK) {
                telemetryIndex=0;telemetryNext=now+300;return 0;
            }
            telemetry[telemetryIndex++]=(u8)value;
            if(telemetryIndex==sizeof(telemetry)) {
                if(ra_bridge_stats_unpack(&raBridgeTelemetry,telemetry)) {
                    raBridgeTelemetryMagic=RA_BRIDGE_STATS_MAGIC;
                }
                telemetryIndex=0;telemetryNext=now+300;return 0;
            }
        } else {
            if(++telemetryWait>120) {
                *word=0;telemetryPending=telemetryIndex=0;telemetryWait=0;
                telemetryNext=now+300;raBridgeSender.timeouts++;
            }
            return 1;
        }
    }
    if(raBridgeSender.count || !raBridgeSender.online || raBridgeSender.disabled)return 0;
    if(!telemetryIndex && (int32_t)(now-telemetryNext)<0)return 0;
    *word=RA_BRIDGE_REQUEST|((u32)RA_RTC_STATS<<8)|telemetryIndex;
    telemetryPending=1;return 1;
}
void raBridge9Tick(raSnapshot *snapshot) {
    if(!ensure())return;
    const raSessionBlock *s=session();
    if(!bridgeEnding && !bridgeReady && (s->startupState==RA_STARTUP_CONFIRMED || s->startupState==RA_STARTUP_OFFLINE)
       && (snapshot->rcStage==RA_RC_ACTIVE || snapshot->rcStage==RA_RC_FRAME)) {
        const char *name=s->displayTitle[0]?s->displayTitle:s->gameTitle;
        if(emit(RA_EVENT_READY,0,name))bridgeReady=1;
    }
    if(snapshot->shared==CARDENGINE_SHARED_ADDRESS_SDK1 || snapshot->shared==CARDENGINE_SHARED_ADDRESS_SDK5) {
        volatile u32 *shared=(volatile u32*)snapshot->shared;
        if(!bridgeSharedInitialized) {
            /* This is our reserved slot; stale RAM is not an in-flight request. */
            shared[RA_BRIDGE_SHARED_SLOT]=0;bridgeSharedInitialized=1;
        }
        /* Best effort. Next SESSION_BEGIN also clears old state if exit stops IRQs first. */
        if(shared[3]==0x54495845u || shared[3]==0x52534554u)raBridge9End();
        if(!raCardReadPending(shared[3]) && !telemetry_step(&shared[RA_BRIDGE_SHARED_SLOT],snapshot->ticks))
            ra_bridge_transmit(&raBridgeSender,&shared[RA_BRIDGE_SHARED_SLOT]);
    }
}
