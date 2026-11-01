#!/usr/bin/env python3
"""Compiled ARM11 instruction tests. Cache/GPU/LCD/RTC timing remain fixtures."""
import argparse,binascii,json,re,struct,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'tools/research/twlbg_postcompose'))
from extract import extract
from test_payload import PayloadMachine
from unicorn.arm_const import UC_ARM_REG_SP
RTC=0x1ec47100
SOURCE=0x1f300000
SIZE=320*240*3
TICKS=268123480
GRAY=bytes([100])*SIZE

class Console:
    def __init__(self,build):
        self.manifest=json.loads((build/'manifest.json').read_text())
        self.symbols={k:int(v,16) for k,v in self.manifest['symbols'].items()}
        code,_=extract((build/'TwlBg.cxi').read_bytes())
        self.m=PayloadMachine(code);self.now=0;self.tick_step=0
        self.m.u.mem_map(0x1ec47000,0x1000);self.m.u.mem_map(0x1ed02000,0x1000)
        self.m.run(int(self.manifest['native_payload_source'],16),0x100000,0x281cc)
        self.m.run(0x102970) # Original VRAM allocator, not a synthetic free-address picker.
        self.m.word(0x120ef4,0xffff8001)
        self.object=0x133000;self.m.word(0x12cb68,self.object)
        self.surface(SOURCE)
        self.presented=SOURCE;self.present_args=None
        def publish(m):
            sp=m.u.reg_read(UC_ARM_REG_SP)
            self.present_args=tuple(m.reg(i) for i in range(4))+tuple(m.word(sp+i*4) for i in range(3))
            screen,index,left,right,stride,fmt,select=self.present_args
            if screen==1:
                self.presented=left;m.word(0x1ef00568+(index&1)*4,left-0x07000000)
            m.ret(0x1234)
        self.m.stubs[0x1088c0]=publish
        def ticks(m):
            value=self.now;self.now+=self.tick_step
            m.reg(1,value>>32);m.ret(value&0xffffffff)
        self.m.stubs[self.symbols['ra_ticks']&~1]=ticks
        self.m.u.mem_write(0x1ed02a04,struct.pack('<I',0x01020304))
    def surface(self,base,height=1024):
        for offset,value in ((4,base),(8,0x8051),(12,240),(16,height)):
            self.m.word(self.object+offset,value)
    def step(self,command=None,data=0,frame=GRAY,screen=1,stride=720,format=0x301,left=SOURCE,index=0,select=0,frame_base=SOURCE):
        self.m.u.mem_write(RTC,b'\0\0') # fixture completes preceding latch
        if command is not None:self.m.u.mem_write(RTC+0x12,bytes((data,command)))
        if screen==1:self.m.u.mem_write(frame_base,frame)
        assert self.m.run(self.symbols['ra_present'],screen,index,left,0,stride,format,select,count=4000000)==0x1234
        assert bytes(self.m.u.mem_read(0x1ed02a04,4))==struct.pack('<I',0x01020304)
        return self.m.u.mem_read(RTC+0x13,1)[0]
    def title(self):return bytes(self.m.u.mem_read(self.symbols['ra_display_title'],96)).split(b'\0')[0].decode('utf-8')
    def image(self):return bytes(self.m.u.mem_read(self.presented,SIZE))
    def stats(self):
        data=bytearray()
        for i in range(198):
            assert self.step(0x57,i,screen=0)==0xce
            data.append(self.m.u.mem_read(RTC+0x12,1)[0])
        assert data[:4]==b'AST2' and binascii.crc_hqx(data[:-2],0xffff)==struct.unpack_from('<H',data,len(data)-2)[0]
        return struct.unpack('<48I',data[4:-2])
    def diag(self):return struct.unpack('<20I',self.m.u.mem_read(self.symbols['ra_diagnostics'],80))
    def send(self,type,sequence,title='',session=77,id=0,flags=12,corrupt=False):
        text=title.encode('utf-8')
        wire=struct.pack('<2sBBBBH4I',b'RA',1,type,flags,len(text),0,session,sequence,42,id)+text
        wire+=struct.pack('<H',binascii.crc_hqx(wire,0xffff))
        if corrupt:wire=wire[:-1]+bytes((wire[-1]^1,))
        assert self.step(0x51,len(wire))==0xc8
        for i,byte in enumerate(wire):assert self.step(0x52+(i&1),byte)==0xd0+(i&1)
        return self.step(0x54)

