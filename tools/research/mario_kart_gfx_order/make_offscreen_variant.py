#!/usr/bin/env python3
"""Create an AMCE-only host experiment; never edit production or build a release."""
import argparse
import hashlib
import re
from pathlib import Path

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('output', type=Path)
p.add_argument('--source', type=Path, help='Archived compositor; defaults to current production C')
p.add_argument('--no-palette', action='store_true', help='Omit the four OBJ palette writes for causal isolation')
args = p.parse_args()
root = Path(__file__).resolve().parents[3]
assert not args.output.resolve().is_relative_to(root), 'Keep experimental C outside the repository'
s = (args.source or root / 'retail/cardenginei/arm9_ra/source/ra_overlay.c').read_text()
before = hashlib.sha256(s.encode()).hexdigest()

def replace(a, b):
    global s
    assert s.count(a) == 1, f'Source changed; inspect experiment anchor: {a[:60]}'
    s = s.replace(a, b)

replace('static int chooseSprites(u8* out) {', '''/* AMCE's observed parked sentinel only. This is not a general visibility test. */
static u16 experimentSavedSpriteAttrs[RA_SPRITES][3];
static bool experimentReusableSprite(int i) {
    return (SUB_OAM[i*4]&0x300)==0x200 ||
        (SUB_OAM[i*4]==0xe0 && SUB_OAM[i*4+1]==0x180 && SUB_OAM[i*4+2]==0xc0);
}
static void experimentSaveSprite(int k) {
    for(int a=0;a<3;++a)experimentSavedSpriteAttrs[k][a]=SUB_OAM[spriteOam[k]*4+a];
}
static int chooseSprites(u8* out) {''')
replace('if ((SUB_OAM[i * 4] & 0x0300) == 0x0200) {', 'if (experimentReusableSprite(i)) {')
replace('\tsavedObjPaletteEntry  = SUB_OBJ_PALETTE[OBJ_PAL_ENTRY];',
        '\tfor (k=0;k<RA_SPRITES;++k)experimentSaveSprite(k);\n\tsavedObjPaletteEntry  = SUB_OBJ_PALETTE[OBJ_PAL_ENTRY];')
replace('''        SUB_OAM[i*4] = 0x0200;
        SUB_OAM[i*4+1] = 0;
        SUB_OAM[i*4+2] = 0;''', '''        for(int a=0;a<3;++a)SUB_OAM[i*4+a]=experimentSavedSpriteAttrs[k][a];''')
replace('''        if ((a & 0x0300) != 0x0200) {''', '''        if (!experimentReusableSprite(spriteOam[k])) {''')
replace('''    surveyObjVram(used, boundary);
    if (used[spriteSlot]) {''', '''    for(k=0;k<RA_SPRITES;++k)if(!spriteOwn(k))experimentSaveSprite(k);
    surveyObjVram(used, boundary);
    if (used[spriteSlot]) {''')
if args.no_palette:
    s, count = re.subn(r'SUB_OBJ_PALETTE\[OBJ_PAL_(?:ENTRY|SHADOW)\]\s*=\s*OVERLAY_(?:INK|SHADOW)_COLOUR;',
                       '/* research: palette writes omitted */', s)
    assert count == 4, 'Inspect palette write sites before updating this experiment'
args.output.write_text(s)
print(f'AMCE research variant from {before}; output SHA256 {hashlib.sha256(s.encode()).hexdigest()}')
