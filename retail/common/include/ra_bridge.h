/* GPL-3.0. Bounded RA notification wire format. No pointers cross a CPU boundary. */
#ifndef RA_BRIDGE_H
#define RA_BRIDGE_H
#include <stdint.h>
#include <stddef.h>
#include <string.h>

#define RA_BRIDGE_VERSION 1
#define RA_BRIDGE_TEXT 96
#define RA_BRIDGE_QUEUE 8
#define RA_BRIDGE_HEADER 24
#define RA_BRIDGE_WIRE_MAX (RA_BRIDGE_HEADER + RA_BRIDGE_TEXT + 1)
#define RA_BRIDGE_SHARED_SLOT 12
#define RA_BRIDGE_REQUEST 0x52410000u
#define RA_BRIDGE_RESPONSE 0x52420000u
#define RA_BRIDGE_TAG_MASK 0xffff0000u
#define RA_RENDERER_LEGACY 0
#define RA_RENDERER_ARM11 1
#define RA_BRIDGE_EXTENSION 0x31425241u
#define RA_BRIDGE_STATS_MAGIC 0x32545341u /* AST2 */
typedef struct {
    uint32_t address, stride, format, count_reason;
} RaBridgeSurface;
typedef struct {
    uint32_t format, stride, shown, rejected, cache_errors, max_ticks;
    uint32_t bottom_calls, composited, rejected_format, rejected_address;
    uint32_t allocation_errors, no_free_buffer, pool_base, last_source, last_output;
    uint32_t last_index, last_select, mode, surface_changes, gpu_busy, active_rejected;
    RaBridgeSurface surfaces[4];
    uint32_t composite_max_ticks, composite_bins[8], composite_total_low, composite_total_high;
} RaBridgeStats;
#define RA_BRIDGE_STATS_BYTES (sizeof(RaBridgeStats) + 6)
typedef char ra_bridge_stats_byte_index_check[
    sizeof(RaBridgeStats)==192 && RA_BRIDGE_STATS_BYTES<256 ? 1 : -1];

enum { RA_EVENT_BEGIN=1, RA_EVENT_READY, RA_EVENT_UNLOCK, RA_EVENT_PREVIEW, RA_EVENT_END };
enum { RA_EVENT_HARDCORE=1, RA_EVENT_OFFLINE=2, RA_EVENT_ENABLED=4,
       RA_EVENT_ACTIVE=8, RA_EVENT_TRUNCATED=16 };
enum { RA_RTC_HELLO=0x50, RA_RTC_START, RA_RTC_BYTE0, RA_RTC_BYTE1,
       RA_RTC_COMMIT, RA_RTC_RESET, RA_RTC_PING, RA_RTC_STATS };
enum { RA_RTC_HELLO_ACK=0xc7, RA_RTC_START_ACK=0xc8, RA_RTC_COMMIT_ACK=0xca,
       RA_RTC_BAD=0xcb, RA_RTC_BUSY=0xcc, RA_RTC_PING_ACK=0xcd, RA_RTC_STATS_ACK=0xce,
       RA_RTC_BYTE0_ACK=0xd0, RA_RTC_BYTE1_ACK=0xd1 };

typedef struct {
    uint32_t session, sequence, game_id, achievement_id;
    uint8_t type, flags;
    char title[RA_BRIDGE_TEXT];
} RaBridgeEvent;

static inline uint16_t ra_bridge_crc(const uint8_t *p, size_t n) {
    uint16_t c=0xffff;
    while (n--) { c^=(uint16_t)*p++ << 8;
        for (unsigned i=0;i<8;i++) c=(uint16_t)((c<<1)^((c&0x8000)?0x1021:0)); }
    return c;
}
static inline void ra_bridge_put32(uint8_t *p,uint32_t v) {
    for(unsigned i=0;i<4;i++) p[i]=(uint8_t)(v>>(8*i));
}
static inline uint32_t ra_bridge_get32(const uint8_t *p) {
    return (uint32_t)p[0]|((uint32_t)p[1]<<8)|((uint32_t)p[2]<<16)|((uint32_t)p[3]<<24);
}
/* Explicit little-endian words, including the fixed-size surface table. CRC
 * covers the complete immutable snapshot, never a partially updated record. */