def typed(build):
    c=Console(build);c.step();assert c.image()==GRAY and not c.title()
    assert c.step(0x50,1)==0xc7
    assert c.step(0x56,0xa5)==0xcd and c.m.u.mem_read(RTC+0x12,1)[0]==0
    assert c.send(1,1)==0xca
    assert c.send(2,2,'Kirby: Squeak Squad')==0xca and c.title()=='Kirby: Squeak Squad'
    statistics=c.stats();assert statistics[:2]==(0x301,720)
    assert statistics[7]>0 and statistics[10:12]==(0,0) and statistics[12]!=0 # composited, errors, owned pool
    changed=[i for i,(a,b) in enumerate(zip(GRAY,c.image())) if a!=b]
    clean=[e for e in c.m.events if e['event']=='cache' and e['svc']=='0x53'][-1]
    assert clean['r1']==c.presented and clean['r2']==SIZE and max(changed)<clean['r2']
    assert any(i>=172800 for i in changed)
    assert bytes(c.m.u.mem_read(SOURCE,SIZE))==GRAY,'GPU source must never receive popup pixels'
    pool=statistics[12]
    for i in range(8):
        old=[c.m.word(0x1ef00568),c.m.word(0x1ef0056c)]
        held={p:bytes(c.m.u.mem_read(p+0x07000000,SIZE)) for p in old if 0x18000000<=p<0x18600000}
        c.step(index=i&1,select=i&1)
        assert c.presented not in (SOURCE,0)
        assert all(not (c.presented-0x07000000<=p<c.presented-0x07000000+SIZE) for p in old)
        assert all(bytes(c.m.u.mem_read(p+0x07000000,SIZE))==pixels for p,pixels in held.items())
        assert c.present_args[0:2]==(1,i&1) and c.present_args[4:]==(720,0x301,i&1)
        # A later producer write must not erase the already published popup.
        shown=c.image();c.m.u.mem_write(SOURCE,bytes([19])*SIZE);assert c.image()==shown
        assert pool<=c.presented<=pool+2*SIZE
    # Cropped viewport need not begin at a cache-line boundary. Its full rounded
    # read span must remain within the validated image descriptor.
    c.step(left=SOURCE+3);assert c.presented!=SOURCE+3
    invalidation=[e for e in c.m.events if e['event']=='cache' and e['svc']=='0x52'][-1]
    assert invalidation['r1']==SOURCE and invalidation['r2']==SIZE+32
    c.now=3*TICKS;assert c.send(3,3,'Spark',id=10)==0xca and c.title()=='Spark'
    assert c.send(3,4,'Fire',id=11)==0xca and c.title()=='Spark'
    c.now=7*TICKS;c.step();assert c.title()=='Fire'
    shown=c.diag()[4];assert c.send(3,4,'Fire',id=11)==0xca
    assert c.diag()[4]==shown and c.diag()[13]>=1
    assert c.send(3,5,'Corrupted',id=12,corrupt=True)==0xcb
    c.now=11*TICKS;c.step();assert c.image()==GRAY and not c.title()
    title='Ação: '+('Long achievement title / '*3)
    assert c.send(3,5,title,id=12)==0xca and c.title()==title
    initial=c.image();c.now+=2*TICKS;c.step();assert c.title()==title and c.image()!=initial
    for kwargs in ({'screen':0},{'format':0},{'stride':1536},{'left':0x1f5ffff0}):
        c.step(**kwargs)
        if kwargs.get('screen',1)==1:assert c.presented==kwargs.get('left',SOURCE)
        else:assert c.present_args[0]==0 and c.present_args[2]==SOURCE
        assert bytes(c.m.u.mem_read(SOURCE,SIZE))==GRAY
    assert c.send(1,1,session=78,flags=0)==0xca and c.image()==GRAY and not c.title()
    assert c.send(3,2,'Disabled',session=78,id=13)==0xca and c.image()==GRAY
    assert c.send(1,1,session=79)==0xca
    assert c.send(4,2,'Nenhuma conquista concedida',session=79)==0xca
    assert c.send(5,3,session=79)==0xca and c.image()==GRAY
    print('PASSED ARM11: typed titles, FIFO, deduplication, CRC, UTF-8, expiry, policy, session reset, bounds, owned triple output, source immutability, cropped reads, cache coverage, ABI and blanking')

