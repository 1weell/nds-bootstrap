/* GPL-3.0. Presentation queue; independent of GPU, RTC, and RA award persistence. */
#ifndef RA_NOTIFY_H
#define RA_NOTIFY_H
#include "ra_bridge.h"
typedef struct {
    RaBridgeEvent queue[RA_BRIDGE_QUEUE], current;
    uint32_t session, sequence, received, shown, duplicates, dropped;
    uint32_t retired[4];
    uint64_t expires, started;
    uint8_t head, count, active, enabled, retired_head;
} RaNotify;
static int ra_notify_accept(RaNotify *n,const RaBridgeEvent *e) {
    if(e->type==RA_EVENT_BEGIN && e->session!=n->session) {
        for(unsigned i=0;i<4;i++)if(n->retired[i]==e->session)return -1;
        if(n->session)n->retired[n->retired_head++%4]=n->session;
        n->head=n->count=n->active=0;n->session=e->session;n->sequence=0;
        n->enabled=(e->flags&RA_EVENT_ENABLED)!=0;
    }
    if(e->session!=n->session)return -1;
    if((int32_t)(e->sequence-n->sequence)<=0){n->duplicates++;return 1;}
    if(e->type==RA_EVENT_BEGIN) {n->sequence=e->sequence;n->received++;return 1;}
    if(e->type==RA_EVENT_END) {
        n->head=n->count=n->active=n->enabled=0;n->sequence=e->sequence;n->received++;return 1;
    }
    if(!n->enabled || (e->type==RA_EVENT_READY && !(e->flags&RA_EVENT_ACTIVE))) {
        n->sequence=e->sequence;n->received++;return 1;
    }
    if(n->count==RA_BRIDGE_QUEUE){n->dropped++;return 0;}
    n->queue[(n->head+n->count)%RA_BRIDGE_QUEUE]=*e;n->count++;
    n->sequence=e->sequence;n->received++;return 1;
}
/* ARM11 system ticks (268123480 Hz), not presentation-call counts. */
#define RA_TICKS_SECOND 268123480ull
static void ra_notify_tick(RaNotify *n,uint64_t now) {
    if(n->active && now>=n->expires)n->active=0;
    if(!n->active && n->count) {
        n->current=n->queue[n->head];n->head=(n->head+1)%RA_BRIDGE_QUEUE;n->count--;
        unsigned seconds=n->current.type==RA_EVENT_UNLOCK?4:3,characters=0;
        for(const unsigned char *p=(const unsigned char *)n->current.title;*p;p++)
            if((*p&0xc0)!=0x80)characters++;
        if(characters>24) {
            unsigned readable=2+(characters-24+7)/8;
            if(readable>seconds)seconds=readable;
        }
        n->started=now;n->expires=now+RA_TICKS_SECOND*seconds;
        n->active=1;n->shown++;
    }
}
/* Keep original UTF-8 in events; render unsupported codepoints deterministically. */
static char ra_display_char(const char **text) {
    const uint8_t *s=(const uint8_t *)*text;
    if(*s<0x80){(*text)++;return (char)(*s>=0x20?*s:' ');}
    unsigned k=(*s&0xe0)==0xc0?2:((*s&0xf0)==0xe0?3:4);
    uint32_t c=*s&((1u<<(7-k))-1);
    for(unsigned i=1;i<k && s[i];i++)c=(c<<6)|(s[i]&63);
    for(unsigned i=0;i<k && **text;i++)(*text)++;
    switch(c) {
    case 0xc0:case 0xc1:case 0xc2:case 0xc3:case 0xc4:case 0xc5:return 'A';
    case 0xe0:case 0xe1:case 0xe2:case 0xe3:case 0xe4:case 0xe5:return 'a';
    case 0xc7:return 'C';case 0xe7:return 'c';
    case 0xc8:case 0xc9:case 0xca:case 0xcb:return 'E';
    case 0xe8:case 0xe9:case 0xea:case 0xeb:return 'e';
    case 0xcc:case 0xcd:case 0xce:case 0xcf:return 'I';
    case 0xec:case 0xed:case 0xee:case 0xef:return 'i';
    case 0xd1:return 'N';case 0xf1:return 'n';
    case 0xd2:case 0xd3:case 0xd4:case 0xd5:case 0xd6:return 'O';
    case 0xf2:case 0xf3:case 0xf4:case 0xf5:case 0xf6:return 'o';
    case 0xd9:case 0xda:case 0xdb:case 0xdc:return 'U';
    case 0xf9:case 0xfa:case 0xfb:case 0xfc:return 'u';
    case 0x2018:case 0x2019:return '\'';case 0x201c:case 0x201d:return '"';
    case 0x2013:case 0x2014:return '-';default:return '?';
    }
}
#endif
