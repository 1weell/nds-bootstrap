/* GPL-3.0. Antigravity v7: typed events, bounded OCR compatibility, checked presentation. */
#include <stddef.h>
#include <stdint.h>
#include "font.h"
#include "notify.h"
#ifndef RA_OCR_FALLBACK
#define RA_OCR_FALLBACK 0
#endif
#ifndef RA_PRIVATE_OUTPUT
#define RA_PRIVATE_OUTPUT 0
#endif
#define PILL_WIDTH 232
#define PILL_HEIGHT 28
#define RTC_BASE 0x1ec47100u
#define VRAM_START 0x1f000000u
#define VRAM_END 0x1f600000u
#define FB_BYTES (320u*720u)
#define HUD_CACHE_FIRST (80u*720u+(240u-8u-PILL_HEIGHT)*3u)
#define HUD_CACHE_END ((80u+PILL_WIDTH-1u)*720u+(240u-8u)*3u)
typedef uint32_t (*Present)(uint32_t,uint32_t,uint32_t,uint32_t,uint32_t,uint32_t,uint32_t);
extern uint32_t ra_store_cache(uint32_t,uint32_t);
extern uint32_t ra_invalidate(uint32_t,uint32_t);
extern uint64_t ra_ticks(void);
extern void ra_copy_frame(void *,const void *);
typedef uint32_t (*Allocate)(uint32_t,uint32_t,uint32_t,uint32_t,uint32_t,uint32_t);
struct Diagnostics {
    uint32_t magic,version,calls,bottom_calls,popups_shown,frames_left,consecutive_blank;
    uint32_t game_starts_detected,unlocks_detected;
    uint32_t rejected_format,rejected_address,cache_errors,received,duplicates,dropped;
    uint32_t last_stride,last_format,rtc_busy,crc_errors,ocr_rejected;
    uint32_t max_ticks, timed_calls, time_bins[8];
    uint64_t total_ticks;
};
volatile struct Diagnostics ra_diagnostics;
RaNotify ra_notifications;
char ra_display_title[RA_BRIDGE_TEXT];
static RaBridgeRx receiver;
static uint8_t statistics[RA_BRIDGE_STATS_BYTES];
static RaBridgeStats presentation;
static uint8_t allocation_failed;
static uint32_t shown_session,shown_sequence;
/* Reset our allocation epoch through the original heap initializer. Keeping a
 * raw pointer across a native heap rebuild would not retain ownership. The
 * builder patches only the verified first-VRAM-heap initialization call. */
uint32_t ra_heap_initialize(uint32_t heap,uint32_t begin,uint32_t bytes,uint32_t flags) {
    typedef uint32_t (*Initialize)(uint32_t,uint32_t,uint32_t,uint32_t);
    if(heap==0x12bdb8) {
        presentation.pool_base=0;presentation.last_output=0;allocation_failed=0;
    }
    return ((Initialize)(uintptr_t)0x104333)(heap,begin,bytes,flags);
}
static uint64_t text_scroll;
static uint32_t ocr_sequence;
static char ocr_last_title[RA_BRIDGE_TEXT],ocr_candidate[RA_BRIDGE_TEXT];
static uint8_t ocr_last_type,ocr_candidate_type,ocr_stable,ocr_absent;
static const uint8_t scaled_pixels[8]={0,1,2,3,5,6,7,8};
static void draw_char(uint8_t *fb, uint32_t stride, int x, int y, char c,
                      uint8_t b, uint8_t g, uint8_t r) {
    if ((uint8_t)c < RA_FONT_FIRST || (uint8_t)c > RA_FONT_LAST) c = ' ';
    const uint8_t *glyph = ra_font[(uint8_t)c - RA_FONT_FIRST];
    for (int row = 0; row < 8; ++row) {
        int py = y + row;
        if (py < 0 || py >= 240) continue;
        uint8_t bits = glyph[row];
        for (int col = 0; col < 8; ++col) {
            if (bits & (0x80 >> col)) {
                int px = x + col;
                if (px < 0 || px >= 320) continue;
                size_t offset = (size_t)px * stride + (239 - py) * 3;
                fb[offset]     = b;
                fb[offset + 1] = g;
                fb[offset + 2] = r;
            }
        }
    }
}

