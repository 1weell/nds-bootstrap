import json
import struct
from pathlib import Path
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM, UC_HOOK_CODE
from unicorn.arm_const import *

STUB=0x027FE000
CALLBACK=0x03741000
STACK=0x02308000
RETURN=0x02001000
code=Path('/tmp/ra-dma-epilogue-proof.bin').read_bytes()
results=[]
for dest,control,wanted in [(0x07000400,0x84000100,1),
                            (0x07000000,0x84000100,0),
                            (0x06600000,0x84000100,0),
                            (0x07000400,0x84000080,0),
                            (0x07000400,0x84400100,0)]:
 for thumb in (False,True):
  for channel in range(4):
   uc=Uc(UC_ARCH_ARM,UC_MODE_ARM)
   uc.ctl_set_cpu_model(UC_CPU_ARM_946)
   for base,size in [(STUB,0x1000),(CALLBACK,0x1000),(0x02300000,0x10000),(RETURN,0x1000)]:uc.mem_map(base,size)
   uc.mem_write(STUB,code)
   uc.mem_write(CALLBACK,b'\x1e\xff\x2f\xe1')
   uc.reg_write(UC_ARM_REG_CPSR,0x1F)
   expected={}
   for index in range(13):
    register=UC_ARM_REG_R0+index
    value=0x10000000+index*0x10101
    uc.reg_write(register,value);expected[index]=value
   # Live r4..r7 at the original DMA epilogue hold control/dest/source/channel;
   # caller values are restored from the function's own saved stack frame.
   uc.reg_write(UC_ARM_REG_R4,control)
   uc.reg_write(UC_ARM_REG_R5,dest)
   uc.reg_write(UC_ARM_REG_R6,0x02200000)
   uc.reg_write(UC_ARM_REG_R7,channel)
   old_lr=RETURN|int(thumb)
   saved=[0xAABBCCDD,*[expected[i] for i in range(4,8)],old_lr]
   uc.mem_write(STACK-24,struct.pack('<6I',*saved))
   uc.reg_write(UC_ARM_REG_SP,STACK-24)
   uc.reg_write(UC_ARM_REG_LR,0x01FF85A8)
   calls=[]
   def hook(emu,pc,size,data):
    if pc!=CALLBACK:return
    assert emu.reg_read(UC_ARM_REG_SP)%8==0
    calls.append((emu.reg_read(UC_ARM_REG_R0),emu.reg_read(UC_ARM_REG_R1)))
    lr=emu.reg_read(UC_ARM_REG_LR)
    # Simulate arbitrary ABI-permitted volatile clobbers by the renderer.
    for r in (UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3,UC_ARM_REG_R12):emu.reg_write(r,0xDEADBEEF)
    emu.reg_write(UC_ARM_REG_PC,lr)
   uc.hook_add(UC_HOOK_CODE,hook)
   uc.emu_start(STUB,RETURN,count=1000)
   assert len(calls)==wanted,(dest,control,thumb,channel,calls)
   if wanted:assert calls[0]==(dest,control)
   assert uc.reg_read(UC_ARM_REG_SP)==STACK
   assert uc.reg_read(UC_ARM_REG_PC)==RETURN
   assert bool(uc.reg_read(UC_ARM_REG_CPSR)&0x20)==thumb
   for i,v in expected.items():assert uc.reg_read(UC_ARM_REG_R0+i)==v,(i,hex(uc.reg_read(UC_ARM_REG_R0+i)),hex(v))
   results.append({'dest':hex(dest),'control':hex(control),'caller_thumb':thumb,'channel':channel,'calls':len(calls),'registers_and_stack_preserved':True})
Path('/tmp/ra-dma-epilogue-proof-results.json').write_text(json.dumps(results,indent=2)+'\n')
print(f'PASSED {len(results)} ARM946 epilogue cases: filter, ARM/Thumb return, stack alignment, register preservation')
