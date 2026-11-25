#!/usr/bin/env python3
"""variantF = variantE + `IsEnabled` forced true.

After ~600 s the ARM process stops dialling even though VLESS auth still succeeds
(log: `user N access address` then `handle vless end`, no `tcp direct dial`), i.e. the
outbound gets disabled.  `l_skYd_cVJ.(*U27afyl).IsEnabled` is the predicate on that path;
forcing it true keeps the data plane open.
"""
import hashlib
import struct

DIR = r"C:\Users\adminuser\Downloads\soco"
SRC = DIR + r"\arm64\bin\soco-arm64.variantE"
OUT = DIR + r"\arm64\bin\soco-arm64.variantF"
SEG_VA, SEG_OFF = 0x23934C0, 0x13834C0

ISENABLED = 0x02F7DE60          # true entry (recovered table + 0x40)
MOV_W0_1 = struct.pack("<I", 0x52800020)   # mov w0, #1
RET = struct.pack("<I", 0xD65F03C0)

d = bytearray(open(SRC, "rb").read())
off = SEG_OFF + (ISENABLED - SEG_VA)
before = bytes(d[off:off + 8])
assert struct.unpack_from("<I", before)[0] == 0xF9400B90, before.hex()
d[off:off + 8] = MOV_W0_1 + RET
open(OUT, "wb").write(bytes(d))
print("out   :", OUT)
print("sha256:", hashlib.sha256(bytes(d)).hexdigest())
print("  va=%#010x off=%#08x  %s -> %s" % (ISENABLED, off, before.hex(), (MOV_W0_1 + RET).hex()))