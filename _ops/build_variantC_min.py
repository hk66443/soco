#!/usr/bin/env python3
"""Split variantC into minimal sub-variants so the production patch surface can
be kept as small as possible.

  vC-nil-xboard   : variantB + E2L2TNbFODvd.O8ecjRSd0zK (xboard nil-error leaf) only
  vC-nil-generic  : variantB + E2L2TNbFODvd.IfBgxLwq4 only
  vC-closure-vless: variantB + the 4 VLESS (JfPfDr1BO) cleanup closures only
"""
import hashlib
import struct

DIR = r"C:\Users\adminuser\Downloads\soco"
BASE = DIR + r"\arm64\bin\soco-arm64.variantB"
SEG_VA, SEG_OFF = 0x23934C0, 0x13834C0
DELTA = 0x40
RET = struct.pack("<I", 0xD65F03C0)
ZERO2 = struct.pack("<III", 0xD2800000, 0xD2800001, 0xD65F03C0)

NIL_XBOARD = 0x02DA85A0
NIL_GENERIC = 0x02D92C10
CLOSURES_VLESS = [0x031B7800, 0x031B97B0, 0x031BB8A0, 0x031BD980]
CLOSURES_SS = [0x0319F580, 0x031A1540, 0x031A3540, 0x031A5560]

VARIANTS = {
    "vC-nil-xboard": [("nil", NIL_XBOARD)],
    "vC-nil-generic": [("nil", NIL_GENERIC)],
    "vC-closure-vless": [("closure", v) for v in CLOSURES_VLESS],
    "vC-closure-ss": [("closure", v) for v in CLOSURES_SS],
}


def build(name, items):
    d = bytearray(open(BASE, "rb").read())
    for kind, raw in items:
        va = raw + DELTA
        off = SEG_OFF + (va - SEG_VA)
        patch = ZERO2 if kind == "nil" else RET
        assert struct.unpack_from("<I", d, off)[0] == 0xF9400B90, (name, hex(va))
        d[off:off + len(patch)] = patch
    out = DIR + r"\arm64\bin\soco-arm64." + name
    open(out, "wb").write(bytes(d))
    print("%-18s %s  patches=%d" % (name, hashlib.sha256(bytes(d)).hexdigest()[:16], len(items)))


for name, items in VARIANTS.items():
    build(name, items)