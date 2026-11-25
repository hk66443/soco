#!/usr/bin/env bash
# lab_perf2.sh <n_users> — 用户态采样版
set -u
N=${1:?usage: lab_perf2.sh <n_users>}
D=/root/lab88
PERF=/usr/bin/perf_5.10
[ -x "$PERF" ] || PERF=/usr/bin/perf

echo "$N" > "$D/n_users"
pkill -f 'soco -c /root/lab88' 2>/dev/null || true
sleep 1.2
pgrep -f 'lab88/mock_panel.py' > /dev/null || { nohup python3 "$D/mock_panel.py" > "$D/mock.out" 2>&1 & sleep 1.2; }

LD_PRELOAD=/usr/local/soco/libsoco.so nohup /usr/local/soco/soco -c "$D/lab_a.conf" > "$D/p$N.out" 2>&1 &
sleep 9
PID=$(pgrep -f 'soco -c /root/lab88/lab_a.conf' | head -1)
echo "n=$N pid=$PID listen=$(ss -lnt 2>/dev/null | grep -c ':19599 ') add=$(grep -ac 'add user' "$D/p$N.out")"

# 用户态 CPU 采样，高频，10 秒
nohup "$PERF" record -e cycles:u -F 5000 -p "$PID" -o "$D/perf-$N.data" -- sleep 10 > "$D/perf-$N.log" 2>&1 &
sleep 1
sed -n '1,2p' "$D/perf-$N.log" 2>/dev/null || true
echo "perf armed (n=$N, userspace)"