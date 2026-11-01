/* Exact ATRE SDK signatures: patch autoload source before ARM9 boot.
 * Both matches must be unique and complete before either epilogue is changed. */
#ifndef RA_GFX_PATCH_H
#define RA_GFX_PATCH_H
#include <string.h>
#define RA_GFX_ABI_MAGIC 0x31475052u
#define RA_GFX_DMA_ENTRY 8
#define RA_GFX_BANK_ENTRY 12
#define RA_GFX_MAGIC_OFFSET 16
#define RA_GFX_STATUS_OFFSET 20
static const u32 raGfxDmaSignature[] = {
    0xE92D40F0u, 0xE24DD004u, 0xE1A07000u, 0xE1A06001u,
    0xE1A05002u, 0xE1A04003u, 0xEB003EA3u, 0xE3A0100Cu,
    0xE0030197u, 0xE2831301u, 0xE59F2038u, 0xE58160B0u,
    0xE0833002u, 0xE5835004u, 0xE5834008u, 0xE5921000u,
    0xE3570000u, 0xE5921000u, 0x03A02000u, 0x05832000u,
    0x059F1014u, 0x05832004u, 0x05831008u, 0xEB003E97u,
    0xE28DD004u, 0xE8BD80F0u,
};
static const u32 raGfxBankSignature[] = {
    0xE92D4000u, 0xE24DD004u, 0xE59F105Cu, 0xE1E0C000u,
    0xE1D121B4u, 0xE1D130B0u, 0xE3500000u, 0xE1C101B4u,
    0xE1832002u, 0xE00C2002u, 0xE1C120B0u, 0x0A000009u,
    0xE3500008u, 0x0A000004u, 0xE3500C01u, 0x059F002Cu,
    0x03A01082u, 0x05C01000u, 0xEA000002u, 0xE59F0020u,
    0xE3A01084u, 0xE5C01000u, 0xE59F000Cu, 0xE1D000B0u,
    0xEB0002E6u, 0xE28DD004u, 0xE8BD8000u,
};
static u32* raGfxFindUnique(u32* image, u32 bytes, const u32* pattern, u32 length) {
    u32* found = 0;
    u32 offset;
    if (bytes < length) return 0;
    for (offset = 0; offset <= bytes-length; offset += 4) {
        u32* at = (u32*)((unsigned char*)image+offset);
        if (at[0] == pattern[0] && memcmp(at, pattern, length) == 0) {
            if (found) return 0;
            found = at;
        }
    }
    return found;
}
static int raGfxPatchImage(u32* image, u32 bytes, u32 dmaTarget, u32 bankTarget) {
    u32* dma = raGfxFindUnique(image, bytes, raGfxDmaSignature, sizeof(raGfxDmaSignature));
    u32* bank = raGfxFindUnique(image, bytes, raGfxBankSignature, sizeof(raGfxBankSignature));
    if (!dma || !bank || dma == bank) return 0;
    dma[0x60/4] = 0xE51FF004u; /* ldr pc,[pc,#-4], literal absolute target */
    dma[0x64/4] = dmaTarget;
    bank[0x64/4] = 0xE51FF004u;
    bank[0x68/4] = bankTarget;
    return 1;
}
#endif
