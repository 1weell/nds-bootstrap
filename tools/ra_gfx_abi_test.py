#!/usr/bin/env python3
"""Execute production header stubs with Unicorn ARM946 (analysis dependency)."""
import json
import pathlib
import struct
import sys
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM, UC_HOOK_CODE
from unicorn.arm_const import *
BASE=0x03740000
CALLBACK=int(sys.argv[2],0) if len(sys.argv)>2 else 0x03742000
RETURN=0x02001000
STACK=0x02308000
code=pathlib.Path(sys.argv[1]).read_bytes()
results=[]
cases=[(8,0x07000400,0x84000100,1),(8,0x07000000,0x84000100,0),
       (8,0x06600000,0x84000100,0),(8,0x07000400,0x84000080,0),
       (8,0x07000400,0x84400100,0),(12,0,0,1)]
for offset,dest,control,wanted in cases:
 for thumb in (False,True):
  for masked in (False,True):
   for channel in range(4):
    uc=Uc(UC_ARCH_ARM,UC_MODE_ARM);uc.ctl_set_cpu_model(UC_CPU_ARM_946)
    for addr,size in [(BASE,0x20000),(RETURN,0x1000),(0x02300000,0x10000)]:uc.mem_map(addr,size)
    uc.mem_write(BASE,code);uc.reg_write(UC_ARM_REG_CPSR,0x1F|(0x80 if masked else 0))
    expected={i:0x10000000+i*0x10101 for i in range(13)}
    for i,value in expected.items():uc.reg_write(UC_ARM_REG_R0+i,value)
    if offset==8:
     for register,value in [(UC_ARM_REG_R4,control),(UC_ARM_REG_R5,dest),(UC_ARM_REG_R6,0x02200000),(UC_ARM_REG_R7,channel)]:uc.reg_write(register,value)
     saved=[0xAABBCCDD,*[expected[i] for i in range(4,8)],RETURN|int(thumb)]
    else:saved=[0xAABBCCDD,RETURN|int(thumb)]
    uc.mem_write(STACK-4*len(saved),struct.pack('<%dI'%len(saved),*saved))
    uc.reg_write(UC_ARM_REG_SP,STACK-4*len(saved));uc.reg_write(UC_ARM_REG_LR,0x01FF85A8)
    calls=[]
    def hook(emu,pc,size,data):
     if pc!=CALLBACK:return
     assert emu.reg_read(UC_ARM_REG_SP)%8==0
     assert emu.reg_read(UC_ARM_REG_CPSR)&0x80, "C refresh is interruptible"
     calls.append(pc);lr=emu.reg_read(UC_ARM_REG_LR)
     for r in (0,1,2,3,12):emu.reg_write(UC_ARM_REG_R0+r,0xDEADBEEF)
     emu.reg_write(UC_ARM_REG_LR,0xDEADBEEF)
     emu.reg_write(UC_ARM_REG_CPSR,(emu.reg_read(UC_ARM_REG_CPSR)&~0x20)|((lr&1)<<5))
     emu.reg_write(UC_ARM_REG_PC,lr&~1)
    uc.hook_add(UC_HOOK_CODE,hook);uc.emu_start(BASE+offset,RETURN,count=1000)
    assert len(calls)==wanted
    assert uc.reg_read(UC_ARM_REG_SP)==STACK and uc.reg_read(UC_ARM_REG_PC)==RETURN
    assert bool(uc.reg_read(UC_ARM_REG_CPSR)&0x20)==thumb
    assert bool(uc.reg_read(UC_ARM_REG_CPSR)&0x80)==masked
    for i,value in expected.items():assert uc.reg_read(UC_ARM_REG_R0+i)==value
    results.append({'entry':offset,'dest':hex(dest),'control':hex(control),'thumb':thumb,'irq_masked':masked,'channel':channel,'calls':len(calls)})
print(json.dumps({'passed':len(results),'cases':results},indent=2))
