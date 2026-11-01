#!/usr/bin/env python3
"""Exercise the actual bootloader patcher, including all-or-nothing matching."""
import ctypes
import pathlib
import struct
import subprocess
import sys
import tempfile
ROOT = pathlib.Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix="ra-gfx-patch-") as directory:
    directory = pathlib.Path(directory)
    source = directory / "probe.c"
    source.write_text(r'''#include <stdint.h>
typedef uint32_t u32;
#include "ra_gfx_patch.h"
int apply(u32* image,u32 bytes) {return raGfxPatchImage(image,bytes,0x03740008,0x0374000C);}
const u32* signature(int bank) {return bank?raGfxBankSignature:raGfxDmaSignature;}
u32 length(int bank) {return bank?sizeof(raGfxBankSignature):sizeof(raGfxDmaSignature);}
''')
    library = directory / "probe.so"
    subprocess.run(["cc", "-std=c99", "-Wall", "-Wextra", "-Werror", "-shared", "-fPIC",
                    "-I" + str(ROOT / "retail/common/include"), str(source), "-o", str(library)], check=True)
    lib = ctypes.CDLL(str(library))
    lib.signature.restype = ctypes.c_void_p
    lib.length.restype = ctypes.c_uint32
    lib.apply.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
    dma, bank = [ctypes.string_at(lib.signature(i), lib.length(i)) for i in (0, 1)]
    def apply(data):
        buf = ctypes.create_string_buffer(bytes(data))
        result = lib.apply(buf, len(data))
        return result, bytes(buf.raw[:len(data)])
    image = bytearray(1024)
    image[64:64+len(dma)] = dma
    image[320:320+len(bank)] = bank
    result, patched = apply(image)
    assert result == 1
    expected = image.copy()
    struct.pack_into("<2I", expected, 64+0x60, 0xE51FF004, 0x03740008)
    struct.pack_into("<2I", expected, 320+0x64, 0xE51FF004, 0x0374000C)
    assert patched == expected
    cases = [bytearray(), image[:319], image[:320+len(bank)-1]]
    changed = image.copy(); changed[320+32] ^= 1; cases.append(changed)
    duplicate = image.copy(); duplicate[600:600+len(dma)] = dma; cases.append(duplicate)
    duplicate = image.copy(); duplicate[600:600+len(bank)] = bank; cases.append(duplicate)
    for data in cases:
        result, after = apply(data)
        assert result == 0 and after == data, "Partial or ambiguous patch mutated image"
    if len(sys.argv) > 1:
        rom = pathlib.Path(sys.argv[1]).read_bytes()
        assert rom[12:16] == b"ATRE"
        offset, entry, address, size = struct.unpack_from("<4I", rom, 0x20)
        original = rom[offset:offset+size]
        result, patched = apply(original)
        assert result == 1
        differences = [i for i,(x,y) in enumerate(zip(original,patched)) if x != y]
        assert all(0x76FC8 <= i < 0x76FD0 or 0x1BBC <= i < 0x1BC4 for i in differences)
        print("PASSED exact ATRE ARM9/autoload patch: only two epilogues changed")
    print("PASSED production graphics patch: complete unique signatures, truncated/corrupt/duplicate rejection, atomic refusal")
