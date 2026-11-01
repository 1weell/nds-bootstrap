/* Mario Kart AMCE observer. No game addresses or scratch patches assumed.
 * Mode irq runs the host compositor at the first IRQ-mode exit in VBlank.
 * This is a model of ordering, not nds-bootstrap or its hardware CPU cost. */
#include "NDS.h"
#include "Args.h"
#include <fstream>
#include <vector>
#include <set>
#include <tuple>
#include <cstdio>
#include <cstring>
using namespace melonDS;
static unsigned Frame, First=120, Preview=900;
static FILE *Trace, *Metrics, *Lines;
static bool Drawing, PaintEnabled, Late, Upload;
static std::string Prefix;
extern "C" {
void ResearchOverlayInit(void);
void ResearchOverlayTick(int);
void ResearchOverlayRefresh(void);
unsigned ResearchOwnedObjects(void);
unsigned ResearchFramesLeft(void), ResearchSprites(void), ResearchLayer(void);
extern unsigned raOverlayShows,raOverlayDenied,raOverlayEvicted,raOverlayRedrawn;
extern unsigned ResearchAdmissionFlags,ResearchDisabledOam,ResearchUsedSlots;
extern unsigned char raOverlayRow;
}
static std::set<std::tuple<unsigned,unsigned,unsigned>> Bursts;

