# Antigravity v7.3 — notification bridge

GPL-3.0. ARM9 produces typed notifications, ARM7 transports them through unused
legacy RTC registers, and the TwlBg ARM11 presentation hook draws them. This
directory also contains an explicitly selected OCR compatibility build.

## Configuration

```ini
renderer=arm11
overlay=1
overlay_games=42,123
```

`overlay=0` disables notifications; `1` uses the existing GameID allowlist; `2`
allows all identified/configured sessions. These meanings are unchanged.
`renderer=arm11` is the new default. `renderer=legacy` explicitly selects the old
DS graphics path. A missing ARM11 peer does **not** enable the legacy renderer.
Detection, SD persistence and deferred submission remain independent of renderer.

## Data and display

- `PatchData.Title` is captured separately from achievement titles. A versioned
  `.meta` cache binds the canonical game name to ROM hash and GameID. It uses CRC,
  verified temporary writes and a previous generation; old definition/identity
  cache files remain readable.
- The existing 256-byte session reservation carries a versioned extension. Old
  hardcore/refusal/overlay/queue offsets are unchanged. Legacy queue names remain
  the original 12-byte ROM names; display names have a separate field.
- Events copy title/ID at trigger time. Multiple triggers cannot overwrite the
  last text strip or beacon. Both producer and presentation queues are bounded;
  overflow is reported and cannot acknowledge or discard an SD award record.
- Titles support 95 UTF-8 bytes plus NUL. JSON Unicode escapes and surrogate pairs
  are decoded; record delimiters become spaces. The renderer scrolls 24 visible
  cells after a one-second hold. Original UTF-8 stays in the event. Duration
  grows for long names so the final window can be read, with eight characters
  per second and a hold at each end. The bitmap font transliterates supported accented Latin characters and shows `?`
  for other unsupported codepoints. Existing caches containing clipped/escaped
  titles need a successful online refresh to obtain the improved labels.
- Earlier cosmetic fields are reclaimed before rejecting executable definitions
  for lack of staging space. Oversized definitions, capacity limits, parse errors
  and skipped evaluation remain visible as partial coverage.

## Transport contract

`retail/common/include/ra_bridge.h` defines `BEGIN`, `READY`, `UNLOCK`, `PREVIEW`
and `END`. Wire records include version, type, flags, length, session, sequence,
GameID, achievement ID, UTF-8 text and CRC16-CCITT. No raw pointer crosses CPUs.

ARM9/ARM7 use only shared slot 12, the last existing slot. Requests have prefix
`0x5241`, responses `0x5242`. Award slots 9/10/11 are untouched. The producer owns
its immutable queued event until COMMIT ACK. RTC commands use register 112 for
data and 113 for control. START resets packet assembly; alternating byte commands
make duplicate writes harmless; COMMIT publishes only a complete valid packet.
Commands **and data** for these two RTCom registers shift MSB first, as in the
reviewed RTCom carrier. The ordinary libnds date/time parameter order is not
valid for this extension. The compiled ARM7 test uses an MSB-first peripheral
oracle and rejects the earlier LSB-first implementation (`01` became `80` and
HELLO `50` became `0a` on the wire).
BUSY applies bounded per-tick backoff without dropping the head event. Missing
ACKs time out and stop after three attempts; no infinite game-IRQ handshake.

ARM7 defers if the RTC chip select is already asserted or a card read is pending.
It preserves RTC pin configuration and does not claim `IRQ_NETWORK` or RCNT.
HELLO refuses another active RTCom control sequence. Circle Pad/other RTCom
patches have **no negotiated coexistence** in this version; use the unmodified,
exact-image baseline accepted by the builder. Do not combine unrelated patches.

Only a new session resets display state. Retransmissions are deduplicated by
session/sequence; recent retired sessions cannot be resurrected by a late BEGIN.
END is best effort when reset/exit is observed. Next BEGIN also clears old state
if shutdown stops interrupts before END can be delivered. PREVIEW follows the
same transport/render path and never awards an achievement.

Transport remains byte paced. Latency depends on actual presentation/VBlank
cadence and title length. The proposed 500 ms target is **not certified**; no
throughput claim is inferred from a simulated endpoint.

## Presentation contract

The builder accepts only the reviewed original TWL_FIRM SHA256. It reserves AXI
memory explicitly, keeps the original cache initialization and verifies the
presentation call bytes. GetSystemTick is checked against the kernel service
table and TwlBg permission mask.

v7.3 uses the in-place presentation path, with cache maintenance restricted to
an interior bounding interval containing every HUD write. Real-console traces
showed alternating source addresses `0x1f337940` and `0x1f36fd50`: the latter is
16-byte aligned and was rejected by v7.1's 32-byte pixel-origin guard. That
rejected every second presentation. Cache alignment belongs to the cache
interval, not to the pixel origin.

The hook accepts bottom-screen RGB8 (`format & 7 == 1`), stride 720 and a complete
230400-byte VRAM viewport. It rounds the HUD interval to cache lines, invalidates
before drawing and cleans/DSBs after. This interval stays strictly inside either
viewport, so it never invalidates an adjacent allocation header. Original
presentation pointers, index, stride, format and selection remain unchanged.
Top-screen pixels and LCD blanking are untouched. No VRAM pool is allocated.

