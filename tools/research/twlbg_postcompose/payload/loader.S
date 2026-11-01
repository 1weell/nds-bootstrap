.syntax unified
.cpu mpcore
.thumb
.section .loader,"ax",%progbits
.global ra_loader
.type ra_loader,%function
.thumb_func
ra_loader:
    push {r3-r7, lr}
    /* Preserve the original cache operation on the relocated Nintendo code. */
    ldr r3, =0x003053e0
    blx r3
    ldr r4, =RA_NATIVE_SOURCE
    ldr r5, =__payload_start
    ldr r6, =__payload_file_end
    subs r6, r6, r5
1:
    ldr r0, [r4]
    str r0, [r5]
    adds r4, #4
    adds r5, #4
    subs r6, #4
    bne 1b
    ldr r4, =__bss_start
    ldr r5, =__bss_end
    movs r0, #0
2:
    cmp r4, r5
    bhs 3f
    str r0, [r4]
    adds r4, #4
    b 2b
3:
    ldr r0, =__payload_start
    ldr r1, =__payload_file_end
    subs r1, r1, r0
    ldr r3, =0x003053e0
    blx r3
    pop {r3-r7, pc}
.size ra_loader, .-ra_loader
.ltorg

.section .cache,"ax",%progbits
.global ra_invalidate
.type ra_invalidate,%function
.thumb_func
ra_invalidate:
    mov r2, r1
    mov r1, r0
    ldr r0, =0x00120ef4
    ldr r0, [r0]
    svc #0x52
    bx lr
.size ra_invalidate, .-ra_invalidate
.ltorg
