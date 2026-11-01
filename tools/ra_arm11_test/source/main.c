/* GPL-3.0. Native ARM11 compositor workbench. This app does not run a DS game,
 * patch TwlBg, evaluate achievements, or access game/bootstrap/save files.
 */
#include <3ds.h>
#include <errno.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include "postcompose.h"
#include "ra_text.h"

#ifndef APP_ROOT
#define APP_ROOT "sdmc:/3ds/ra-arm11-test"
#endif
#define TOP_BYTES (400u*240u*3u)
#define BOTTOM_BYTES (320u*240u*3u)
#define FRAME_BYTES (TOP_BYTES+BOTTOM_BYTES)
#define SAMPLE_COUNT 600u
#define EVENT_COUNT 32u
#define POPUP_FRAMES 180u

typedef struct {
    u32 start_frame,end_frame,drawn_frames;
    u64 start_tick,end_tick;
    unsigned panel;
    const char *kind,*end_reason;
} Event;
static Event events[EVENT_COUNT];
static unsigned event_count,event_overflow;
static u32 copy_samples[SAMPLE_COUNT],flush_samples[SAMPLE_COUNT];
static unsigned sample_count,frames,preview_requests,panel_moves,manual_closes,suspends;
static u64 copy_total,flush_total;
static u64 session_ticks;
static u32 copy_max,flush_max;
static unsigned frames_left;
static gfxScreen_t panel=GFX_BOTTOM;
static int render_error;
static unsigned memory_checks;
static uintptr_t checked_buffers[4];
static size_t checked_sizes[4];
static aptHookCookie hook;
static u32 popup_strip[512] __attribute__((aligned(4)));
static u32 label_strip[512] __attribute__((aligned(4)));
static u32 stats_strip[512] __attribute__((aligned(4)));

static u32 word(const u8 *p) {
    return (u32)p[0]|(u32)p[1]<<8|(u32)p[2]<<16|(u32)p[3]<<24;
}
static u32 fnv(const u8 *p,size_t n) {
    u32 h=2166136261u;
    for(size_t i=0;i<n;++i)h=(h^p[i])*16777619u;
    return h;
}
static u32 microseconds(u64 ticks) {
    return (u32)(ticks*1000000u/SYSCLOCK_ARM11);
}
static int cpu_writable(const void *pointer,size_t bytes) {
    uintptr_t address=(uintptr_t)pointer;
    if(!address || address>UINT32_MAX || bytes>UINT32_MAX-address)return 0;
    for(unsigned i=0;i<4;++i)
        if(checked_buffers[i]==address && checked_sizes[i]>=bytes)return 1;
    u32 cursor=(u32)address,remaining=(u32)bytes;
    while(remaining) {
        MemInfo memory={0};PageInfo page={0};
        ++memory_checks;
        Result result=svcQueryMemory(&memory,&page,cursor);
        if(R_FAILED(result) || (memory.perm&MEMPERM_READWRITE)!=MEMPERM_READWRITE ||
           memory.base_addr>cursor || cursor-memory.base_addr>=memory.size)return 0;
        u32 available=memory.size-(cursor-memory.base_addr);
        u32 step=remaining<available?remaining:available;
        cursor+=step;remaining-=step;
    }
    for(unsigned i=0;i<4;++i)if(!checked_buffers[i]) {
        checked_buffers[i]=address;checked_sizes[i]=bytes;break;
    }
    return 1;
}
static void stamp(u8 *out,unsigned width,unsigned y,const u32 *strip) {
    /* Output is this app's writable backbuffer. Gray colors are BGR-invariant. */
    for(unsigned row=0;row<16;++row)for(unsigned col=0;col<256;++col) {
        unsigned i=((row/8)*32+col/8)*8+row%8;
        unsigned ink=(strip[i]>>((col%8)*4))&15;
        u8 value=ink==1?255:ink==2?0:24;
        size_t p=(((width-256)/2+col)*240u+239-(y+row))*3;
        out[p]=out[p+1]=out[p+2]=value;
    }
}
static void close_event(const char *reason) {
    if(frames_left && event_count && !events[event_count-1].end_reason) {
        events[event_count-1].end_reason=reason;
        events[event_count-1].end_frame=frames;
        events[event_count-1].end_tick=svcGetSystemTick();
    }
    frames_left=0;
}
static void begin_event(const char *kind,const char *first,const char *second) {
    close_event("replaced");
    memcpy(popup_strip,ra_text_render(first,second),sizeof(popup_strip));
    frames_left=POPUP_FRAMES;
    if(event_count<EVENT_COUNT) {
        events[event_count++]=(Event){.start_frame=frames,.start_tick=svcGetSystemTick(),
                                    .panel=(unsigned)panel,.kind=kind};
    } else ++event_overflow;
}
static void apt_event(APT_HookType type,void *unused) {
    (void)unused;
    if(type==APTHOOK_ONSUSPEND)++suspends;
}