static inline void ra_bridge_stats_pack(uint8_t *wire,const RaBridgeStats *stats) {
    ra_bridge_put32(wire,RA_BRIDGE_STATS_MAGIC);
    for(size_t i=0;i<sizeof(*stats);i+=4) {
        uint32_t word;memcpy(&word,(const uint8_t *)stats+i,4);
        ra_bridge_put32(wire+4+i,word);
    }
    uint16_t crc=ra_bridge_crc(wire,RA_BRIDGE_STATS_BYTES-2);
    wire[RA_BRIDGE_STATS_BYTES-2]=(uint8_t)crc;
    wire[RA_BRIDGE_STATS_BYTES-1]=(uint8_t)(crc>>8);
}
static inline int ra_bridge_stats_unpack(RaBridgeStats *stats,const uint8_t *wire) {
    if(ra_bridge_get32(wire)!=RA_BRIDGE_STATS_MAGIC ||
       ra_bridge_crc(wire,RA_BRIDGE_STATS_BYTES-2)!=
       ((uint16_t)wire[RA_BRIDGE_STATS_BYTES-2]|((uint16_t)wire[RA_BRIDGE_STATS_BYTES-1]<<8)))return 0;
    for(size_t i=0;i<sizeof(*stats);i+=4) {
        uint32_t word=ra_bridge_get32(wire+4+i);memcpy((uint8_t *)stats+i,&word,4);
    }
    return 1;
}
/* Copy whole UTF-8 codepoints only. Control characters cannot become record delimiters. */
static inline int ra_bridge_text(char *out,size_t cap,const char *in) {
    size_t n=0; int cut=0;
    if(!cap) return 1;
    if(!in) in="";
    while(*in) {
        const uint8_t c=(uint8_t)*in;
        unsigned k=c<0x80?1:(c>=0xc2&&c<=0xdf?2:(c>=0xe0&&c<=0xef?3:(c>=0xf0&&c<=0xf4?4:0)));
        if(!k) { if(n+1>=cap){cut=1;break;} out[n++]='?'; in++; continue; }
        unsigned j;
        for(j=1;j<k;j++) if(!in[j]||((uint8_t)in[j]&0xc0)!=0x80) break;
        if(j!=k || (k==3 && ((c==0xe0&&(uint8_t)in[1]<0xa0)||(c==0xed&&(uint8_t)in[1]>=0xa0))) ||
           (k==4 && ((c==0xf0&&(uint8_t)in[1]<0x90)||(c==0xf4&&(uint8_t)in[1]>=0x90)))) {
            if(n+1>=cap){cut=1;break;} out[n++]='?'; in++; continue;
        }
        if(n+k>=cap){cut=1;break;}
        if(k==1 && c<0x20) out[n++]=' ';
        else for(j=0;j<k;j++) out[n++]=in[j];
        in+=k;
    }
    out[n]=0; return cut;
}
static inline size_t ra_bridge_encode(uint8_t *wire,const RaBridgeEvent *e) {
    size_t n=0; while(n<RA_BRIDGE_TEXT && e->title[n]) n++;
    if(n==RA_BRIDGE_TEXT || !e->session || !e->sequence || e->type<RA_EVENT_BEGIN || e->type>RA_EVENT_END) return 0;
    memset(wire,0,RA_BRIDGE_HEADER); wire[0]='R';wire[1]='A';wire[2]=RA_BRIDGE_VERSION;
    wire[3]=e->type;wire[4]=e->flags;wire[5]=(uint8_t)n;
    ra_bridge_put32(wire+8,e->session);ra_bridge_put32(wire+12,e->sequence);
    ra_bridge_put32(wire+16,e->game_id);ra_bridge_put32(wire+20,e->achievement_id);
    memcpy(wire+RA_BRIDGE_HEADER,e->title,n);
    uint16_t crc=ra_bridge_crc(wire,RA_BRIDGE_HEADER+n);
    wire[RA_BRIDGE_HEADER+n]=(uint8_t)crc;wire[RA_BRIDGE_HEADER+n+1]=(uint8_t)(crc>>8);
    return RA_BRIDGE_HEADER+n+2;
}
static inline int ra_bridge_decode(RaBridgeEvent *e,const uint8_t *wire,size_t size) {
    if(size<RA_BRIDGE_HEADER+2 || size>RA_BRIDGE_WIRE_MAX || wire[0]!='R'||wire[1]!='A'||
       wire[2]!=RA_BRIDGE_VERSION || wire[3]<RA_EVENT_BEGIN || wire[3]>RA_EVENT_END || (wire[4]&~31u) ||
       wire[5]>=RA_BRIDGE_TEXT || size!=RA_BRIDGE_HEADER+(size_t)wire[5]+2 || wire[6] || wire[7] ||
       ra_bridge_crc(wire,size-2)!=((uint16_t)wire[size-2]|((uint16_t)wire[size-1]<<8))) return 0;
    memset(e,0,sizeof(*e));e->type=wire[3];e->flags=wire[4];
    e->session=ra_bridge_get32(wire+8);e->sequence=ra_bridge_get32(wire+12);
    e->game_id=ra_bridge_get32(wire+16);e->achievement_id=ra_bridge_get32(wire+20);
    if(!e->session||!e->sequence || (e->type==RA_EVENT_UNLOCK && !e->achievement_id)) return 0;
    memcpy(e->title,wire+RA_BRIDGE_HEADER,wire[5]);
    if(strlen(e->title)!=wire[5]) return 0;
    char checked[RA_BRIDGE_TEXT];
    if(ra_bridge_text(checked,sizeof(checked),e->title)||strcmp(checked,e->title)) return 0;
    return 1;
}

