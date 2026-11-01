/* GPL-3.0. Host postcomposition only. No firmware hook or emulated CPU cost.
 * Link against the pinned, instrumented melonDS core from the Mario Kart study.
 */
#include "NDS.h"
#include "Args.h"
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <vector>
extern "C" {
#include "postcompose.h"
const void *ra_text_render(const char *, const char *);
}
using namespace melonDS;
namespace melonDS {
bool ResearchIRQActive=false, ResearchRefreshPending=false;
void ResearchInstruction(NDS&,u32) {}
void ResearchScanline(NDS&,u32) {}
void ResearchTrace(NDS&,u32,u32,unsigned) {}
}
static std::vector<u8> read(const char *path) {
    std::ifstream input(path,std::ios::binary);
    return std::vector<u8>((std::istreambuf_iterator<char>(input)),{});
}
int main(int argc,char **argv) {
    if(argc!=6) {
        fprintf(stderr,"ROM SAVE FRAMES OUTPUT_LINES OUTPUT_METRICS\n");return 2;
    }
    auto rom=read(argv[1]),save=read(argv[2]);
    auto cart=NDSCart::ParseROM(rom.data(),rom.size());
    if(!cart||save.empty())return 3;
    auto owner=std::make_unique<NDS>();NDS& n=*owner;
    n.SetNDSCart(std::move(cart));n.Reset();n.SetNDSSave(save.data(),save.size());
    n.SetupDirectBoot("Mario Kart DS.nds");n.Start();
    // Exclusive creation: do not replace previous research evidence.
    FILE *lines=fopen(argv[4],"wbx"),*metrics=fopen(argv[5],"wx");
    if(!lines||!metrics)return 4;
    fprintf(metrics,"frame,active,changed_pixels,outside_band,source_changed\n");
    std::vector<u8> source(256*192*3),out(source.size());
    std::vector<u32> before(256*192*2);
    alignas(4) uint32_t strip[512]={};
    for(unsigned frame=0;frame<unsigned(atoi(argv[3]));++frame) {
        u32 keys=0xfff;
        if(frame>360&&frame%180>=10&&frame%180<14)keys&=~1u;
        n.SetKeyMask(keys);n.RunFrame();
        void *top,*bottom;
        if(!n.GPU.GetFramebuffers(&top,&bottom))return 5;
        memcpy(before.data(),top,256*192*4);
        memcpy(before.data()+256*192,bottom,256*192*4);
        for(void *p:{top,bottom})for(unsigned y=0;y<192;++y) {
            uint64_t h=1469598103934665603ULL;
            for(unsigned x=0;x<256;++x)h=(h^((u32*)p)[y*256+x])*1099511628211ULL;
            if(fwrite(&h,sizeof(h),1,lines)!=1)return 6;
        }
        if(frame==320||frame==900) {
            const void *text=ra_text_render(frame==320?"RETROACHIEVEMENTS":"POPUP TEST",
                frame==320?"Ready: Mario Kart DS":"No achievement awarded");
            memcpy(strip,text,sizeof(strip));
        }
        bool active=(frame>=320&&frame<500)||(frame>=900&&frame<1080);
        for(unsigned i=0;i<256*192;++i) {
            u32 c=((u32*)bottom)[i];source[3*i]=u8(c>>16);
            source[3*i+1]=u8(c>>8);source[3*i+2]=u8(c);
        }
        if(ra_postcompose(source.data(),source.size(),out.data(),out.size(),
                          256,192,RA_ROWS_RGB,strip,8,active))return 7;
        unsigned changed=0,outside=0;
        for(unsigned y=0;y<192;++y)for(unsigned x=0;x<256;++x) {
            unsigned i=(y*256+x)*3;
            if(memcmp(&source[i],&out[i],3)) {
                ++changed;if(!active||y<8||y>=24)++outside;
            }
        }
        bool mutated=memcmp(before.data(),top,256*192*4)||
            memcmp(before.data()+256*192,bottom,256*192*4);
        fprintf(metrics,"%u,%u,%u,%u,%u\n",frame,unsigned(active),changed,outside,unsigned(mutated));
        if(mutated||outside||(active&&!changed))return 8;
        if(frame%240==0)fprintf(stderr,"postcompose host model frame %u\n",frame);
    }
    fclose(lines);fclose(metrics);return 0;
}
