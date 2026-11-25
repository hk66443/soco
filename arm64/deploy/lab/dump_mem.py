import sys

pid = int(sys.argv[1])
start = int(sys.argv[2], 0)
size = int(sys.argv[3], 0)
out = sys.argv[4]

with open("/proc/%d/mem" % pid, "rb", buffering=0) as f:
    f.seek(start)
    data = f.read(size)

with open(out, "wb") as f:
    f.write(data)
print("%d bytes -> %s" % (len(data), out))