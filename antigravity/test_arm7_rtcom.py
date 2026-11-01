#!/usr/bin/env python3
"""Run compiled ARM7 carrier instructions with a serial-RTC fixture. No timing claims."""
from pathlib import Path
import subprocess
import struct
from unicorn import Uc,UC_ARCH_ARM,UC_MODE_ARM,UC_HOOK_MEM_READ,UC_HOOK_MEM_WRITE,UC_HOOK_INTR
from unicorn.arm_const import UC_ARM_REG_R0,UC_ARM_REG_R4,UC_ARM_REG_R5,UC_ARM_REG_R6,UC_ARM_REG_R7,UC_ARM_REG_R8,UC_ARM_REG_R9,UC_ARM_REG_R10,UC_ARM_REG_R11,UC_ARM_REG_SP,UC_ARM_REG_LR,UC_ARM_REG_PC
ROOT=Path(__file__).resolve().parent.parent
PREFIX=Path('/opt/devkitpro/devkitARM/bin/arm-none-eabi-')
ELF=ROOT/'retail/cardenginei/arm7/build/cardenginei_arm7.elf'
BINARY=ROOT/'retail/nitrofiles_dec/cardenginei_arm7.bin'
GPIO=0x04000138
SHARED=0x027ffa0c
STOP=0x08000000
nm=subprocess.check_output([str(PREFIX)+'nm','-n',str(ELF)],text=True)
symbols={line.split()[2]:int(line.split()[0],16) for line in nm.splitlines() if len(line.split())==3}

class RTCFixture:
    def __init__(self):
        self.u=Uc(UC_ARCH_ARM,UC_MODE_ARM)
        base=symbols['__text_start']&~4095
        self.u.mem_map(base,0x20000);self.u.mem_write(symbols['__text_start'],BINARY.read_bytes())
        self.u.mem_map(0x027ff000,0x4000);self.u.mem_map(0x04000000,0x10000);self.u.mem_map(STOP,0x1000)
        self.u.mem_write(GPIO,b'\x72');self.u.mem_write(0x04000134,b'\xfe\xca')
        self.registers={0x6f:0,0x6d:0};self.transactions=[];self.active=False;self.previous=0x72
        self.bits=[];self.read_index=0;self.swi=0
        self.u.hook_add(UC_HOOK_MEM_WRITE,self.write_hook)
        self.u.hook_add(UC_HOOK_MEM_READ,self.read_hook)
        def interrupt(u,number,user):self.swi+=1
        self.u.hook_add(UC_HOOK_INTR,interrupt)
    def write_hook(self,u,access,address,size,value,user):
        if address!=GPIO:return
        selected=bool(value&4);clock=bool(value&2)
        if selected and not self.active:
            self.active=True;self.bits=[];self.read_index=0
        elif selected and not(self.previous&2) and clock:
            if len(self.bits)<8:self.bits.append(value&1)
            elif value&16:self.bits.append(value&1)
            else:self.read_index+=1
        elif not selected and self.active:
            command=sum(bit<<(7-i) for i,bit in enumerate(self.bits[:8]))
            if command&1:
                self.transactions.append(('read',command,self.registers.get(command,0)))
            else:
                # RTCom's 112/113 registers use MSB-first data, unlike the
                # ordinary libnds date/time transaction. Independent wire oracle.
                data=sum(bit<<(7-i) for i,bit in enumerate(self.bits[8:16]))
                self.registers[command|1]=data;self.transactions.append(('write',command,data))
            self.active=False
        self.previous=value
    def read_hook(self,u,access,address,size,value,user):
        if address!=GPIO or not self.active or len(self.bits)<8 or not self.read_index:return
        command=sum(bit<<(7-i) for i,bit in enumerate(self.bits[:8]))
        bit=(self.registers.get(command,0)>>(8-self.read_index))&1
        current=u.mem_read(GPIO,1)[0];u.mem_write(GPIO,bytes(((current&~1)|bit,)))
    def request(self,command,data=0):self.u.mem_write(SHARED+48,struct.pack('<I',0x52410000|(command<<8)|data))
    def word(self):return struct.unpack('<I',self.u.mem_read(SHARED+48,4))[0]
    def run(self):
        registers=[UC_ARM_REG_R4,UC_ARM_REG_R5,UC_ARM_REG_R6,UC_ARM_REG_R7,UC_ARM_REG_R8,UC_ARM_REG_R9,UC_ARM_REG_R10,UC_ARM_REG_R11]
        for i,r in enumerate(registers):self.u.reg_write(r,0xabc000+i)
        self.u.reg_write(UC_ARM_REG_R0,SHARED);self.u.reg_write(UC_ARM_REG_SP,0x02802000)
        self.u.reg_write(UC_ARM_REG_LR,STOP|1)
        self.u.emu_start(symbols['raBridgeArm7']|1,STOP,count=20000)
        assert self.u.reg_read(UC_ARM_REG_PC)==STOP
        assert self.u.reg_read(UC_ARM_REG_SP)==0x02802000
        assert all(self.u.reg_read(r)==0xabc000+i for i,r in enumerate(registers))
        assert bytes(self.u.mem_read(0x04000134,2))==b'\xfe\xca'
        assert self.swi<200,'unexpected/unbounded serial delay'

def main():
    f=RTCFixture();f.request(0x50,1);f.run()
    assert f.transactions==[('read',0x6f,0),('write',0x6c,1),('write',0x6e,0x50)],f.transactions
    assert f.u.mem_read(GPIO,1)[0]==0x72
    f.registers[0x6f]=0xc7;f.run();assert f.word()==0x5242c701
    f=RTCFixture();f.registers[0x6f]=0x41;f.request(0x50,1);f.run()
    assert f.word()==0x5242cb00 and len(f.transactions)==1
    f=RTCFixture();f.request(0x50,1);f.u.mem_write(GPIO,b'\x76');f.run();assert not f.transactions
    f=RTCFixture();f.request(0x50,1);f.u.mem_write(SHARED+12,struct.pack('<I',0x025ffb09));f.run();assert not f.transactions
    f=RTCFixture();f.request(0x56,0xa5);f.run();f.swi=0
    f.registers[0x6f]=0xcd;f.registers[0x6d]=0;f.run();assert f.word()==0x5242cd00
    f=RTCFixture();f.request(0x57,4);f.run();f.swi=0
    f.registers[0x6f]=0xce;f.registers[0x6d]=0xab;f.run();assert f.word()==0x5242ceab
    f=RTCFixture();f.request(0x57,197);f.run()
    assert f.transactions[-2:]==[('write',0x6c,197),('write',0x6e,0x57)]
    print('PASSED compiled ARM7: RTC command bit order, byte read/write, ACK/echo, bus/card-read deferral, foreign-peer refusal, bounded SWIs, preserved pins/RCNT and callee ABI')
if __name__=='__main__':main()