static u8 *load_frames(unsigned *count,u32 *checksum) {
    FILE *file=fopen(APP_ROOT "/frames.bin","rb");
    if(!file)return NULL;
    u8 header[32];u8 *data=NULL;
    if(fread(header,1,sizeof(header),file)!=sizeof(header) ||
       memcmp(header,"RAPRF1\0\0",8) || word(header+12)!=400 ||
       word(header+16)!=320 || word(header+20)!=240)goto end;
    *count=word(header+8);*checksum=word(header+28);
    if(!*count || *count>8 || word(header+24)!=*count*FRAME_BYTES)goto end;
    size_t bytes=(size_t)*count*FRAME_BYTES;
    data=malloc(bytes);
    if(!data)goto end;
    if(fread(data,1,bytes,file)!=bytes || fgetc(file)!=EOF ||
       ferror(file) || fnv(data,bytes)!=*checksum){free(data);data=NULL;}
end:
    fclose(file);return data;
}
static int compare_u32(const void *a,const void *b) {
    u32 x=*(const u32*)a,y=*(const u32*)b;
    return (x>y)-(x<y);
}
static int save_file(const char *path,const void *data,size_t size) {
    FILE *file=fopen(path,"wb");
    if(!file)return 0;
    int ok=fwrite(data,1,size,file)==size;
    if(fclose(file))ok=0;
    return ok;
}
static int save_report(u32 asset_checksum,unsigned image_count,
                       const u8 *top,const u8 *bottom) {
    char directory[160],path[192];int created=0;
    if(mkdir(APP_ROOT "/reports",0700) && errno!=EEXIST)return 0;
    for(unsigned i=0;i<1000;++i) {
        snprintf(directory,sizeof(directory),APP_ROOT "/reports/%03u",i);
        if(!mkdir(directory,0700)){created=1;break;}
        if(errno!=EEXIST)break;
    }
    if(!created)return 0;
    snprintf(path,sizeof(path),"%s/report.json",directory);
    FILE *file=fopen(path,"w");
    if(!file)return 0;
    unsigned n=sample_count<SAMPLE_COUNT?sample_count:SAMPLE_COUNT;
    qsort(copy_samples,n,sizeof(u32),compare_u32);
    qsort(flush_samples,n,sizeof(u32),compare_u32);
    u8 model=255;Result result=cfguInit();
    if(R_SUCCEEDED(result)){CFGU_GetSystemModel(&model);cfguExit();}
    fprintf(file,"{\n  \"format\": \"RA_ARM11_TEST_2\",\n  \"scope\": \"Native 3DS homebrew, captured images; no DS game or TwlBg execution\",\n");
    fprintf(file,"  \"cpu_speedup_requested\": false,\n  \"actual_cpu_frequency_measured\": false,\n  \"vram_backbuffers_requested\": false,\n  \"framebuffer_kind\": \"libctru linear RAM\",\n  \"model\": %u,\n",model);
    fprintf(file,"  \"memory_permission_checks\": %u,\n",memory_checks);
    fprintf(file,"  \"frames\": %u,\n  \"source_images\": %u,\n  \"asset_fnv1a\": \"%08lx\",\n",frames,image_count,(unsigned long)asset_checksum);
    fprintf(file,"  \"session_wall_us\": %llu,\n",
            (unsigned long long)(session_ticks*1000000u/SYSCLOCK_ARM11));
    fprintf(file,"  \"popup_duration_frames\": %u,\n  \"previews\": %u,\n  \"panel_moves\": %u,\n  \"manual_closes\": %u,\n  \"suspends\": %u,\n  \"render_error\": %d,\n",
            POPUP_FRAMES,preview_requests,panel_moves,manual_closes,suspends,render_error);
    fprintf(file,"  \"copy_and_popup_us\": {\"mean\": %llu, \"max\": %lu, \"recent_p50\": %lu, \"recent_p95\": %lu},\n",
            frames?(unsigned long long)(copy_total/frames):0,(unsigned long)copy_max,
            (unsigned long)(n?copy_samples[n/2]:0),(unsigned long)(n?copy_samples[(n-1)*95/100]:0));
    fprintf(file,"  \"flush_us\": {\"mean\": %llu, \"max\": %lu, \"recent_p95\": %lu},\n",
            frames?(unsigned long long)(flush_total/frames):0,(unsigned long)flush_max,
            (unsigned long)(n?flush_samples[(n-1)*95/100]:0));
    fprintf(file,"  \"timing_scope\": \"Both complete frame copies plus popup; footer and SD IO excluded. Cache flush timed separately. Wall duration is not a photometric measurement.\",\n  \"event_overflow\": %u,\n  \"events\": [",event_overflow);
    for(unsigned i=0;i<event_count;++i) {
        const Event *e=&events[i];
        fprintf(file,"%s\n    {\"kind\": \"%s\", \"initial_panel\": %u, \"start_frame\": %lu, \"end_frame\": %lu, \"drawn_frames\": %lu, \"wall_us\": %lu, \"end_reason\": \"%s\"}",
                i?",":"",e->kind,e->panel,(unsigned long)e->start_frame,(unsigned long)e->end_frame,
                (unsigned long)e->drawn_frames,(unsigned long)microseconds(e->end_tick-e->start_tick),e->end_reason?e->end_reason:"unknown");
    }
    fprintf(file,"\n  ],\n  \"overlay_hardware_compatibility_proven\": false\n}\n");
    int ok=!ferror(file);if(fclose(file))ok=0;
    snprintf(path,sizeof(path),"%s/top.bgr",directory);if(top&&!save_file(path,top,TOP_BYTES))ok=0;
    snprintf(path,sizeof(path),"%s/bottom.bgr",directory);if(bottom&&!save_file(path,bottom,BOTTOM_BYTES))ok=0;
    return ok;
}

