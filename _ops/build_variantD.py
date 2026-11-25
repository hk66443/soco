import hashlib, struct
DIR=r"C:\Users\adminuser\Downloads\soco"
BASE=DIR+r"\arm64\bin\soco-arm64.variantB"
OUT=DIR+r"\arm64\bin\soco-arm64.variantD"
d=bytearray(open(BASE,"rb").read())
off=0x13834C0+(0x2da85e0-0x23934C0)
assert struct.unpack_from("<I",d,off)[0]==0xF9400B90
d[off:off+12]=struct.pack("<III",0xD2800000,0xD2800001,0xD65F03C0)
open(OUT,"wb").write(bytes(d))
print("variantD sha256:",hashlib.sha256(bytes(d)).hexdigest())
print("size:",len(d))
