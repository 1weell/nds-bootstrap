ENTRY(ra_loader)
SECTIONS {
    . = 0x0012e160;
    __payload_start = .;
    .text : { KEEP(*(.loader)) *(.text*) *(.cache) }
    .rodata : { *(.rodata*) }
    .data : { *(.data*) }
    . = ALIGN(4);
    __payload_file_end = .;
    .bss (NOLOAD) : {
        __bss_start = .;
        *(.bss*) *(COMMON)
        . = ALIGN(4);
        __bss_end = .;
    }
    __reserved_end = ALIGN(0x1000);
    ASSERT(__reserved_end <= 0x00132000, "Payload consumes more than reserved AXI budget")
    /DISCARD/ : { *(.comment*) *(.ARM.exidx*) *(.ARM.extab*) }
}
