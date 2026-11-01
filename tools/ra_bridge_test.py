#!/usr/bin/env python3
"""Compile production notification components, without hardware/network dependencies."""
from pathlib import Path
import os
import subprocess
import tempfile
root=Path(__file__).resolve().parent.parent
with tempfile.TemporaryDirectory(prefix="ra-bridge-test-") as directory:
    out=Path(directory)
    (out/"nds").mkdir()
    (out/"nds/ndstypes.h").write_text("#include <stdint.h>\n#include <stdbool.h>\ntypedef uint8_t u8;typedef uint16_t u16;typedef uint32_t u32;typedef int8_t s8;typedef int16_t s16;typedef int32_t s32;typedef volatile uint8_t vu8;typedef volatile uint16_t vu16;typedef volatile uint32_t vu32;\n")
    subprocess.run([os.environ.get("CC","cc"),"-std=gnu11","-Wall","-Wextra","-Werror",
        "-Wno-int-to-pointer-cast","-O1","-DRA_LAUNCHER_WIFI=2","-I"+str(out),
        "-I"+str(root/"retail/common/include"),"-I"+str(root/"retail/cardenginei/arm9_ra/include"),
        "-I"+str(root/"antigravity/payload"),str(root/"tools/ra_bridge_test.c"),
        str(root/"retail/cardenginei/arm9_ra/source/ra_bridge9.c"),
        str(root/"retail/arm9/source/ra_patch.c"),str(root/"retail/arm9/source/ra_metadata.c"),
        "-o",str(out/"test")],check=True)
    subprocess.run([str(out/"test")],check=True)
from ra_popup_report import Popup,decode
import ctypes
assert ctypes.sizeof(Popup)==304
record=Popup();record.magic=0x35445052;record.allowed=1;record.bridgeStatus=1;record.bridgeSent=2
assert decode(bytes(record))['bridge']['delivered']==2
record.arm11Magic=0x32545341;record.arm11Mode=1;record.arm11Composited=180
record.arm11Surfaces[0]=0x1f300003;record.arm11Surfaces[1]=720
record.arm11Surfaces[2]=0x301;record.arm11Surfaces[3]=3|(4<<24)
decoded=decode(bytes(record))['bridge']['arm11']
assert decoded['private_output'] and decoded['composited_frames']==180
assert decoded['recent_surfaces'][0]['reason_bits']=='0x4'
record.arm11CompositeBins[0]=1;record.arm11CompositeBins[4]=19
record.arm11CompositeMaxTicks=400000;record.arm11CompositeTotalLow=19*400000
timing=decode(bytes(record))['bridge']['arm11']['composition_timing']
assert timing['samples']==20 and timing['p50_us_bounds']==[1000,2000] and timing['p95_us_bounds']==[1000,2000]
# Saved older generations remain readable even after the structure grows.
old=bytearray(bytes(record)[:136]);old[:4]=(0x34445052).to_bytes(4,'little')
old[108:112]=(0x31545341).to_bytes(4,'little')
assert decode(old)['bridge']['delivered']==2
assert 'private_output' not in decode(old)['bridge']['arm11']
try:
    decode(bytes(record)[:92])
    raise AssertionError('Truncated diagnostics accepted')
except ValueError:
    pass