static void draw_string(uint8_t *fb, uint32_t stride, int x, int y, const char *s,
                        uint8_t text_b, uint8_t text_g, uint8_t text_r, int with_shadow) {
    if (!s) return;
    char line[RA_BRIDGE_TEXT];
    unsigned length=0;
    while (*s && length < sizeof(line)-1) line[length++]=ra_display_char(&s);
    line[length]=0;
    unsigned first=0;
    if (length>24 && text_scroll>RA_TICKS_SECOND)
        first=(unsigned)((text_scroll-RA_TICKS_SECOND)/(RA_TICKS_SECOND/8));
    if(first>length-24 && length>24) first=length-24;
    int cur_x=x;
    for(unsigned i=first;i<length && cur_x+8<=x+24*8;i++,cur_x+=8) {
        char c=line[i];
        if(with_shadow)draw_char(fb,stride,cur_x+1,y+1,c,0,0,0);
        draw_char(fb,stride,cur_x,y,c,text_b,text_g,text_r);
    }
}

static void draw_pill_hud(uint8_t *fb, uint32_t stride, int x_start, int y_start,
                          const char *line1, const char *line2) {
    // 12x14 Trophy icon bitmask
    static const uint16_t trophy_bits[14] = {
        0x1F8, 0x3FC, 0xFFF, 0xDFB, 0xDFB, 0x5FA, 0x1F8,
        0x0F0, 0x060, 0x060, 0x0F0, 0x1F8, 0x3FC, 0x7FE
    };

    // 1. Draw Pill Background, Borders, and Trophy
    for (unsigned v = 0; v < PILL_HEIGHT; ++v) {
        unsigned y = y_start + v;
        if (y >= 240) continue;

        for (unsigned u = 0; u < PILL_WIDTH; ++u) {
            unsigned x = x_start + u;
            if (x >= 320) continue;

            int is_border = 0;
            int is_inner = 0;
            int inside = 1;

            if (u < 14) {
                int dx = (int)u - 13;
                int dy = (int)v - 13;
                int d2 = dx * dx + dy * dy;
                if (d2 > 196) inside = 0;
                else if (d2 > 144) is_border = 1;
                else if (d2 > 110) is_inner = 1;
            } else if (u >= (PILL_WIDTH - 14)) {
                int dx = (int)u - (PILL_WIDTH - 14);
                int dy = (int)v - 13;
                int d2 = dx * dx + dy * dy;
                if (d2 > 196) inside = 0;
                else if (d2 > 144) is_border = 1;
                else if (d2 > 110) is_inner = 1;
            } else {
                if (v == 0 || v == (PILL_HEIGHT - 1)) is_border = 1;
                else if (v == 1 || v == (PILL_HEIGHT - 2)) is_inner = 1;
            }

            if (!inside) continue;

            uint8_t b, g, r;
            if (is_border) {
                // Outer Gold Border (BGR: 65, 185, 225)
                b = 65; g = 185; r = 225;
            } else if (is_inner) {
                // Inner Dark Bronze Accent (BGR: 20, 60, 80)
                b = 20; g = 60; r = 80;
            } else {
                // Check Trophy Icon (u: 8..19, v: 7..20)
                int is_trophy = 0;
                if (u >= 8 && u < 20 && v >= 7 && v < 21) {
                    unsigned tu = u - 8;
                    unsigned tv = v - 7;
                    if ((trophy_bits[tv] >> (11 - tu)) & 1) {
                        is_trophy = 1;
                        if (tv < 3 && tu >= 4 && tu <= 7) {
                            // Specular White Highlight
                            b = 230; g = 252; r = 255;
                        } else if (tu == 0 || tu == 11 || tv == 13) {
                            // Dark Gold Shadow
                            b = 20; g = 140; r = 190;
                        } else {
                            // Vibrant Gold
                            b = 0; g = 215; r = 255;
                        }
                    }
                }

                if (!is_trophy) {
                    // Body Glassmorphism Gradient
                    if (v < 8) {
                        // Top highlight (Deep Slate Navy)
                        b = 56; g = 38; r = 28;
                    } else if (v < 19) {
                        // Mid tone (Dark Obsidian)
                        b = 36; g = 23; r = 16;
                    } else {
                        // Bottom shadow (Midnight Glass)
                        b = 22; g = 14; r = 10;
                    }
                }
            }

            size_t offset = (size_t)x * stride + (239 - y) * 3;
            fb[offset]     = b;
            fb[offset + 1] = g;
            fb[offset + 2] = r;
        }
    }

    // 2. Render Text directly inside the Pill
    // Line 1: Header in Vibrant Gold (BGR: 68, 195, 246)
    draw_string(fb, stride, x_start + 26, y_start + 5, line1, 68, 195, 246, 1);

    // Line 2: Details in Crisp Pure White (BGR: 255, 255, 255)
    draw_string(fb, stride, x_start + 26, y_start + 15, line2, 255, 255, 255, 1);
}