def owned_output(build):
    # Execute original caller, wrappers, pointer conversion ABI and LCD stores.
    c=Console(build);assert c.send(1,1)==0xca;assert c.send(2,2,'Kirby: Squeak Squad')==0xca
    original_stub=c.m.stubs.pop(0x1088c0)
    def translate(m):
        p=m.reg(0);assert 0x1f000000<=p<0x1f600000;m.ret(p-0x07000000)
    c.m.stubs[0x10f1b8]=translate
    c.surface(SOURCE,640);c.m.word(0x12cb80,320)
    for i in range(6):
        c.m.u.mem_write(SOURCE,GRAY*2)
        old=[c.m.word(0x1ef00568),c.m.word(0x1ef0056c)]
        c.m.word(0x12cb8c,i&1)
        c.m.run(0x105f78,0x401,count=4000000) # original routine has no result contract
        out=c.m.word(0x1ef00568+(i&1)*4)+0x07000000
        assert out not in (SOURCE,SOURCE+SIZE) and c.m.word(0x1ef00590)==720
        assert c.m.word(0x1ef00570)&0xffff==0x301 and c.m.word(0x12cb8c)==1-(i&1)
        assert all(not(out-0x07000000<=p<out-0x07000000+SIZE) for p in old)
        assert bytes(c.m.u.mem_read(SOURCE,SIZE*2))==GRAY*2
        published=bytes(c.m.u.mem_read(out,SIZE));assert published!=GRAY
        c.m.u.mem_write(SOURCE,bytes([13])*(SIZE*2))
        assert bytes(c.m.u.mem_read(out,SIZE))==published
    c.m.stubs[0x1088c0]=original_stub
    # Exhaustion cannot make us modify an LCD-referenced output.
    pool=c.stats()[12];before=bytes(c.m.u.mem_read(pool,SIZE*3))
    c.m.word(0x1ef00568,pool-0x07000000+8);c.m.word(0x1ef0056c,pool+SIZE-0x07000000+8)
    c.step();assert c.presented==SOURCE and bytes(c.m.u.mem_read(pool,SIZE*3))==before
    assert c.stats()[11]>0
    # Native heap reinitialization invalidates ownership even if the address
    # could be reused. Reacquire through the allocator and recheck both LCD slots.
    c.m.run(0x102970);assert c.stats()[12]==0
    c.step();assert c.presented!=SOURCE and c.stats()[12]!=0
    # No memory: one failed allocation, no popup pixels, no fake 'shown'.
    d=Console(build);attempts=[]
    d.m.stubs[0x11045c]=lambda m:(attempts.append(tuple(m.reg(i) for i in range(4))),m.ret(0))
    d.send(1,1);d.send(2,2,'No memory')
    for _ in range(3):d.step()
    s=d.stats();assert len(attempts)==1 and s[10]==1 and s[2]==0 and s[7]==0
    assert d.presented==SOURCE and d.image()==GRAY
    for svc in (0x52,0x53):
        d=Console(build);d.m.cache_results[svc]=0xffffffff
        d.send(1,1);d.send(2,2,'Cache failure')
        assert d.presented==SOURCE and d.image()==GRAY
        assert d.stats()[2]==0 and d.stats()[4]>0
        d.m.cache_results.clear();d.step();assert d.title()=='Cache failure' and d.presented!=SOURCE
    # Untagged storage must preserve an active Nintendo texture ID and table.
    d=Console(build);d.m.word(0x1279f8,2);d.m.word(0x12be70,0x12345678)
    d.send(1,1);d.send(2,2,'Texture ownership')
    assert d.presented!=SOURCE and d.m.word(0x1279f8)==2 and d.m.word(0x12be70)==0x12345678
    # An uninitialized heap or in-flight GPU yields without spending a queued
    # notification's display duration.
    for address,stat_index in ((0x12bdd0,20),(0x12ca51,19)):
        d=Console(build);d.m.word(address,1);d.send(1,1);d.send(2,2,'Deferred')
        assert d.presented==SOURCE and not d.title();assert d.stats()[stat_index]>0
        d.now=9*TICKS;d.m.word(address,0x45585048 if address==0x12bdd0 else 0);d.step();assert d.title()=='Deferred'
        d.now=10*TICKS;d.step();assert d.title()=='Deferred'
    # Unsupported descriptors and source/owned-pool overlap are never read/written.
    d=Console(build);d.send(1,1);d.send(2,2,'Bounds');pool=d.stats()[12]
    d.m.word(0x12cb68,0xfffffff0);d.step();assert d.presented==SOURCE and d.image()==GRAY
    d.m.word(0x12cb68,d.object);d.surface(pool,1024)
    before=bytes(d.m.u.mem_read(pool,SIZE*3));d.step(left=pool)
    assert d.presented==pool and bytes(d.m.u.mem_read(pool,SIZE*3))==before
    d=Console(build);d.send(1,1);d.send(2,2,'Timing');d.tick_step=200000
    for _ in range(10):d.step()
    s=d.stats();assert s[37]>=400000 and s[42]>=10 # composite max and 1..2 ms bucket
    assert sum(s[38:46])==s[7] and ((s[47]<<32)|s[46])>=4000000
    print('PASSED ownership: original allocator/LCD publication, immutable GPU and held LCD frames, exhaustion, allocation/cache failure, texture-ID preservation, heap rebuild/readiness, GPU deferral, timing bins and bounds')