/* Receiver writes only this private packet. Commit is the only publication point. */
typedef struct {
    uint8_t packet[RA_BRIDGE_WIRE_MAX], length, used, toggle, started;
    uint32_t received, crc_errors, duplicates, busy;
} RaBridgeRx;
static inline uint8_t ra_bridge_receive_byte(RaBridgeRx *r,uint8_t command,uint8_t data,
                                            RaBridgeEvent *event,int *complete) {
    *complete=0;
    if(command==RA_RTC_HELLO) { r->started=0; return data==RA_BRIDGE_VERSION?RA_RTC_HELLO_ACK:RA_RTC_BAD; }
    if(command==RA_RTC_RESET) {r->started=0;return RA_RTC_START_ACK;}
    if(command==RA_RTC_PING) return RA_RTC_PING_ACK;
    if(command==RA_RTC_START) {
        if(data<RA_BRIDGE_HEADER+2||data>RA_BRIDGE_WIRE_MAX) return RA_RTC_BAD;
        r->length=data;r->used=0;r->toggle=0;r->started=1;return RA_RTC_START_ACK;
    }
    if(command==RA_RTC_BYTE0||command==RA_RTC_BYTE1) {
        uint8_t toggle=command-RA_RTC_BYTE0;
        if(!r->started) return RA_RTC_BAD;
        if(toggle!=r->toggle) {r->duplicates++;return toggle?RA_RTC_BYTE1_ACK:RA_RTC_BYTE0_ACK;}
        if(r->used>=r->length) return RA_RTC_BAD;
        r->packet[r->used++]=data;r->toggle^=1;
        return toggle?RA_RTC_BYTE1_ACK:RA_RTC_BYTE0_ACK;
    }
    if(command==RA_RTC_COMMIT) {
        if(!r->started||r->used!=r->length||!ra_bridge_decode(event,r->packet,r->used)) {
            r->crc_errors++;return RA_RTC_BAD;
        }
        *complete=1;return RA_RTC_COMMIT_ACK;
    }
    return 0; /* Unknown commands belong to another client; never overwrite them. */
}

typedef struct {
    RaBridgeEvent queue[RA_BRIDGE_QUEUE];
    uint8_t wire[RA_BRIDGE_WIRE_MAX], head, count, phase, position, length, online, retries, disabled;
    uint16_t waiting, cooldown;
    uint32_t sent, dropped, timeouts;
} RaBridgeTx;
static inline int ra_bridge_enqueue(RaBridgeTx *t,const RaBridgeEvent *event) {
    if(t->count==RA_BRIDGE_QUEUE){t->dropped++;return 0;}
    t->queue[(t->head+t->count)%RA_BRIDGE_QUEUE]=*event;t->count++;return 1;
}
/* One shared-word operation per tick. No waiting for the ARM7, RTC, or ARM11. */
static inline void ra_bridge_transmit(RaBridgeTx *t,volatile uint32_t *word) {
    if(t->disabled) return;
    if(t->cooldown){t->cooldown--;return;}
    uint32_t v=*word;
    if((v&RA_BRIDGE_TAG_MASK)==RA_BRIDGE_REQUEST) {
        if(++t->waiting>120) {
            t->timeouts++;t->waiting=0;*word=0;t->online=0;t->phase=0;
            if(++t->retries>=3)t->disabled=1;
        }
        return;
    }
    if(v && (v&RA_BRIDGE_TAG_MASK)!=RA_BRIDGE_RESPONSE) return;
    t->waiting=0;
    uint8_t ack=(uint8_t)(v>>8);
    if(v) {
        *word=0;
        if(!t->online) {
            if(ack!=RA_RTC_HELLO_ACK){t->disabled=1;return;}
            t->online=1;t->phase=0;
        } else if(ack==RA_RTC_BUSY) {
            t->phase=0;t->cooldown=30;return; /* Backpressure is not a corrupt packet. */
        } else if(ack==RA_RTC_BAD) {
            t->phase=0;
            if(++t->retries>=3){t->disabled=1;return;}
        } else if(t->phase==1 && ack==RA_RTC_START_ACK) t->phase=2;
        else if(t->phase==2 && ack==(t->position&1?RA_RTC_BYTE1_ACK:RA_RTC_BYTE0_ACK)) {
            if(++t->position==t->length)t->phase=3;
        } else if(t->phase==3 && ack==RA_RTC_COMMIT_ACK) {
            t->head=(t->head+1)%RA_BRIDGE_QUEUE;t->count--;t->sent++;t->phase=0;t->retries=0;
        } else {t->timeouts++;t->phase=0;t->online=0;}
    }
    if(!t->count)return;
    uint8_t command,data=0;
    if(!t->online){command=RA_RTC_HELLO;data=RA_BRIDGE_VERSION;}
    else if(!t->phase) {
        t->length=(uint8_t)ra_bridge_encode(t->wire,&t->queue[t->head]);
        if(!t->length){t->disabled=1;return;}
        t->position=0;t->phase=1;command=RA_RTC_START;data=t->length;
    } else if(t->phase==2) {command=RA_RTC_BYTE0+(t->position&1);data=t->wire[t->position];}
    else if(t->phase==3) command=RA_RTC_COMMIT;
    else return;
    *word=RA_BRIDGE_REQUEST|((uint32_t)command<<8)|data;
}
#endif