static void poll_rtcom(void) {
    volatile uint16_t *rtc=(volatile uint16_t *)(uintptr_t)RTC_BASE;
    if(rtc[0]&0x4000){ra_diagnostics.rtc_busy++;return;}
    uint16_t value=rtc[9];
    uint8_t command=(uint8_t)(value>>8),data=(uint8_t)value;
    if(command<RA_RTC_HELLO||command>RA_RTC_STATS)return;
    RaBridgeEvent event;int complete;
    uint8_t ack;
    if(command==RA_RTC_STATS) {
        complete=0;
        if(data==0) {
            presentation.format=ra_diagnostics.last_format;
            presentation.stride=ra_diagnostics.last_stride;
            presentation.shown=ra_diagnostics.popups_shown;
            presentation.rejected=ra_diagnostics.rejected_format+ra_diagnostics.rejected_address;
            presentation.cache_errors=ra_diagnostics.cache_errors;
            presentation.max_ticks=ra_diagnostics.max_ticks;
            presentation.bottom_calls=ra_diagnostics.bottom_calls;
            presentation.rejected_format=ra_diagnostics.rejected_format;
            presentation.rejected_address=ra_diagnostics.rejected_address;
            ra_bridge_stats_pack(statistics,&presentation);
        }
        ack=data<sizeof(statistics)?RA_RTC_STATS_ACK:RA_RTC_BAD;
        *(volatile uint8_t *)(uintptr_t)(RTC_BASE+0x12)=data<sizeof(statistics)?statistics[data]:0;
    } else ack=ra_bridge_receive_byte(&receiver,command,data,&event,&complete);
    if(command==RA_RTC_PING)
        *(volatile uint8_t *)(uintptr_t)(RTC_BASE+0x12)=data^0xa5;
    if(complete) {
        int result=ra_notify_accept(&ra_notifications,&event);
        ack=result>0?RA_RTC_COMMIT_ACK:(result==0?RA_RTC_BUSY:RA_RTC_BAD);
        if(result>0)receiver.received++;
    }
    /* Latch only the status byte. Never wait for the RTC busy bit in this hook. */
    *(volatile uint8_t *)(uintptr_t)(RTC_BASE+0x13)=ack;
    rtc[0]=(command==RA_RTC_PING || command==RA_RTC_STATS)?0x600c:0x6008;
}
static unsigned bit_count(uint8_t bits) {
    unsigned n=0;while(bits){bits&=bits-1;n++;}return n;
}
static uint8_t sample_row(const uint8_t *fb,int col,int row,int gy,int scaled) {
    uint8_t bits=0;
    int py=row+(scaled?scaled_pixels[gy]:gy);
    for(int gx=0;gx<8;gx++) {
        int px=(scaled?col*10:32+col*8)+(scaled?scaled_pixels[gx]:gx);
        size_t off=(size_t)px*720+(239-py)*3;
        if(fb[off]>220&&fb[off+1]>220&&fb[off+2]>220)bits|=0x80>>gx;
    }
    return bits;
}
static unsigned glyph_difference(const uint8_t *fb,int col,int row,char c,int scaled) {
    unsigned diff=0;
    for(int gy=0;gy<8;gy++)diff+=bit_count(sample_row(fb,col,row,gy,scaled)^ra_font[(uint8_t)c-RA_FONT_FIRST][gy]);
    return diff;
}
static int header_matches(const uint8_t *fb,int row,const char *text,int scaled) {
    int n=(int)strlen(text),start=31-n;unsigned total=0;
    /* Full positive and negative glyph masks; no empty-prefix inference. */
    if(glyph_difference(fb,30,row,text[n-1],scaled)>5)return 0;
    for(int i=0;i<n;i++) {
        unsigned d=glyph_difference(fb,start+i,row,text[i],scaled);
        if(d>6)return 0;
        total+=d;
    }
    return total<=(unsigned)n*3;
}
static int decode_title(const uint8_t *fb,int row,int scaled,char *out) {
    char decoded[32];unsigned uncertain=0;
    for(int col=0;col<31;col++) {
        uint8_t cell[8];
        for(int gy=0;gy<8;gy++)cell[gy]=sample_row(fb,col,row,gy,scaled);
        unsigned best=65,second=65;char ch=' ';
        for(int c=RA_FONT_FIRST;c<=RA_FONT_LAST;c++) {
            unsigned d=0;
            for(int gy=0;gy<8;gy++)d+=bit_count(cell[gy]^ra_font[c-RA_FONT_FIRST][gy]);
            if(d<best){second=best;best=d;ch=(char)c;}else if(d<second)second=d;
        }
        if(best>6 || second==best || (best && second<best+2)){ch='?';uncertain++;}
        decoded[col]=ch;
    }
    decoded[31]=0;
    int start=0,end=31;while(start<end&&decoded[start]==' ')start++;
    while(end>start&&decoded[end-1]==' ')end--;
    if(uncertain||start==end)return 0;
    decoded[end]=0;ra_bridge_text(out,RA_BRIDGE_TEXT,decoded+start);return 1;
}
static void poll_ocr(const uint8_t *fb) {
    if(!RA_OCR_FALLBACK || (ra_notifications.session && ra_notifications.session!=0x4f435231u))return;
    static const char *headers[]={"RETROACHIEVEMENTS","ACHIEVEMENT","POPUP TEST"};
    uint8_t type=0;char title[RA_BRIDGE_TEXT]={0};
    for(int scaled=1;scaled>=0 && !type;scaled--)for(int row=0;row<2 && !type;row++) {
        int y=scaled?row*10:24+row*8;
        for(unsigned h=0;h<3;h++)if(header_matches(fb,y,headers[h],scaled)) {
            if(!decode_title(fb,y+(scaled?10:8),scaled,title)){ra_diagnostics.ocr_rejected++;break;}
            type=h==0?RA_EVENT_READY:(h==1?RA_EVENT_UNLOCK:RA_EVENT_PREVIEW);break;
        }
    }
    if(!type){ocr_stable=0;if(ocr_absent<3)ocr_absent++;if(ocr_absent==3)ocr_last_type=0;return;}
    ocr_absent=0;
    if(type!=ocr_candidate_type || strcmp(title,ocr_candidate)) {
        ocr_candidate_type=type;ra_bridge_text(ocr_candidate,sizeof(ocr_candidate),title);ocr_stable=1;return;
    }
    if(ocr_stable<2)ocr_stable++;
    if(ocr_stable<2 || (type==ocr_last_type && !strcmp(title,ocr_last_title)))return;
    RaBridgeEvent e={0};e.session=0x4f435231u;e.sequence=++ocr_sequence;e.flags=RA_EVENT_ENABLED|RA_EVENT_ACTIVE;
    if(!ra_notifications.session){e.type=RA_EVENT_BEGIN;ra_notify_accept(&ra_notifications,&e);e.sequence=++ocr_sequence;}
    e.type=type;ra_bridge_text(e.title,sizeof(e.title),title);
    if(type==RA_EVENT_READY) {
        const char *s=e.title;
        if(!strncmp(s,"Sessao iniciada: ",16))s+=16;
        else if(!strncmp(s,"Offline: ",9)){s+=9;e.flags|=RA_EVENT_OFFLINE;}
        char name[RA_BRIDGE_TEXT]={0};ra_bridge_text(name,sizeof(name),s);memcpy(e.title,name,sizeof(name));
    }
    if(ra_notify_accept(&ra_notifications,&e)>0) {
        ocr_last_type=type;ra_bridge_text(ocr_last_title,sizeof(ocr_last_title),title);
    }
}
static uint32_t read32(uint32_t address) {
    return *(volatile uint32_t *)(uintptr_t)address;
}
static int span(uint32_t address,uint32_t bytes,uint32_t begin,uint32_t end) {
    return address>=begin && address<=end && bytes<=end-address;
}
static int overlaps(uint32_t a,uint32_t b,uint32_t bytes) {
    return a<=b ? b-a<bytes : a-b<bytes;
}
/* The caller computes the LCD viewport from this image descriptor. Validate
 * both the read and its rounded cache span inside that same allocation. */