def inplace_roi(build):
    c=Console(build)
    def forbidden(m):raise AssertionError('default compositor attempted a VRAM allocation')
    c.m.stubs[0x11045c]=forbidden
    c.m.word(0x12cb68,0xfffffff0) # no assumed descriptor pointer is needed to draw
    assert c.send(1,1)==0xca
    assert c.send(2,2,'Kirby: Squeak Squad')==0xca and c.title()=='Kirby: Squeak Squad'
    assert c.image()!=GRAY
    # Exact alternating addresses measured on the console: +16-byte second
    # origin, with an allocator header immediately before each pixel region.
    for i in range(12):
        pointer=(0x1f337940,0x1f36fd50)[i&1]
        frame=bytes([40+i])*SIZE;sentinel=b'\xa5'*16
        c.m.u.mem_write(pointer-16,sentinel);c.m.u.mem_write(pointer+SIZE,sentinel)
        c.step(left=pointer,frame_base=pointer,frame=frame,index=i&1,select=i&1)
        assert c.presented==pointer and c.present_args==(1,i&1,pointer,0,720,0x301,i&1)
        assert bytes(c.m.u.mem_read(pointer-16,16))==sentinel
        assert bytes(c.m.u.mem_read(pointer+SIZE,16))==sentinel
        changed=[n for n,(a,b) in enumerate(zip(frame,c.image())) if a!=b];assert changed
        caches=[e for e in c.m.events if e['event']=='cache'][-2:]
        assert [e['svc'] for e in caches]==['0x52','0x53']
        for e in caches:
            assert e['r1']%32==0 and e['r2']%32==0
            assert pointer<=e['r1']<=pointer+min(changed)
            assert pointer+max(changed)<e['r1']+e['r2']<=pointer+SIZE
    s=c.stats();assert s[17]==2 and s[7]>=13 and s[10:13]==(0,0,0)
    assert s[8:10]==(0,0) # neither physical alignment is rejected
    c.now=3*TICKS;assert c.send(3,3,'Spark',id=10)==0xca and c.title()=='Spark'
    assert c.send(3,4,'Fire',id=11)==0xca and c.title()=='Spark'
    c.now=7*TICKS;c.step();assert c.title()=='Fire'
    shown=c.diag()[4];assert c.send(3,4,'Fire',id=11)==0xca and c.diag()[4]==shown
    c.now=11*TICKS;c.step();assert not c.title() and c.image()==GRAY
    title='Ação: '+('Long achievement title / '*3)
    c.send(3,5,title,id=12);assert c.title()==title
    first=c.image();c.now+=2*TICKS;c.step();assert c.image()!=first
    for kwargs in ({'screen':0},{'format':0},{'stride':1536},{'left':0x1f5ffff0}):
        c.step(**kwargs)
        assert bytes(c.m.u.mem_read(SOURCE,SIZE))==GRAY if kwargs.get('screen',1)==1 else c.present_args[0]==0
    c.send(1,1,session=78,flags=0);assert c.image()==GRAY and not c.title()
    c.send(3,2,'Disabled',session=78,id=13);assert c.image()==GRAY
    c.send(1,1,session=79);c.send(4,2,'Nenhuma conquista concedida',session=79)
    assert c.title()=='Nenhuma conquista concedida'
    c.send(5,3,session=79);assert c.image()==GRAY
    c.send(1,1,session=80);c.send(2,2,'Native presentation',session=80)
    c.m.word(0x12cb68,c.object);c.surface(SOURCE,640);c.m.word(0x12cb80,320)
    del c.m.stubs[0x1088c0]
    def translate(m):
        p=m.reg(0);assert 0x1f000000<=p<0x1f600000;m.ret(p-0x07000000)
    c.m.stubs[0x10f1b8]=translate
    for index in (0,1):
        c.m.u.mem_write(SOURCE,GRAY*2);c.m.word(0x12cb8c,index)
        c.m.run(0x105f78,0x401,count=4000000)
        assert c.m.word(0x1ef00568+index*4)==SOURCE+SIZE-0x07000000
        assert c.m.word(0x1ef00590)==720 and c.m.word(0x12cb8c)==1-index
        assert bytes(c.m.u.mem_read(SOURCE+SIZE,SIZE))!=GRAY
    print('PASSED ROI: exact physical alternating addresses, +16 alignment, header preservation, complete modified-byte cache coverage, no allocation, titles/FIFO/UTF-8/marquee/expiry/policy and original presentation ABI')

