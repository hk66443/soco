#!/usr/bin/env python3
"""Build ARM soco variants from crack-soga10:
Variant A: restore the 8 whole-function stubs on xVhdeAZ_or (keep W2IY7p stub + tjJW_G patch).
"""
import hashlib
import sys

DIR = r"C:\Users\adminuser\Downloads\soco\arm64\bin"
ORIG = DIR + r"\soga-arm64.original"
CRACK = DIR + r"\soga-arm64.crack-soga10"
OUT = DIR + r"\soco-arm64.variantA"
DELTA = 0x1010000  # va - file_off inside the RX segment

STUB_SITES = [0x30627B0, 0x3080AF0, 0x3086FA0, 0x3094D10, 0x30A2F08, 0x30B3120, 0x30BA3F0, 0x30C3BB0]
STUB_MOV = bytes.fromhex("e0031faa")   # mov x0, xzr
STUB_MOV3 = bytes.fromhex("e3031faa")  # mov x3, xzr


def main():
    orig = open(ORIG, "rb").read()
    data = bytearray(open(CRACK, "rb").read())
    print("crack sha256:", hashlib.sha256(data).hexdigest())
    changed = 0
    for va in STUB_SITES:
        off = va - DELTA
        cur = bytes(data[off:off + 4])
        src = bytes(orig[off:off + 4])
        print("%#x off=%#x  crack=%s orig=%s" % (va, off, cur.hex(), src.hex()))
        if cur == src:
            print("   !! identical, nothing to restore")
            continue
        data[off:off + 4] = src
        changed += 1
    open(OUT, "wb").write(bytes(data))
    print("wrote", OUT, "restored", changed, "sites")
    print("variantA sha256:", hashlib.sha256(bytes(data)).hexdigest())
    # confirm the 43-byte diff baseline: count differing bytes crack vs variantA
    diff = sum(1 for a, b in zip(bytes(data), open(CRACK, "rb").read()) if a != b)
    print("bytes differing from crack:", diff)


if __name__ == "__main__":
    main()