static unsigned source_reason(uint32_t left,uint32_t right,uint32_t stride,uint32_t format) {
    if(stride!=720 || (format&7)!=1 || (right && right!=left))return 1;
    if(!span(left,FB_BYTES,VRAM_START,VRAM_END))return 2;
    uint32_t object=read32(0x12cb68);
    if(!span(object,24,0x100000,0x154000) && !span(object,24,VRAM_START,VRAM_END))return 4;
    uint32_t base=read32(object+4),width=read32(object+12),height=read32(object+16);
    if(read32(object+8)!=0x8051 || width!=240 || height<320 || height>1024)return 4;
    uint32_t bytes=width*height*3,first=left&~31u,last=(left+FB_BYTES+31)&~31u;
    if(!span(base,bytes,VRAM_START,VRAM_END) || first<base ||
       last<first || last-base>bytes)return 4;
    return 0;
}
static void surface_record(uint32_t left,uint32_t stride,uint32_t format,unsigned reason) {
    unsigned slot=4;
    for(unsigned i=0;i<4;i++) {
        RaBridgeSurface *s=&presentation.surfaces[i];
        if(s->count_reason && s->address==left && s->stride==stride && s->format==format){slot=i;break;}
    }
    if(slot==4) {
        slot=presentation.surface_changes++%4;
        presentation.surfaces[slot]=(RaBridgeSurface){left,stride,format,0};
    }
    RaBridgeSurface *s=&presentation.surfaces[slot];
    uint32_t count=s->count_reason&0xffffff;
    if(count<0xffffff)count++;
    s->count_reason=count|((s->count_reason|((uint32_t)reason<<24))&0xff000000);
}
/* One allocator-owned block, three disjoint complete frames. Never infer free
 * VRAM from a mapped address; allocation failure leaves original presentation. */