v7.2's private-output candidate failed on the console: pool allocation/validation
failed, and the descriptor/cache guard rejected the second surface. Its code is
retained only behind `--private-output` for research; OCR compatibility also uses
that experimental profile. The package builder refuses that compositor for the
current release. Do not redeploy v7.2 as a supported stable candidate.

The revised guard/cache interval is tested with the exact physical addresses,
including coverage of every changed byte and preservation of adjacent headers.
These are CPU tests with modeled cache/GPU effects. On 2026-11-01 the user confirmed stable Kirby startup and three real unlock
popups with correct full names/scrolling, plus correct Advance Wars identification.
Validation covers that reported scope; see `FLICKER_20261101.md`.

Duration uses ARM11 ticks, not the number of hook calls. Diagnostics include
format/address/cache rejects, received/shown/duplicate/overflow counts and hook
timing: total/max ticks and bins at 100/250/500 us, 1/2/4/8 ms. Timing bins support
bounded percentile estimates; they are measurements only after a console run.
In-game Popup Diagnostics reports producer queue/delivery/loss/timeouts, title
source and partial coverage. Delivery ACK is distinct from server confirmation.
The RPD5 diagnostic receives an immutable 198-byte `AST2` snapshot over RTC,
validated with CRC16: format/stride, published notifications, composited frames,
total and active rejects, cache/allocation errors, output/GPU busy counts,
pool/source/output addresses, index/select and four recent surface tuples.
Composition-only timing includes maximum, total ticks and eight bins; the report
derives mean and bounded p50/p95 values without mixing idle frames into samples.
Diagnostic requests yield to events and time out. Refresh waits 300 runtime ticks
after the last complete transfer while the event queue is idle; byte pacing means
the sample can lag by several seconds. Opening the menu saves the latest sample,
not frames measured while gameplay is paused. The offline report reader retains
support for RPD2/3/4 records. See `FLICKER_20261101.md` for reason bits and evidence.

## Build and tests

Use a private output directory: the build contains extracted Nintendo firmware.

```sh
rtk proxy python3 -B antigravity/build_antigravity.py /private/twl.firm /private/v7
rtk proxy /path/to/python-with-unicorn -B antigravity/test_antigravity.py /private/v7
rtk proxy /path/to/python-with-unicorn -B antigravity/test_arm7_rtcom.py
rtk proxy python3 -B tools/ra_bridge_test.py
rtk proxy python3 -B antigravity/test_deploy_package.py
rtk proxy bash tools/ra_reader_test.sh
```

`--ocr` builds compatibility mode. Its full-header checks support the modeled
1.25x scale and centered 1:1 layout, rows 0/1, confidence checks, two observations
and a distinct presence latch. It can extract the startup name available in the
legacy banner and queue changed unlock text. It cannot distinguish identical
titles with different IDs or recover text already clipped by an old bootstrap.
Use typed events for the paired v7 installation. OCR is never an automatic fallback.

The cross-build release check is `tools/ra_release.sh`, using the configured
devkitARM environment. It checks WiFi 0/2 builds, image limits, IGM layout,
graphics ABI and the host suite. Tests execute production components and compiled
ARM11 instructions. GPU/cache/MMIO timing are explicitly synthetic fixtures.
The two tight TWLSDK ARM7 variants use `-Os` for service/clock/menu modules, retain
the SD driver's original flags and assert separation between BSS and user stack.
The RA ARM9 build disables debug assertions only in the two rcheevos modules
that referenced `__assert_func`, avoiding the large stderr formatting/heap
dependency. Explicit input validation remains enabled; the release still
requires at least 8192 bytes of real-set arena margin.

## Package, installation and recovery

The private package contains `TwlBg.cxi`, `nds-bootstrap.nds` and `package.json`
with SHA256 values and `renderer: typed-events`. Install both components together:

```sh
rtk proxy python3 -B antigravity/deploy_package.py IP /private/package \
  --port 5000 --backup-dir /private/new-backup-directory
```

Installation verifies the reviewed remote baseline, backs up each original locally
and remotely, reads back backups and staged candidates, promotes the pair and
configuration, and verifies final bytes. Failure restores promoted originals.
Only `renderer` changes in `ra.cfg`; other settings and credentials remain private.
The backup directory is mode 0700 and files containing configuration are mode 0600.
`deploy_ftp.py` forwards to this package-based command to avoid deploying a stale
single CXI accidentally. No NAND writes occur.

For recovery, power off, restore the paths recorded in private `installation.json`,
or rename `/luma/sysmodules/TwlBg.cxi` to `TwlBg.cxi.disabled` to use original TwlBg.
Do not restore unrelated configuration blindly. Restart the TWL session after a
module change; existing TwlBg remains loaded until then.

Hardware acceptance: explicit preview first; canonical startup name; two named
Kirby unlocks; Mario Kart race without graphics/audio regression; 1:1 display;
offline cached name; menu/sleep/second launch; and deferred server confirmation.
The accepted v7.3 package records the reported hardware scope in
`hardware-validation.json`; its original build manifest remains archived separately.
In-game network sync, badges, animated transitions and a full Unicode font are
outside this notification implementation.
