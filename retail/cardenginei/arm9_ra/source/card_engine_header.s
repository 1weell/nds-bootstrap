@---------------------------------------------------------------------------------
@ Entry point for cardenginei_arm9_ra, the RetroAchievements code that does not fit
@ in the ARM9 cardengine's 12K window. Loaded into DSi WRAM and called once per
@ frame; see docs/retroachievements.md.
@
@ The layout is the colour LUT's, deliberately, because the loader recognises it:
@ the first word must be a branch, so `*(u16*)(location + 2)` reads 0xEA00 and an
@ unloaded window -- which holds whatever was there before -- can be told apart from
@ real code. The flags word at +4 is there for the launcher to write configuration
@ into before the binary is copied across, the same way the colour LUT receives its.
@---------------------------------------------------------------------------------
	.section ".init"
@---------------------------------------------------------------------------------
	.align	4
	.arm

card_engine_start:

	b ra_wram_tick

.global raWramFlags
raWramFlags:
.word 0

@ Versioned graphics entries; offsets pinned by release verification.
	b raGfxDmaEpilogue
	b raGfxBankEpilogue
.word 0x31475052
.global raGfxHookStatus
raGfxHookStatus:
.word 0

.pool

card_engine_end:

@ Synchronous SDK epilogues. Preserve caller state and exclude VBlank while
@ refreshing shared overlay state. No allocator, lifetime tick or RA evaluation.
.text
.align 2
raGfxDmaEpilogue:
 stmdb sp!, {r0-r3,r12,lr}
 ldr r12, =0x07000400
 cmp r5, r12
 bne 1f
 ldr r12, =0x84000100
 cmp r4, r12
 bne 1f
 bl raGfxRefreshCritical
1:
 ldmia sp!, {r0-r3,r12,lr}
 add sp, sp, #4
 ldmia sp!, {r4-r7,pc}

raGfxBankEpilogue:
 stmdb sp!, {r0-r3,r12,lr}
 bl raGfxRefreshCritical
 ldmia sp!, {r0-r3,r12,lr}
 add sp, sp, #4
 ldmia sp!, {pc}

raGfxRefreshCritical:
 mrs r2, cpsr
 orr r3, r2, #0x80
 msr cpsr_c, r3
 stmdb sp!, {r2,lr}
 bl ra_overlay_after_upload
 ldmia sp!, {r2,lr}
 msr cpsr_c, r2
 bx lr
.pool
