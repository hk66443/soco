#!/usr/bin/env python3
"""Build variant B: original binary + W2IY7p stub + tjJW_G branch + every 88-cap gate branch
turned into an unconditional jump (amd64 core-slice-preserve / core-cleanup-skip equivalent).

Emits:
  - patched binary  -> arm64/bin/soco-arm64.variantB
  - patch list      -> _ops/variantB_patchlist.txt  (va, file_off, before, after)
Also prints the same list so it can be replayed on the device.
"""
import struct
import sys
import hashlib
from capstone import Cs, CS_ARCH_ARM64, CS_MODE_ARM

DIR = r"C:\Users\adminuser\Downloads\soco"
ORIG = DIR + r"\arm64\bin\soga-arm64.original"
OUT = DIR + r"\arm64\bin\soco-arm64.variantB"
LIST = DIR + r"\_ops\variantB_patchlist.txt"
SEG_VA, SEG_OFF, SEG_SZ = 0x23934C0, 0x13834C0, 0x11B1190

# crack-soga10 patches that are kept (gate stub + cbnz)
KEEP = [
    (0x2B6FBDC, bytes.fromhex("e0031f2ac0035fd6"), bytes.fromhex("fe0f1bf8fd831ff8")),  # W2IY7p entry -> mov w0,wzr; ret
    (0x322C544, bytes.fromhex("01000014"), bytes.fromhex("c10300b5")),                   # tjJW_G cbnz -> b .+4
]

md = Cs(CS_ARCH_ARM64, CS_MODE_ARM)


def main():
    d = bytearray(open(ORIG, "rb").read())

    def va2off(va):
        return SEG_OFF + (va - SEG_VA)

    # 1) scan cmp x?, #0x58 sites
    blob = bytes(d[SEG_OFF:SEG_OFF + SEG_SZ])
    cmp_sites = []
    for k in range(0, len(blob) - 4, 4):
        w = struct.unpack_from("<I", blob, k)[0]
        if (w & 0xFFC00000) == 0xF1000000 and ((w >> 10) & 0xFFF) == 0x58:
            cmp_sites.append(SEG_VA + k)
    print("cmp x?,#0x58 sites:", len(cmp_sites))

    # 2) for each site look back up to 3 instructions for a conditional branch on a w reg
    plan = []
    for va in cmp_sites:
        found = None
        for back in (8, 4, 12):
            pc = va - back
            w = struct.unpack_from("<I", d, va2off(pc))[0]
            op = w & 0x7F000000
            kind = None
            if (w & 0x7F000000) == 0x36000000:   # TBZ 32-bit
                kind = "tbz"
            elif (w & 0x7F000000) == 0x34000000:  # CBZ 32-bit
                kind = "cbz"
            elif (w & 0x7F000000) == 0x35000000:  # CBNZ 32-bit
                kind = "cbnz"
            if kind:
                # decode imm14 / imm19
                if kind == "tbz":
                    imm = (w >> 5) & 0x3FFF
                    if imm & 0x2000:
                        imm -= 0x4000
                    rt = w & 0x1F
                    target = pc + imm * 4
                else:
                    imm = (w >> 5) & 0x7FFFF
                    if imm & 0x40000:
                        imm -= 0x80000
                    rt = w & 0x1F
                    target = pc + imm * 4
                found = (pc, kind, target, w)
                break
        plan.append((va, found))

    print("\n%-12s %-12s %-6s %-12s %s" % ("cmp@", "branch@", "kind", "target", "back"))
    rows = []
    for va, f in plan:
        if not f:
            print("%#010x   (no preceding conditional branch within 12 bytes)" % va)
            continue
        pc, kind, target, w = f
        imm26 = (target - pc) // 4
        if not (-0x2000000 <= imm26 < 0x2000000):
            print("%#010x  branch out of range" % va)
            continue
        neww = 0x14000000 | (imm26 & 0x03FFFFFF)
        rows.append((pc, va, target, kind, w, neww))
        print("%#010x %#010x %-6s %#010x  -%d" % (va, pc, kind, target, va - pc))

    print("\nbranches to patch:", len(rows))
    for r in rows:
        pc, va, target, kind, w, neww = r
        d[va2off(pc):va2off(pc) + 4] = struct.pack("<I", neww)

    # 3) apply KEEP patches (on top of original)
    for va, new, old in KEEP:
        d[va2off(va):va2off(va) + len(new)] = new

    open(OUT, "wb").write(bytes(d))
    print("\nwrote", OUT)
    print("sha256:", hashlib.sha256(bytes(d)).hexdigest())

    with open(LIST, "w", encoding="utf-8") as fh:
        fh.write("# variantB: %d gone-branch patches + %d kept crack patches\n" % (len(rows), len(KEEP)))
        fh.write("# format: file_off va before_hex after_hex note\n")
        for pc, va, target, kind, w, neww in rows:
            fh.write("%#x %#x %s %s %s->%#x\n" % (va2off(pc), pc,
                                                  struct.pack("<I", w).hex(),
                                                  struct.pack("<I", neww).hex(), kind, target))
        for va, new, old in KEEP:
            fh.write("%#x %#x %s %s keep-crack\n" % (va2off(va), va, old.hex(), new.hex()))
    print("patch list ->", LIST)

    # 4) verify with capstone
    print("\nspot check:")
    for pc, va, target, kind, w, neww in rows[:6]:
        off = va2off(pc)
        ins = list(md.disasm(bytes(d[off:off + 4]), pc))
        print("  %#x  %s %s   (was %s -> %#x)" % (pc, ins[0].mnemonic if ins else "?",
                                                  ins[0].op_str if ins else "?", kind, target))


if __name__ == "__main__":
    main()