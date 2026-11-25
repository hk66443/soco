#!/usr/bin/env python3
"""variantE = variantC + the 8 `mov #3 -> mov xzr` patches that the old crack build had.

The previous production build (crack-soga10, 37332960…) carried 8 extra single-patch sites at
the `xVhdeAZ_or` decision points: `mov x0,#3` / `mov x3,#3` -> `mov xzr`.  Those were dropped
when variantB was rebuilt from the original binary, and their absence is what brings the
600-second data-plane gate back.  This variant restores them on top of variantC.
"""
import hashlib
import struct

DIR = r"C:\Users\adminuser\Downloads\soco"
SRC = DIR + r"\arm64\bin\soco-arm64.variantC"
OUT = DIR + r"\arm64\bin\soco-arm64.variantE"
SEG_VA, SEG_OFF = 0x23934C0, 0x13834C0

MOV_X0_ZR = struct.pack("<I", 0xAA1F03E0)   # mov x0, xzr
MOV_X3_ZR = struct.pack("<I", 0xAA1F03E3)   # mov x3, xzr
MOV_X0_3 = struct.pack("<I", 0xD2400060)    # movz x0, #3   (original)

SITES = [
    (0x030627B0, MOV_X0_ZR),
    (0x03080AF0, MOV_X0_ZR),
    (0x03086FA0, MOV_X0_ZR),
    (0x03094D10, MOV_X0_ZR),
    (0x030A2F08, MOV_X0_ZR),
    (0x030B3120, MOV_X0_ZR),
    (0x030BA3F0, MOV_X0_ZR),
    (0x030C3BB0, MOV_X3_ZR),
]

d = bytearray(open(SRC, "rb").read())
rows = []
for va, new in SITES:
    off = SEG_OFF + (va - SEG_VA)
    before = bytes(d[off:off + 4])
    assert struct.unpack("<I", before)[0] in (0xD2400060, 0xD2400063), (hex(va), before.hex())
    d[off:off + 4] = new
    rows.append((va, off, before.hex(), new.hex()))

open(OUT, "wb").write(bytes(d))
print("out   :", OUT)
print("sha256:", hashlib.sha256(bytes(d)).hexdigest())
for va, off, b, a in rows:
    print("  va=%#010x off=%#08x  %s -> %s" % (va, off, b, a))