static void error_screen(const char *message) {
    consoleInit(GFX_TOP,NULL);printf("RA ARM11 Test\n\n%s\n\nSTART: sair\n",message);
    while(aptMainLoop()) {
        hidScanInput();if(hidKeysDown()&KEY_START)break;
        gfxFlushBuffers();gfxSwapBuffers();gspWaitForVBlank();
    }
}
int main(void) {
    osSetSpeedupEnable(false);
    /* Software compositor needs CPU-writable buffers. gfxInitDefault also uses
     * linear RAM. The VRAM-backed variant faulted in this homebrew process. */
    gfxInit(GSP_BGR8_OES,GSP_BGR8_OES,false);
    gfxSet3D(false);gfxSetWide(false);
    unsigned image_count=0;u32 checksum=0;
    u8 *assets=load_frames(&image_count,&checksum);
    if(!assets){error_screen("Erro em frames.bin. Reabra FTP.");gfxExit();return 1;}
    memcpy(label_strip,ra_text_render("TESTE ARM11 - CAPTURAS DS",
           "A POPUP X TELA B FECHA START SAI"),sizeof(label_strip));
    memcpy(stats_strip,ra_text_render("Medindo copia e texto...",
           "START salva medidas no SD"),sizeof(stats_strip));
    aptHook(&hook,apt_event,NULL);
    u64 session_start=svcGetSystemTick();
    begin_event("startup_test","RETROACHIEVEMENTS","Teste de desenho no ARM11");
    u8 *last_top=NULL,*last_bottom=NULL;
    while(aptMainLoop()) {
        hidScanInput();u32 keys=hidKeysDown();
        if(keys&KEY_START)break;
        if(keys&KEY_A){++preview_requests;begin_event("preview_test","POPUP TEST","Sem conquista registrada");}
        if(keys&KEY_B){++manual_closes;close_event("manual");}
        if(keys&KEY_X){++panel_moves;panel=panel==GFX_BOTTOM?GFX_TOP:GFX_BOTTOM;}
        unsigned image=(frames/90)%image_count;
        const u8 *source=assets+(size_t)image*FRAME_BYTES;
        u16 tw,th,bw,bh;
        u8 *top=gfxGetFramebuffer(GFX_TOP,GFX_LEFT,&tw,&th);
        u8 *bottom=gfxGetFramebuffer(GFX_BOTTOM,GFX_LEFT,&bw,&bh);
        if(!top || !bottom || tw!=240 || th!=400 || bw!=240 || bh!=320){render_error=-2;break;}
        if(!cpu_writable(top,TOP_BYTES) || !cpu_writable(bottom,BOTTOM_BYTES)){render_error=-4;break;}
        u64 start=svcGetSystemTick();
        int a=ra_postcompose(source,TOP_BYTES,top,TOP_BYTES,400,240,RA_CTR_BGR,popup_strip,12,
                             frames_left&&panel==GFX_TOP);
        int b=ra_postcompose(source+TOP_BYTES,BOTTOM_BYTES,bottom,BOTTOM_BYTES,320,240,
                             RA_CTR_BGR,popup_strip,12,frames_left&&panel==GFX_BOTTOM);
        u32 copy_us=microseconds(svcGetSystemTick()-start);
        if(a||b){render_error=-3;break;}
        if(frames%30==0) {
            char timing[40];snprintf(timing,sizeof(timing),"Copia %luus Max %luus",
                                    (unsigned long)copy_us,(unsigned long)copy_max);
            memcpy(stats_strip,ra_text_render(timing,"START salva medidas no SD"),sizeof(stats_strip));
        }
        stamp(top,400,220,label_strip);stamp(bottom,320,220,stats_strip);
        start=svcGetSystemTick();gfxFlushBuffers();
        u32 flush_us=microseconds(svcGetSystemTick()-start);
        copy_total+=copy_us;flush_total+=flush_us;
        if(copy_us>copy_max)copy_max=copy_us;
        if(flush_us>flush_max)flush_max=flush_us;
        copy_samples[sample_count%SAMPLE_COUNT]=copy_us;
        flush_samples[sample_count%SAMPLE_COUNT]=flush_us;++sample_count;
        gfxSwapBuffers();gspWaitForVBlank();
        last_top=top;last_bottom=bottom;
        if(frames_left && event_count && !events[event_count-1].end_reason)
            ++events[event_count-1].drawn_frames;
        ++frames;
        if(frames_left && --frames_left==0 && event_count && !events[event_count-1].end_reason) {
            events[event_count-1].end_reason="expired";events[event_count-1].end_frame=frames;
            events[event_count-1].end_tick=svcGetSystemTick();
        }
    }
    session_ticks=svcGetSystemTick()-session_start;
    close_event("exit");aptUnhook(&hook);
    int saved=save_report(checksum,image_count,last_top,last_bottom);
    free(assets);
    if(!saved && !render_error)error_screen("Erro salvando relatorio. Reabra FTP.");
    /* On a denied surface, return to Homebrew Launcher after saving the report.
     * Do not ask consoleInit to draw an error onto that same denied surface. */
    gfxExit();return render_error?1:0;
}