static void paint(NDS& n,bool refresh=false) {
    static unsigned last=~0u;
    if(!refresh&&last==Frame)return;
    if(!refresh)last=Frame;
    u8* io=(u8*)0x04000000;
    *(u16*)(io+6)=n.GPU.VCount;*(u16*)(io+0x304)=n.PowerControl9;
    *(u32*)(io+0x1000)=n.GPU.GPU2D_B.DispCnt;
    for(unsigned i=0;i<4;++i) {
        *(u16*)(io+0x1008+2*i)=n.GPU.GPU2D_B.BGCnt[i];
        *(u16*)(io+0x1010+4*i)=n.GPU.GPU2D_B.BGXPos[i];
        *(u16*)(io+0x1012+4*i)=n.GPU.GPU2D_B.BGYPos[i];
    }
    *(u16*)(io+0x1048)=n.GPU.GPU2D_B.WinCnt[0]|(n.GPU.GPU2D_B.WinCnt[1]<<8);
    *(u16*)(io+0x104a)=n.GPU.GPU2D_B.WinCnt[2]|(n.GPU.GPU2D_B.WinCnt[3]<<8);
    *(u16*)(io+0x106c)=n.GPU.MasterBrightnessB;
    const unsigned offsets[]={0,1,2,3,4,5,6,8,9};
    for(unsigned i=0;i<9;++i)io[0x240+offsets[i]]=n.GPU.VRAMCNT[i];
    memcpy((void*)0x05000000,n.GPU.Palette,2048);
    memcpy((void*)0x07000000,n.GPU.OAM,2048);
    if(Frame==Preview&&!refresh) {
        FILE* f=fopen((Prefix+"-preview-oam.bin").c_str(),"wb");
        fwrite(n.GPU.OAM+0x400,1,1024,f);fclose(f);
    }
    for(unsigned i=0;i<0x4000;i+=4)*(u32*)(0x06600000+i)=n.ARM9Read32(0x06600000+i);
    for(unsigned i=0;i<0x20000;i+=4)*(u32*)(0x06200000+i)=n.ARM9Read32(0x06200000+i);
    std::vector<u8> oldio(io,io+0x3000);
    std::vector<u32> obj((u32*)0x06600000,(u32*)0x06604000);
    std::vector<u32> bg((u32*)0x06200000,(u32*)0x06220000);
    Drawing=true;
    if(refresh)ResearchOverlayRefresh();
    else ResearchOverlayTick(Frame==First?1:Frame==Preview?2:0);
    for(unsigned i=0;i<2048;i+=2) {
        if(*(u16*)(0x07000000+i)!=*(u16*)&n.GPU.OAM[i])n.ARM9Write16(0x07000000+i,*(u16*)(0x07000000+i));
        if(*(u16*)(0x05000000+i)!=*(u16*)&n.GPU.Palette[i])n.ARM9Write16(0x05000000+i,*(u16*)(0x05000000+i));
    }
    for(unsigned i=0;i<obj.size();++i)if(obj[i]!=((u32*)0x06600000)[i])n.ARM9Write32(0x06600000+i*4,((u32*)0x06600000)[i]);
    for(unsigned i=0;i<bg.size();++i)if(bg[i]!=((u32*)0x06200000)[i])n.ARM9Write32(0x06200000+i*4,((u32*)0x06200000)[i]);
    for(unsigned i=0x1000;i<0x1020;i+=2)if(*(u16*)(io+i)!=*(u16*)&oldio[i])n.ARM9Write16(0x04000000+i,*(u16*)(io+i));
    fprintf(Trace,"%u,%u,%s,%08x,0,0,%02x,0\n",Frame,unsigned(n.GPU.VCount),refresh?"refresh":"paint",n.ARM9.R[15],n.ARM9.CPSR&0x3f);
    Drawing=false;
}
namespace melonDS {
bool ResearchIRQActive=false;
bool ResearchRefreshPending=false;
void ResearchInstruction(NDS& n,u32 pc) {
    if(ResearchRefreshPending) { ResearchRefreshPending=false;paint(n,true); }
    const bool irq=(n.ARM9.CPSR&31)==0x12;
    if(irq==ResearchIRQActive)return;
    ResearchIRQActive=irq;
    if(Trace)fprintf(Trace,"%u,%u,%s,%08x,0,0,%02x,%08x\n",Frame,unsigned(n.GPU.VCount),irq?"irq_enter":"irq_exit",pc,n.ARM9.CPSR&0x3f,n.ARM9.R[14]);
    if(!irq&&(n.ARM9.CPSR&31)==0x1f&&PaintEnabled&&!Late
        &&n.GPU.VCount>=192&&n.GPU.VCount<263)paint(n);
}
void ResearchScanline(NDS& n,u32) {
    if(Late&&n.GPU.VCount==230)paint(n); /* timing oracle, never a shipping hook */
    if(n.GPU.VCount!=7||!Metrics)return;
    auto& b=n.GPU.GPU2D_B;
    memcpy((void*)0x07000400,n.GPU.OAM+0x400,1024);
    unsigned parked=0;
    for(unsigned i=0;i<128;++i) {
        const u16 a=*(u16*)&n.GPU.OAM[0x400+8*i];
        if((a&255)==192 && !(a&0x100))++parked;
    }
    fprintf(Metrics,"%u,%08x,%04x,%04x,%04x,%04x,%04x,%04x,%04x,%04x,%04x,%u,%u,%u,%u,%u,%u,%u,%u,%u,%u",
        Frame,b.DispCnt,b.BGCnt[0],b.BGCnt[1],b.BGCnt[2],b.BGCnt[3],
        *(u16*)&n.GPU.Palette[0x5e2],*(u16*)&n.GPU.Palette[0x5e4],
        *(u16*)&n.GPU.Palette[0x7e2],*(u16*)&n.GPU.Palette[0x7e4],
        b.BlendCnt, b.EVA,b.EVB,b.EVY,raOverlayShows,raOverlayDenied,raOverlayEvicted,
        raOverlayRedrawn,ResearchFramesLeft(),ResearchSprites(),ResearchLayer());
    for(unsigned i=0;i<9;++i)fprintf(Metrics,",%02x",n.GPU.VRAMCNT[i]);
    fprintf(Metrics,",%u,%u,%u,%u,%04x,%04x,%u,%u,%u,%u\n",ResearchAdmissionFlags,ResearchDisabledOam,
        ResearchUsedSlots,raOverlayRow,n.PowerControl9,n.GPU.MasterBrightnessB,
        parked,unsigned(b.BGXPos[0]),unsigned(b.BGYPos[0]),ResearchOwnedObjects());
}
void ResearchTrace(NDS& n,u32 addr,u32 value,unsigned size) {
    if(!Trace||Drawing)return;
    /* Idealized observer of the observed forward full-OAM copy's final word.
     * This does not establish a safe bootloader signature or shipping hook. */
    if(Upload&&addr<=0x070007fc&&addr+size>=0x07000800)ResearchRefreshPending=true;
    const bool pal=(addr<=0x050005e4&&addr+size>0x050005e2)||(addr<=0x050007e4&&addr+size>0x050007e2);
    const bool io=(addr>=0x04001000&&addr<0x04001070)||(addr>=0x04000240&&addr<0x0400024a)||addr==0x04000304;
    const bool mem=(addr>=0x07000400&&addr<0x07000800)||(addr>=0x06600000&&addr<0x06604000)||(addr>=0x06200000&&addr<0x06210000);
    if(!pal&&!io&&!mem)return;
    if(mem&&!Bursts.emplace(addr&~0x7ffu,n.ARM9.R[15],unsigned(n.GPU.VCount)).second)return;
    fprintf(Trace,"%u,%u,write,%08x,%08x,%08x,%02x,%08x\n",Frame,unsigned(n.GPU.VCount),n.ARM9.R[15],addr,value,n.ARM9.CPSR&0x3f,n.ARM9.R[14]);
}
}
static void screenshot(NDS& n) {
    void* top;void* bottom;if(!n.GPU.GetFramebuffers(&top,&bottom))return;
    const std::string name=Prefix+"-frame-"+std::to_string(Frame)+".ppm";
    FILE* f=fopen(name.c_str(),"wb");fprintf(f,"P6\n256 384\n255\n");
    for(void* p:{top,bottom})for(unsigned i=0;i<256*192;++i) {
        u32 c=((u32*)p)[i];u8 rgb[]={u8(c>>16),u8(c>>8),u8(c)};fwrite(rgb,1,3,f);
    }
    fclose(f);
}
int main(int argc,char** argv) {
    if(argc<5){fprintf(stderr,"ROM frames trace|irq|late|upload output-prefix [startup-frame preview-frame save-path]\n");return 2;}
    Late=std::string(argv[3])=="late";
    Upload=std::string(argv[3])=="upload";
    PaintEnabled=Late||Upload||std::string(argv[3])=="irq";Prefix=argv[4];
    if(argc>5)First=atoi(argv[5]);if(argc>6)Preview=atoi(argv[6]);
    ResearchOverlayInit();
    std::ifstream f(argv[1],std::ios::binary);std::vector<u8> rom((std::istreambuf_iterator<char>(f)),{});
    auto cart=NDSCart::ParseROM(rom.data(),rom.size());if(!cart)return 3;
    auto owner=std::make_unique<NDS>();NDS& n=*owner;
    n.SetNDSCart(std::move(cart));n.Reset();
    if(argc>7) {
        std::ifstream sf(argv[7],std::ios::binary);std::vector<u8> save((std::istreambuf_iterator<char>(sf)),{});
        if(save.empty())return 4;n.SetNDSSave(save.data(),save.size());
    }
    n.SetupDirectBoot("Mario Kart DS.nds");n.Start();
    Trace=fopen((Prefix+"-trace.csv").c_str(),"w");
    fprintf(Trace,"frame,line,event,pc,address,value,mode,lr\n");
    Metrics=fopen((Prefix+"-metrics.csv").c_str(),"w");
    fprintf(Metrics,"frame,display,bg0,bg1,bg2,bg3,bg_ink,bg_shadow,obj_ink,obj_shadow,blend,eva,evb,evy,shows,denied,evicted,repairs,left,sprites,layer,A,B,C,D,E,F,G,H,I,admission_flags,disabled_oam,used_slots,row,power,brightness,parked_y192,bg0_x,bg0_y,owned_oam\n");
    Lines=fopen((Prefix+"-lines.bin").c_str(),"wb");
    for(Frame=0;Frame<unsigned(atoi(argv[2]));++Frame) {
        Bursts.clear();u32 keys=0xfff;
        if(Frame>360&&Frame%180>=10&&Frame%180<14)keys&=~1u;
        n.SetKeyMask(keys);n.RunFrame();
        void* top;void* bottom;
        if(n.GPU.GetFramebuffers(&top,&bottom))for(void* p:{top,bottom})for(unsigned y=0;y<192;++y) {
            uint64_t h=1469598103934665603ULL;
            for(unsigned x=0;x<256;++x)h=(h^((u32*)p)[y*256+x])*1099511628211ULL;
            fwrite(&h,sizeof(h),1,Lines);
        }
        if(Frame%120==0||Frame==First+60||Frame==Preview+60) {
            fprintf(stderr,"frame %u sub %08x pc %08x\n",Frame,n.GPU.GPU2D_B.DispCnt,n.ARM9.R[15]);screenshot(n);
        }
    }
    screenshot(n);fclose(Trace);fclose(Metrics);fclose(Lines);
}
