# nds-bootstrap RetroAchievements — v7.3

Experimental 3DS-family fork of nds-bootstrap with typed RetroAchievements
notifications through ARM9/ARM7 RTC and an ARM11 TwlBg hook.

Hardware report: Kirby startup correctly identified, three real achievements
with full titles and horizontal scrolling, stable popups; Advance Wars correctly
identified. This is not universal compatibility or server confirmation evidence.
Awards are persisted locally and submitted later through the launcher; do not
claim live in-game server synchronization or officially accepted hardcore.

## Build and validate

Use devkitPro/devkitARM and the upstream nds-bootstrap prerequisites. Run from
this directory. Dependencies are vendored; see DEPENDENCIES.md and LICENSE.

```sh
bash tools/ra_reader_test.sh
bash tools/ra_release.sh /absolute/private/path/nds-bootstrap-release.nds
```

The release script performs clean Wi-Fi 0/2 builds, ABI/layout checks and host
suite; output is the Wi-Fi 2 artifact. A host-only suite without built ELFs uses
recorded memory limits; it does not validate the final compiled footprint.

ARM11 requires Python, Unicorn/Capstone for tests, devkitARM and a privately
supplied exact supported firmware. Set DEVKITPRO appropriately:

```sh
python3 antigravity/build_antigravity.py /private/twl.firm /private/arm11-build
python3 antigravity/test_antigravity.py /private/arm11-build
```

Install bootstrap and locally generated ARM11 module as a verified pair only
with backups. Configuration example: tools/ra.example.cfg. Never publish real
ra.cfg, firmware, generated CXI, ROMs or saves. See antigravity/README.md for
configuration and recovery. Private outputs are not GitHub release assets.

## Status and history

Current compositor aligns the interior HUD cache interval, accepting both
observed framebuffer origins (including 16-byte alignment). The private-buffer
v7.2 candidate failed on hardware and is not the release default.

See docs/RELATORIO_01-11-2026.md and PUBLICATION.md. Historical release text is
archived under docs/history and is not current installation guidance.
