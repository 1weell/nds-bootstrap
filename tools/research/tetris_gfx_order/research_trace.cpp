#include "NDS.h"
#include "Args.h"
#include <fstream>
#include <vector>
#include <map>
#include <tuple>
#include <cstdio>
#include <cstring>
using namespace melonDS;
static unsigned Frame;
static FILE* Trace;
static FILE* Metrics;
static FILE* Hashes;
static FILE* Lines;
static std::string Mode="trace";
static std::string Tag;
static bool AutoContinue;
static bool OverlayWriting;
extern "C" void ResearchOverlayInit(void);
extern "C" int ResearchRepairTiles;
namespace melonDS { bool ResearchMapPending=false; }
extern "C" void ResearchOverlayTick(int first);
extern "C" void ResearchOverlayRefresh(void);
extern "C" unsigned int raOverlayShows,raOverlayEvicted;
extern "C" unsigned short raOverlayHeld;
extern "C" unsigned char raOverlayRow;
static std::map<std::tuple<unsigned,unsigned,unsigned>,unsigned> Bursts;
static void paint(NDS& n,bool refresh=false) {
 static unsigned last=~0u;
 if(Frame<650||(!refresh&&Frame==last))return;
 if(!refresh)last=Frame;
 auto io=(u8*)0x04000000;
 *(u16*)(io+6)=n.GPU.VCount;*(u16*)(io+0x304)=n.PowerControl9;
 *(u32*)(io+0x1000)=n.GPU.GPU2D_B.DispCnt;
 for(unsigned i=0;i<4;i++) {
  *(u16*)(io+0x1008+2*i)=n.GPU.GPU2D_B.BGCnt[i];
  *(u16*)(io+0x1010+4*i)=n.GPU.GPU2D_B.BGXPos[i];
  *(u16*)(io+0x1012+4*i)=n.GPU.GPU2D_B.BGYPos[i];
 }
 *(u16*)(io+0x1048)=n.GPU.GPU2D_B.WinCnt[0]|(n.GPU.GPU2D_B.WinCnt[1]<<8);
 *(u16*)(io+0x104a)=n.GPU.GPU2D_B.WinCnt[2]|(n.GPU.GPU2D_B.WinCnt[3]<<8);
 *(u16*)(io+0x106c)=n.GPU.MasterBrightnessB;
 const unsigned offsets[]={0,1,2,3,4,5,6,8,9};
 for(unsigned i=0;i<9;i++)io[0x240+offsets[i]]=n.GPU.VRAMCNT[i];
 memcpy((void*)0x05000000,n.GPU.Palette,2048);
 memcpy((void*)0x07000000,n.GPU.OAM,2048);
 for(unsigned i=0;i<0x4000;i+=4)*(u32*)(0x06600000+i)=n.ARM9Read32(0x06600000+i);
 for(unsigned i=0;i<0x20000;i+=4)*(u32*)(0x06200000+i)=n.ARM9Read32(0x06200000+i);
 std::vector<u8> oldio(io,io+0x3000);
 std::vector<u32> oldobj((u32*)0x06600000,(u32*)0x06604000);
 std::vector<u32> oldbg((u32*)0x06200000,(u32*)0x06220000);
 OverlayWriting=true;
 int request=Frame==650||Frame==1250||Frame==1550;
 if(request&&Mode=="bgirq")request=2;
 if(refresh)ResearchOverlayRefresh();else ResearchOverlayTick(request);
 for(unsigned i=0;i<2048;i+=2) {
  if(*(u16*)(0x07000000+i)!=*(u16*)&n.GPU.OAM[i])n.ARM9Write16(0x07000000+i,*(u16*)(0x07000000+i));
  if(*(u16*)(0x05000000+i)!=*(u16*)&n.GPU.Palette[i])n.ARM9Write16(0x05000000+i,*(u16*)(0x05000000+i));
 }
 for(unsigned i=0;i<oldobj.size();i++)if(oldobj[i]!=((u32*)0x06600000)[i])n.ARM9Write32(0x06600000+i*4,((u32*)0x06600000)[i]);
 for(unsigned i=0;i<oldbg.size();i++)if(oldbg[i]!=((u32*)0x06200000)[i])n.ARM9Write32(0x06200000+i*4,((u32*)0x06200000)[i]);
 for(unsigned i=0x1000;i<0x1020;i+=2)if(*(u16*)(io+i)!=*(u16*)&oldio[i])n.ARM9Write16(0x04000000+i,*(u16*)(io+i));
 OverlayWriting=false;
}
namespace melonDS {
void ResearchIRQTrace(NDS& n,u32 pc) {
 if(ResearchMapPending){ResearchMapPending=false;paint(n,true);}
 if(pc==0x01fffb00&&Mode=="sdk") {paint(n,true);u32 lr=n.ARM9.R[14];for(unsigned r:{0u,1u,2u,3u,12u})n.ARM9.R[r]=0xDEADBEEF;n.ARM9.JumpTo(lr);return;}
 if(pc==0x01fffd00&&(Mode=="patched"||Mode=="split"||(Mode=="map"||Mode=="sdk"))) {
  paint(n,Mode=="split"||(Mode=="map"||Mode=="sdk"));const u32 lr=n.ARM9.R[14];
  for(unsigned r:{0u,1u,2u,3u,12u})n.ARM9.R[r]=0xDEADBEEF;
  n.ARM9.JumpTo(lr);return;
 }
 if(pc==0x01ff85ac) {
  if(Trace&&Frame>=650&&Frame<=655&&n.ARM9.R[5]==0x07000400)fprintf(Trace,"%u,%u,ffff0004,0,%08x,%08x,%02x,%08x,%08x,%08x\n",Frame,unsigned(n.GPU.VCount),n.ARM9.R[4],pc,n.ARM9.CPSR&0x3f,n.ARM9.R[14],n.ARM9.R[13],n.ARM9.R_IRQ[1]);
  if(Mode=="dma"&&n.ARM9.R[5]==0x07000400)paint(n);
  return;
 }
 static bool active=false;
 if(pc==(*(u32*)&n.ARM9.DTCM[8]&~1u))active=true;
 else if(!active)return;
 if(Trace&&Frame>=300)fprintf(Trace,"%u,%u,%08x,0,%08x,%08x,%02x,%08x,%08x,%08x\n",Frame,unsigned(n.GPU.VCount),pc==0x01ff8058?0xffff0002u:0xffff0001u,*(u32*)&n.ARM9.DTCM[8],pc,n.ARM9.CPSR&0x3f,n.ARM9.R[14],n.ARM9.R[13],n.ARM9.R_IRQ[1]);
 if(pc==0x01ff8058) { if(Mode=="irq"||Mode=="bgirq"||Mode=="split"||(Mode=="map"||Mode=="sdk"))paint(n);active=false; }
}
void ResearchScanline(NDS& n,u32 line) {
 if(line==200&&Mode=="late")paint(n);
 if(line==7&&Metrics&&Frame>=650) {
  u16* o=(u16*)(n.GPU.OAM+0x400);unsigned count=0;
  for(unsigned k=0;k<8;k++)if(o[(127-k)*4]==0x4008&&o[(127-k)*4+1]==(0x8000|k*32))count++;
  unsigned ink=0;unsigned boundary=32u<<((n.GPU.GPU2D_B.DispCnt>>20)&3);unsigned addr=0x06600000+(o[127*4+2]&1023)*boundary;
  for(unsigned j=0;j<2048;j+=4){u32 v=n.ARM9Read32(addr+j);for(unsigned z=0;z<8;z++)if((v>>(z*4))&15)ink++;}
  fprintf(Metrics,"%u,%u,%04x,%u,%u,%u,%u,%04x,%u\n",Frame,count,*(u16*)&n.GPU.Palette[0x600+2*241],raOverlayShows,raOverlayEvicted,raOverlayHeld,ink,n.GPU.GPU2D_B.BlendCnt,n.GPU.GPU2D_B.EVY);
 }
}
void ResearchTrace(NDS& n,u32 addr,u32 val,unsigned size) {
 if(!Trace||OverlayWriting)return;
 if(Mode=="map"&&addr>=0x04000240&&addr<=0x04000249)ResearchMapPending=true;
 bool oam=addr>=0x07000400&&addr<0x07000800;
 bool obj=addr>=0x06600000&&addr<0x06604000;
 bool researchvram=Frame>=748&&Frame<=751&&addr>=0x06000000&&addr<0x06900000;
 bool io=(addr>=0x04000240&&addr<=0x04000249)||addr==0x04000304||(addr>=0x04001000&&addr<0x04001070);
 bool pal=addr>=0x05000600&&addr<0x05000800;
 if(!oam&&!obj&&!io&&!pal&&!researchvram)return;
 if(Frame<300)return;
 unsigned region=researchvram?(addr&0xffffc000):oam?0x07000400:obj?0x06600000:pal?0x05000600:addr;
 auto key=std::make_tuple(region,unsigned(n.GPU.VCount),n.ARM9.R[15]);
 if(!io) { auto& count=Bursts[key];if(count++)return; }
 fprintf(Trace,"%u,%u,%08x,%u,%08x,%08x,%02x,%08x,%08x,%08x\n",Frame,unsigned(n.GPU.VCount),addr,size,val,n.ARM9.R[15],n.ARM9.CPSR&0x3f,n.ARM9.R[14],n.ARM9.R[13],n.ARM9.R_IRQ[1]);
}
}
static void screenshot(NDS& n,unsigned frame) {
 void* t;void* b;if(!n.GPU.GetFramebuffers(&t,&b))return;
 char path[128];snprintf(path,sizeof(path),"/tmp/ra-emulator-%s-frame-%u.ppm",Tag.c_str(),frame);
 FILE* f=fopen(path,"wb");fprintf(f,"P6\n256 384\n255\n");
 for(void* p:{t,b})for(unsigned i=0;i<256*192;++i) {
  u32 c=static_cast<u32*>(p)[i];unsigned char rgb[3]={static_cast<unsigned char>(c>>16),static_cast<unsigned char>(c>>8),static_cast<unsigned char>(c)};fwrite(rgb,1,3,f);
 }
 fclose(f);
}
int main(int argc,char** argv) {
 if(argc<2)return 2;
 if(argc>3)Mode=argv[3];
 if(argc>4)AutoContinue=std::string(argv[4])=="auto";
 Tag=Mode+(AutoContinue?"-auto":"-main");
 if(argc>5)Tag=argv[5];
 ResearchRepairTiles=(Mode=="map"||Mode=="sdk");ResearchOverlayInit();
 std::ifstream f(argv[1],std::ios::binary);std::vector<u8> rom((std::istreambuf_iterator<char>(f)),{});
 auto cart=NDSCart::ParseROM(rom.data(),rom.size());if(!cart){fprintf(stderr,"bad ROM\n");return 3;}
 auto owner=std::make_unique<NDS>();NDS& n=*owner;n.SetNDSCart(std::move(cart));n.Reset();n.SetupDirectBoot("Tetris DS.nds");n.Start();
 Trace=fopen(("/tmp/ra-tetris-"+Tag+"-trace.csv").c_str(),"w");fprintf(Trace,"frame,line,address,size,value,pc,cpsr,lr,sp,irq_lr\n");
 Metrics=fopen(("/tmp/ra-overlay-"+Tag+"-metrics.csv").c_str(),"w");fprintf(Metrics,"frame,sprites_at_line7,ink_palette,shows,evicted,held,tile_nonzero_nibbles,blendcnt,blendy\n");
 Hashes=fopen(("/tmp/ra-overlay-"+Tag+"-hashes.csv").c_str(),"w");fprintf(Hashes,"frame,full_hash,outside_band_hash,row,shows,evicted,held,power,brightness,dispcnt,blendcnt,blendy\n");
 Lines=fopen(("/tmp/ra-overlay-"+Tag+"-lines.bin").c_str(),"wb");
 unsigned total=argc>2?atoi(argv[2]):1200;
 for(Frame=0;Frame<total;++Frame) {
  Bursts.clear();
  if(Frame==640&&(Mode=="patched"||Mode=="split"||(Mode=="map"||Mode=="sdk"))) {
   if(*(u32*)&n.ARM9.ITCM[0x5a8]!=0xE28DD004||*(u32*)&n.ARM9.ITCM[0x5ac]!=0xE8BD80F0){fprintf(stderr,"epilogue signature mismatch\n");return 5;}
   std::ifstream sf("/tmp/ra-dma-epilogue-live.bin",std::ios::binary);std::vector<u8> stub((std::istreambuf_iterator<char>(sf)),{});
   if(stub.empty()||stub.size()>256)return 6;
   if(Mode=="sdk") {
    if(n.ARM9Read32(0x02001bbc)!=0xE28DD004||n.ARM9Read32(0x02001bc0)!=0xE8BD8000)return 7;
    std::ifstream vf("/tmp/ra-vram-epilogue-live.bin",std::ios::binary);std::vector<u8> vs((std::istreambuf_iterator<char>(vf)),{});
    if(vs.empty()||vs.size()>256)return 8;
    memcpy(n.ARM9.ITCM+0x7c00,vs.data(),vs.size());*(u32*)&n.ARM9.ITCM[0x7b00]=0xE12FFF1E;
    n.ARM9Write32(0x02001bbc,0xE51FF004);n.ARM9Write32(0x02001bc0,0x01FFFC00);
   }
   memcpy(n.ARM9.ITCM+0x7e00,stub.data(),stub.size());
   *(u32*)&n.ARM9.ITCM[0x7d00]=0xE12FFF1E;
   *(u32*)&n.ARM9.ITCM[0x5a8]=0xE51FF004;*(u32*)&n.ARM9.ITCM[0x5ac]=0x01FFFE00;
  }
  // Tap A periodically after title startup, selecting default single-player modes.
  u32 keys=0xfff;if(Frame>360&&(Frame<600||AutoContinue)&&Frame%180>=10&&Frame%180<14)keys&=~1u;
  n.SetKeyMask(keys);n.RunFrame();
  void* top;void* bottom;
  if(n.GPU.GetFramebuffers(&top,&bottom)) {
   uint64_t full=1469598103934665603ULL,outside=full;
   uint64_t linehashes[384];unsigned linenum=0;
   for(void* p:{top,bottom})for(unsigned i=0;i<256*192;i++) {
    u32 color=static_cast<u32*>(p)[i];full=(full^color)*1099511628211ULL;
    if(i%256==0)linehashes[linenum]=1469598103934665603ULL;
    linehashes[linenum]=(linehashes[linenum]^color)*1099511628211ULL;
    if(i%256==255)linenum++;
    if(i/256<8||i/256>=24)outside=(outside^color)*1099511628211ULL;
   }
   fprintf(Hashes,"%u,%016llx,%016llx,%u,%u,%u,%u,%04x,%04x,%08x,%04x,%u\n",Frame,(unsigned long long)full,(unsigned long long)outside,raOverlayRow,raOverlayShows,raOverlayEvicted,raOverlayHeld,n.PowerControl9,n.GPU.MasterBrightnessB,n.GPU.GPU2D_B.DispCnt,n.GPU.GPU2D_B.BlendCnt,n.GPU.GPU2D_B.EVY);
   fwrite(linehashes,sizeof(linehashes),1,Lines);
  }
  if(Frame==749||Frame==750||Frame==751||Frame==780||Frame==800||Frame==820||Frame==1300||Frame==1600)screenshot(n,Frame);
  if(Frame%120==0){fprintf(stderr,"frame %u pc %08x sub %08x pow %04x\n",Frame,n.ARM9.R[15],n.GPU.GPU2D_B.DispCnt,n.PowerControl9);screenshot(n,Frame);}
 }
 screenshot(n,Frame);fclose(Trace);Trace=nullptr;fclose(Metrics);Metrics=nullptr;fclose(Hashes);fclose(Lines);
 FILE* out=fopen("/tmp/ra-tetris-mainram.bin","wb");fwrite(n.MainRAM,1,0x400000,out);fclose(out);
 out=fopen("/tmp/ra-tetris-dtcm.bin","wb");fwrite(n.ARM9.DTCM,1,0x4000,out);fclose(out);
 out=fopen("/tmp/ra-tetris-itcm.bin","wb");fwrite(n.ARM9.ITCM,1,0x8000,out);fclose(out);
 fprintf(stderr,"finished %u frames dtcm=%08x\n",Frame,n.ARM9.DTCMBase);
}