def native_exhaustion(build):
    c=Console(build)
    assert c.m.run(0x11045c,0x12bdb8,0x2c0000,128,0,0,0)
    c.send(1,1);c.send(2,2,'Native heap exhausted')
    s=c.stats();assert s[10]==1 and not s[12] and not s[2] and c.presented==SOURCE
    assert c.image()==GRAY
    print('PASSED native allocator exhaustion: no panic, publication, retry loop or source writes')

def ocr(build):
    text=(HERE/'payload/font.h').read_text();text=text[text.index('ra_font['):]
    font=[int(x,16) for x in re.findall(r'0x[0-9a-fA-F]{2}',text)]
    def frame(header,title,scaled=True,row=0,white_prefix=False):
        f=bytearray(GRAY)
        for line,string in enumerate((header,title)):
            for i,ch in enumerate(string):
                for gy in range(8):
                    for gx in range(8):
                        if font[(ord(ch)-32)*8+gy]&(0x80>>gx):
                            x=(31-len(string)+i)*8+gx;y=(row+line)*8+gy
                            x=x*5//4 if scaled else x+32;y=y*5//4 if scaled else y+24
                            off=x*720+(239-y)*3;f[off:off+3]=b'\xff'*3
        if white_prefix:
            for x in (153,163):off=x*720+(239-2)*3;f[off:off+3]=b'\xff'*3
        return bytes(f)
    for scaled in (True,False):
        c=Console(build);image=frame('ACHIEVEMENT','Spark',scaled,white_prefix=scaled)
        c.step(frame=image);c.step(frame=image);assert c.title()=='Spark',(scaled,c.title())
        image=frame('ACHIEVEMENT','Fire',scaled);c.step(frame=image);c.step(frame=image)
        c.now=4*TICKS;c.step(frame=image);assert c.title()=='Fire'
        shown=c.diag()[4];c.now=8*TICKS;c.step(frame=image);assert c.diag()[4]==shown
        for _ in range(3):c.step()
        image=frame('RETROACHIEVEMENTS','Offline: KIRBY',scaled,row=1)
        c.step(frame=image);c.step(frame=image);assert c.title()=='KIRBY',(scaled,c.title(),c.diag())
    c=Console(build);white=bytes([255])*SIZE;c.step(frame=white);c.step(frame=white);assert c.image()==white
    print('PASSED OCR: full header, white-prefix regression, sequential titles, persistent-banner deduplication, startup name, rows 0/1 and scales 1.25/1.0')

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('build',type=Path,nargs='?',default=HERE/'build')
    args=parser.parse_args()
    if json.loads((args.build/'manifest.json').read_text()).get('compositor')=='in-place-hud-cache-span':
        inplace_roi(args.build);return
    typed(args.build);owned_output(args.build);native_exhaustion(args.build)
    if json.loads((args.build/'manifest.json').read_text())['renderer']=='ocr-compatibility':ocr(args.build)
if __name__=='__main__':main()
