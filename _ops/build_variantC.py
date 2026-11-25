#!/usr/bin/env python3
"""Build variant C on top of variant B.

variant B (42 gone-branch patches + the two crack patches) fixed the *loading*
layer: ARM soco now really holds 100 users in memory.  The data plane is still
closed at count>88, so this variant ports the last 10 amd64 intents that were
never applied to ARM:

  * 8 x control-ss-vless-leaf : the SS / VLESS "test control" cleanup goroutine
    closures get `ret` at their (verified) entry, exactly like amd64 did with
    1-byte 0x49 -> 0xC3.
  * 2 x nil-error-leaf        : the generic + xboard local nil-error leaves
    return zeroed results (amd64: 4c8d6424d8 -> 31c031dbc3).

Entry addresses come from arm64.funcs.fixed.json (reconstructed functab + 0x40,
verified against the Go stack-split prologue).
"""
import hashlib
import struct

from capstone import Cs, CS_ARCH_ARM64, CS_MODE_ARM

DIR = r"C:\Users\adminuser\Downloads\soco"
BASE = DIR + r"\arm64\bin\soco-arm64.variantB"
OUT = DIR + r"\arm64\bin\soco-arm64.variantC"
LIST = DIR + r"\_ops\variantC_patchlist.txt"
SEG_VA, SEG_OFF, SEG_SZ = 0x23934C0, 0x13834C0, 0x11B1190

RET = struct.pack("<I", 0xD65F03C0)                     # ret
ZERO2 = struct.pack("<III", 0xD2800000, 0xD2800001, 0xD65F03C0)  # mov x0,#0; mov x1,#0; ret

# (label, va_raw_in_functab, patched_bytes)
CLOSURES = [
    ("Ke3Pasll._jIcEtfai4.func2.func1", 0x0319F580),
    ("Ke3Pasll._jIcEtfai4.func1.func1", 0x031A1540),
    ("Ke3Pasll.jvauV_P.func1.func1", 0x031A3540),
    ("Ke3Pasll.jvauV_P.func2.func1", 0x031A5560),
    ("JfPfDr1BO._jIcEtfai4.func2.func1", 0x031B7800),
    ("JfPfDr1BO._jIcEtfai4.func1.func1", 0x031B97B0),
    ("JfPfDr1BO.jvauV_P.func2.func1", 0x031BB8A0),
    ("JfPfDr1BO.jvauV_P.func1.func1", 0x031BD980),
]
NIL = [
    ("E2L2TNbFODvd.O8ecjRSd0zK (xboard nil-error leaf)", 0x02DA85A0),
    ("E2L2TNbFODvd.IfBgxLwq4 (generic nil-error leaf)", 0x02D92C10),
]
DELTA = 0x40

md = Cs(CS_ARCH_ARM64, CS_MODE_ARM)


def main():
    d = bytearray(open(BASE, "rb").read())

    def va2off(va):
        return SEG_OFF + (va - SEG_VA)

    rows = []
    for label, raw in CLOSURES:
        va = raw + DELTA
        off = va2off(va)
        before = bytes(d[off:off + 4])
        w = struct.unpack("<I", before)[0]
        assert w == 0xF9400B90, "%s: entry %#x is not a stack-check prologue (%#x)" % (label, va, w)
        d[off:off + 4] = RET
        rows.append((label, va, off, before.hex(), RET.hex()))

    for label, raw in NIL:
        va = raw + DELTA
        off = va2off(va)
        before = bytes(d[off:off + 12])
        w = struct.unpack_from("<I", before)[0]
        assert w == 0xF9400B90, "%s: entry %#x is not a stack-check prologue (%#x)" % (label, va, w)
        d[off:off + 12] = ZERO2
        rows.append((label, va, off, before.hex(), ZERO2.hex()))

    open(OUT, "wb").write(bytes(d))
    h = hashlib.sha256(bytes(d)).hexdigest()

    with open(LIST, "w", encoding="utf-8") as fh:
        fh.write("# variantC = variantB + 8 closure rets + 2 nil-error leaves\n")
        fh.write("# format: file_off va before_hex after_hex label\n")
        for label, va, off, b, a in rows:
            fh.write("%#x %#x %s %s %s\n" % (off, va, b, a, label))

    print("base  :", BASE)
    print("out   :", OUT)
    print("sha256:", h)
    print("patches:", len(rows))
    for label, va, off, b, a in rows:
        ins = list(md.disasm(bytes(d[off:off + 12]), va))[:2]
        print("  va=%#010x off=%#08x  %-46s -> %s" % (
            va, off, label,
            "; ".join("%s %s" % (i.mnemonic, i.op_str) for i in ins)))


if __name__ == "__main__":
    main()