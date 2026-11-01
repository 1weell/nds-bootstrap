#!/bin/sh
#
# Build the ROM that gets handed to a person, and refuse to produce one that is not what it claims.
#
# This exists because of a specific failure, and the failure is worth writing down because nothing in
# the build would have caught it. The pre-delivery checklist in docs/retroachievements.md says a ROM
# must compile at RA_LAUNCHER_WIFI=0 and =2. Running both `make`s satisfies that -- and leaves
# retail/bin/nds-bootstrap.nds holding whichever one ran *last*. Copying it after a `=0` build hands
# over a launcher with no network: no RetroAchievements ladder, nothing staged for the cardengine, and
# cardenginei_arm9_ra falling back to its built-in self-test, which fires one unlock with the synthetic
# id 0xF0000000 seconds into the game.
#
# That was mistaken for an intermittent memory fault for several days. The arena, the pending block's
# address and the launcher's statics were all blamed in turn, on evidence that was really "did the =2
# build happen to run last this time". The logs agreed with each other and not with the console,
# because a boot with no network never rewrites ra_wifi_launcher.log -- so the log being read was the
# previous, working boot's.
#
# So: the order is fixed here rather than remembered, and the result is verified against the binary
# rather than against intent. `=0` is built first because it is only a compile check; `=2` is built
# last because it is the deliverable.
#
set -e

cd "$(dirname "$0")/.."

OUT=${1:-nds-bootstrap-release.nds}

# From scratch, always, and that is a finding rather than caution.
#
# The ROM handed over for a hardware test was for a long time whatever an *incremental* build left on
# disk, and this project's development involves running `make` inside individual cardengine
# directories all day to measure link margins. Building the same commit clean, at the same path,
# produced a **different binary** -- so at least one artifact in that tree was not being rebuilt when
# it should have been, and the ROM under test did not reproduce from its own source.
#
# That is the one thing this script exists to prevent: it already refuses to ship a build that is not
# what it claims. A binary nobody can reproduce is exactly that, and it is worse than a wrong flag
# because a hardware result gets attached to it. Every reading in docs/devlogs is a reading of some
# specific binary; if that binary cannot be rebuilt, the reading cannot be checked.
#
# The cost is a few minutes per release. The alternative is test results that mean nothing.
#
# **This does not make the build reproducible for anyone else**, and that is a separate, known
# limitation: dsiwifi's lwip compiles __FILE__ into 26 assertion strings, so the absolute source path
# is embedded in the ROM. Two clean builds of the same commit at different paths differ -- and because
# the payloads are LZ77-compressed, a handful of changed bytes cascades into most of the file. Same
# path, same result; different path, different bytes. Fixing that means -ffile-prefix-map through
# upstream's build, which is not this script's to change.
echo "cleaning, so the deliverable is built from source rather than from what is lying around"
build_log=$(mktemp)
trap 'rm -f "$build_log"' EXIT
checked_make() {
	if make -j1 "$@" >"$build_log" 2>&1; then return 0; fi
	tail -n 45 "$build_log" >&2
	return 1
}
checked_make clean

echo "checking RA_LAUNCHER_WIFI=0 still compiles"
checked_make RA_LAUNCHER_WIFI=0

echo "building the deliverable at RA_LAUNCHER_WIFI=2"
checked_make RA_LAUNCHER_WIFI=2

# The proof, taken from the ELF the ROM was built from. A =2 launcher links dsiwifi into its ARM7 and
# a =0 launcher does not, so this separates them without trusting which make ran last.
WIFI=$(arm-none-eabi-nm retail/arm7/nds-bootstrap.elf 2>/dev/null | grep -ci 'dsiwifi\|wifi_' || true)
if [ "$WIFI" -lt 20 ]; then
	echo "REFUSING: the ARM7 has $WIFI wifi symbols, so this is not a network build" >&2
	exit 1
fi

# The in-game menu's one unchecked mirror, taken from the link rather than from intent.
#
# struct IgmText's size is written by hand a second time as a `.space` in
# arm9_igm/source/card_engine_header.s, and nothing links the two files. When they disagreed --
# 0xF40 there against 0xF68 in the header -- every symbol after the text block landed short of where
# the C side computes it, and opening the menu jumped into the middle of the text. Contra 4 died on
# the frame the menu opened, and the cause took a session to find because the build was clean.
#
# sharedAddr sits immediately after the block, 16-byte aligned, so its offset from igmText *is*
# IGM_TEXT_SIZE_ALIGNED. If the two numbers disagree this is where it shows, before a card does.
echo "the in-game menu's text mirror"
IGM_ELF=retail/cardenginei/arm9_igm/build/cardenginei_arm9_igm.elf
if [ -f "$IGM_ELF" ]; then
	IGM_BASE=$(arm-none-eabi-nm "$IGM_ELF" | awk '$3 == "igmText" { print $1 }')
	IGM_SHARED=$(arm-none-eabi-nm "$IGM_ELF" | awk '$3 == "sharedAddr" { print $1 }')
	IGM_SIZE=$(printf '%d' $((0x$IGM_SHARED - 0x$IGM_BASE)))
	IGM_WANT=$(grep -o 'sizeof(IgmText) == 0x[0-9A-Fa-f]*' retail/common/include/igm_text.h \
	           | grep -o '0x[0-9A-Fa-f]*')
	IGM_WANT=$(printf '%d' $(( ( $IGM_WANT + 0xF ) & ~0xF )))
	if [ "$IGM_SIZE" -ne "$IGM_WANT" ]; then
		echo "REFUSING: igmText occupies $IGM_SIZE bytes, the header says $IGM_WANT" >&2
		echo "  the .space in arm9_igm/source/card_engine_header.s does not match struct IgmText" >&2
		exit 1
	fi
	echo "  igmText $IGM_SIZE bytes, header and .space agree"