static uint32_t private_output(uint32_t source,unsigned *reason) {
    if(allocation_failed){*reason=16;return 0;}
    if(!presentation.pool_base) {
        if(read32(0x12bdd0)!=0x45585048 || read32(0x12bde8)!=VRAM_START ||
           read32(0x12bdec)!=0x1f300000){*reason=32;return 0;}
        /* Same heap call/arguments as 0x10560c, before the texture wrapper
         * registers its result under global Nintendo texture ID 0x1279f8.
         * Our storage is untagged; do not alter that ID or its pointer table. */
        Allocate allocate=(Allocate)(uintptr_t)0x11045d;
        uint32_t pool=allocate(0x12bdb8,3*FB_BYTES,128,0,0,0);
        if((pool&127) || !span(pool,3*FB_BYTES,VRAM_START,0x1f300000)) {
            allocation_failed=1;presentation.allocation_errors++;*reason=16;return 0;
        }
        presentation.pool_base=pool;
    }
    if(source<presentation.pool_base+3*FB_BYTES && source+FB_BYTES>presentation.pool_base) {
        *reason=64;return 0;
    }
    uint32_t a=read32(0x1ef00568),b=read32(0x1ef0056c);
    for(unsigned i=0;i<3;i++) {
        uint32_t p=presentation.pool_base+i*FB_BYTES,physical=p-0x07000000;
        if(!overlaps(physical,a,FB_BYTES) && !overlaps(physical,b,FB_BYTES))return p;
    }
    presentation.no_free_buffer++;*reason=128;return 0;
}
uint32_t ra_present(uint32_t screen,uint32_t index,uint32_t left,uint32_t right,
                    uint32_t stride,uint32_t format,uint32_t select) {
    Present original=(Present)(uintptr_t)0x1088c1;
    ra_diagnostics.magic=0x31574c54;ra_diagnostics.version=8;ra_diagnostics.calls++;
    uint64_t started=ra_ticks();
    poll_rtcom();
    if(screen!=1)return original(screen,index,left,right,stride,format,select);
    ra_diagnostics.bottom_calls++;ra_diagnostics.last_stride=stride;ra_diagnostics.last_format=format;
    presentation.last_source=left;presentation.last_index=index;presentation.last_select=select;
    presentation.mode=RA_PRIVATE_OUTPUT?1:2;
    uint32_t output=0;
    unsigned reason;
    if(RA_PRIVATE_OUTPUT)reason=source_reason(left,right,stride,format);
    else reason=(stride!=720 || (format&7)!=1 || (right && right!=left))?1:
                (!span(left,FB_BYTES,VRAM_START,VRAM_END)?2:0);
    uint64_t now=ra_ticks();
    if(ra_notifications.active && now>=ra_notifications.expires)ra_notifications.active=0;
    if(reason) {
        if(reason==1)ra_diagnostics.rejected_format++;else ra_diagnostics.rejected_address++;
        goto done;
    }
    if(!RA_OCR_FALLBACK && !ra_notifications.active && !ra_notifications.count)goto done;
    if(*(volatile uint8_t *)(uintptr_t)0x12ca51) {
        presentation.gpu_busy++;reason=8;goto done;
    }
    /* Only HUD lines are touched in the proven in-place path. Frame starts
     * observed on hardware alternate between 32-byte alignment and +16.
     * Rounding the entire image down would include its allocator header.
     * This interior interval contains every HUD write and stays inside either
     * viewport, including the unaligned one, without touching that header. */
    uint32_t first=(RA_PRIVATE_OUTPUT?left:left+HUD_CACHE_FIRST)&~31u;
    uint32_t end=RA_PRIVATE_OUTPUT?left+FB_BYTES:left+HUD_CACHE_END;
    uint32_t size=((end+31)&~31u)-first;
    if(ra_invalidate(first,size)){ra_diagnostics.cache_errors++;goto done;}
    const uint8_t *source=(const uint8_t *)(uintptr_t)left;
    poll_ocr(source);
    if(!ra_notifications.active && !ra_notifications.count)goto done;
    if(RA_PRIVATE_OUTPUT)output=private_output(left,&reason);else output=left;
    if(!output)goto done;
    uint8_t *fb=(uint8_t *)(uintptr_t)output;
    if(RA_PRIVATE_OUTPUT) {
        if(left&3)memcpy(fb,source,FB_BYTES);else ra_copy_frame(fb,source);
    }
    /* Start a queued notification only after its surface/cache guard succeeds. */
    ra_notify_tick(&ra_notifications,now);
    if(ra_notifications.active) {
        const RaBridgeEvent *e=&ra_notifications.current;
        memcpy(ra_display_title,e->title,sizeof(ra_display_title));
        const char *line1=e->type==RA_EVENT_UNLOCK?"CONQUISTA DESBLOQUEADA!":
                         (e->type==RA_EVENT_PREVIEW?"TESTE DE NOTIFICACAO":
                          ((e->flags&RA_EVENT_OFFLINE)?"RETROACHIEVEMENTS OFFLINE":"RETROACHIEVEMENTS"));
        text_scroll=now-ra_notifications.started;
        draw_pill_hud(fb,stride,80,8,line1,e->title[0]?e->title:"Nome indisponivel");
        uint32_t clean=RA_PRIVATE_OUTPUT?output:first;
        uint32_t clean_size=RA_PRIVATE_OUTPUT?FB_BYTES:size;
        if(ra_store_cache(clean,clean_size)) {
            ra_diagnostics.cache_errors++;output=0;
        } else {
            presentation.last_output=output;presentation.composited++;
            if(shown_session!=e->session || shown_sequence!=e->sequence) {
                shown_session=e->session;shown_sequence=e->sequence;ra_diagnostics.popups_shown++;
                if(e->type==RA_EVENT_UNLOCK)ra_diagnostics.unlocks_detected++;
                else if(e->type==RA_EVENT_READY)ra_diagnostics.game_starts_detected++;
            }
        }
    }
done:
    surface_record(left,stride,format,reason);
    if(reason && (ra_notifications.active || ra_notifications.count))presentation.active_rejected++;
    {
        uint32_t elapsed=(uint32_t)(ra_ticks()-started);
        static const uint32_t limits[7]={26812,67030,134061,268123,536246,1072493,2144987};
        unsigned bucket=0;while(bucket<7 && elapsed>limits[bucket])bucket++;
        ra_diagnostics.time_bins[bucket]++;ra_diagnostics.timed_calls++;
        ra_diagnostics.total_ticks+=elapsed;
        if(elapsed>ra_diagnostics.max_ticks)ra_diagnostics.max_ticks=elapsed;
        if(output) {
            presentation.composite_bins[bucket]++;
            if(elapsed>presentation.composite_max_ticks)presentation.composite_max_ticks=elapsed;
            uint32_t previous=presentation.composite_total_low;
            presentation.composite_total_low+=elapsed;
            if(presentation.composite_total_low<previous)presentation.composite_total_high++;
        }
    }
    if(!ra_notifications.active)ra_display_title[0]=0;
    ra_diagnostics.received=ra_notifications.received;ra_diagnostics.duplicates=ra_notifications.duplicates;
    ra_diagnostics.dropped=ra_notifications.dropped;ra_diagnostics.crc_errors=receiver.crc_errors;
    return original(screen,index,output?output:left,output&&right?output:right,stride,format,select);
}
