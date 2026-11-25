#!/usr/bin/env bash
# lab_findstr.sh — 起实例并在内存里找解密后的日志字符串明文
set -u
D=/root/lab88
L=/etc/soga/soga-vless-$(date +%Y-%m-%d).log

echo 100 > "$D/n_users"
pkill -f 'soco -c /root/lab88/lab_a.conf' 2>/dev/null || true
sleep 1.2
pgrep -f 'lab88/mock_panel.py' > /dev/null || { nohup python3 "$D/mock_panel.py" > "$D/mock.out" 2>&1 & sleep 1.2; }

LD_PRELOAD=/usr/local/soco/libsoco.so nohup /usr/local/soco/soco -c "$D/lab_a.conf" > "$D/fs.out" 2>&1 &
sleep 11
PID=$(pgrep -f 'soco -c /root/lab88/lab_a.conf' | head -1)
echo "pid=$PID add=$(grep -ac 'add user' "$D/fs.out") listen=$(ss -lnt 2>/dev/null | grep -c ':19599 ')"

# dump 三段可写区（.data / bss 前 4MB / 尾段）
python3 "$D/dump_mem.py" "$PID" 0x3554650 199088    "$D/m-data.bin"   2>&1 | sed 's/^/  /'
python3 "$D/dump_mem.py" "$PID" 0x35949c0 0x400000  "$D/m-bss.bin"    2>&1 | sed 's/^/  /'
python3 "$D/dump_mem.py" "$PID" 0x87cf4c0 279760    "$D/m-tail.bin"   2>&1 | sed 's/^/  /'

echo
echo "=== 在 dump 里搜解密后的日志字符串 ==="
python3 - <<'PY'
import os
BASE = {'m-data.bin': 0x3554650, 'm-bss.bin': 0x35949c0, 'm-tail.bin': 0x87cf4c0}
NEEDLES = [b'domain resolved', b'detect tls host', b'handle vless end', b'access address',
           b'current user num', b'tcp direct dial', b'start tcp relay', b'add user',
           b'ban private ip', b'VLESS listen']
for fn, base in BASE.items():
    p = '/root/lab88/' + fn
    if not os.path.exists(p):
        continue
    d = open(p, 'rb').read()
    for n in NEEDLES:
        st = 0
        hits = []
        while True:
            j = d.find(n, st)
            if j < 0:
                break
            hits.append(base + j)
            st = j + 1
            if len(hits) > 4:
                break
        if hits:
            print("  %-14s in %-12s @ %s" % (n.decode(), fn, [hex(h) for h in hits]))
PY