else
	echo "REFUSING: $IGM_ELF is missing, so the mirror cannot be checked" >&2
	exit 1
fi

echo "versioned RA graphics entry ABI"
python3 - <<'PY_GFX_ABI'
import pathlib, struct, subprocess
base = 0x03740000
binary = pathlib.Path('retail/nitrofiles/cardenginei_arm9_ra.bin').read_bytes()
elf = 'retail/cardenginei/arm9_ra/build/cardenginei_arm9_ra.elf'
symbols = {line.split()[-1]:int(line.split()[0],16)
           for line in subprocess.check_output(['arm-none-eabi-nm',elf],text=True).splitlines()
           if len(line.split())==3}
assert struct.unpack_from('<I',binary,16)[0] == 0x31475052
for offset,name in ((8,'raGfxDmaEpilogue'),(12,'raGfxBankEpilogue')):
    word = struct.unpack_from('<I',binary,offset)[0]
    assert word >> 24 == 0xEA
    displacement = word & 0xFFFFFF
    if displacement & 0x800000: displacement -= 0x1000000
    assert base+offset+8+displacement*4 == symbols[name], name
ready = symbols['raGfxReady']-base
assert 0 <= ready <= len(binary)-4
assert struct.unpack_from('<I',binary,ready)[0] == 0, 'readiness must be in copied image'
assert symbols['raGfxHookStatus'] == base+20
print('  graphics entries and fresh image readiness verified')
PY_GFX_ABI

echo "host suite"
# The exit status, not a grep for a word.
#
# This used to be `| grep -q "PASSED"`, and that is not a check: the suite runs several binaries and
# prints a verdict for each, so one FAILED among three PASSED still matched. It let a build ship with
# a stale `sizeof(raSnapshot)` pin -- a field had been appended and the assertion still named the old
# size -- and said nothing, which is the one thing this script exists not to do.
#
# ra_reader_test.sh already exits with the right status. Output is held back so a passing run stays
# quiet, and printed when it matters.
if ! SUITE=$(bash tools/ra_reader_test.sh 2>&1); then
	printf '%s\n' "$SUITE" | grep -E '^FAILED|^[[:space:]]*FAIL[[:space:]]|error:' >&2
	echo "REFUSING: the host suite did not pass" >&2
	exit 1
fi
# Anchor the verdict: successful CHECK output can contain MAP_FAILED.
# ...and a belt for the braces: a binary that reports FAILED without a non-zero exit is still a fail.
if printf '%s\n' "$SUITE" | grep -E '^FAILED([[:space:]]|$)' >/dev/null; then
	printf '%s\n' "$SUITE" | grep -E '^FAILED|^[[:space:]]*FAIL[[:space:]]' >&2
	echo "REFUSING: the host suite reported a failure" >&2
	exit 1
fi

echo "snapshot address and free bytes"
bash tools/ra_snapshot_addr.sh

cp retail/bin/nds-bootstrap.nds "$OUT"
# Bind saved diagnostic offsets to this exact artifact and menu ELF.
python3 - "$OUT" "$IGM_ELF" <<'PY_MANIFEST'
import hashlib, json, pathlib, re, subprocess, sys
artifact, elf = map(pathlib.Path, sys.argv[1:])
symbols = subprocess.check_output(['arm-none-eabi-nm', str(elf)], text=True)
match = re.search(r'^([0-9a-fA-F]+) [bBdD] raPopupLast$', symbols, re.M)
manifest = {'artifact_sha256': hashlib.sha256(artifact.read_bytes()).hexdigest(),
            'igm_elf_sha256': hashlib.sha256(elf.read_bytes()).hexdigest()}
if match:
    offset = int(match[1], 16) - 0x02F88000
    if not 0 <= offset < 0xA000:
        raise SystemExit('REFUSING: popup diagnostic is outside saved menu image')
    # The size is deliberately not recorded. It was a literal here and in the reader, they
    # drifted when the struct gained trailing fields, and the console reading was refused for
    # a mismatch that mattered to nothing: the reader decodes with its own struct definition.
    # The sha256 below is what proves the artifact is the one built from this ELF.
    manifest['popup_pagefile_offset'] = offset
pathlib.Path(str(artifact) + '.manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
PY_MANIFEST
echo
echo "$OUT"
if git rev-parse --git-dir >/dev/null 2>&1; then
    echo "  commit  $(git rev-parse --short HEAD)$(git diff --quiet || echo ' (WORKING TREE DIRTY)')"
else
    echo "  source  exported snapshot (no Git history)"
fi
echo "  wifi    $WIFI symbols -- RA_LAUNCHER_WIFI=2"
echo "  md5     $(md5sum "$OUT" | cut -d' ' -f1)"
