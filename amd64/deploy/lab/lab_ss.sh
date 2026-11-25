#!/usr/bin/env bash
# lab_ss.sh <n_users> — 在 amd 上起隔离实例（mock 面板 + 19589）并输出状态
set -u
N=${1:?usage: lab_ss.sh <n_users>}
D=/root/labss
L=/etc/soga/soga-ss-$(date +%Y-%m-%d).log

mkdir -p "$D"
echo "$N" > "$D/n_users"

pkill -f 'soco -c /root/labss/lab_ss.conf' 2>/dev/null || true
pkill -f 'labss/mock_panel_ss.py' 2>/dev/null || true
sleep 1

nohup python3 "$D/mock_panel_ss.py" > "$D/mock.out" 2>&1 &
sleep 1.5
head -1 "$D/mock.out"
echo -n "mock users = "
curl -s "http://127.0.0.1:18080/api/v1/server/UniProxy/user?node_id=1100&node_type=shadowsocks&token=lab" \
  | python3 -c 'import sys,json;print(len(json.load(sys.stdin)["users"]))'

START=0
[ -f "$L" ] && START=$(wc -l < "$L")
LD_PRELOAD=/usr/local/soco/libsoco.so nohup /usr/local/soco/soco -c "$D/lab_ss.conf" > "$D/lab$N.out" 2>&1 &
sleep 10
PID=$(pgrep -f 'soco -c /root/labss/lab_ss.conf' | head -1)
echo "pid=$PID listen=$(ss -lnt 2>/dev/null | grep -c ':19589 ')"
echo "add user = $(grep -ac 'add user' "$D/lab$N.out")"
echo "适配层   = $(grep -a '\[soco\]' "$D/lab$N.out" | tail -1)"
echo "用户数   = $(grep -a 'current user num' "$D/lab$N.out" | tail -1 | sed 's/.*INFO[[:space:]]*//')"
echo "--- 启动关键行 ---"
grep -aE 'Shadowsocks listen|create shadowsocks|current user num' "$D/lab$N.out" | sed -n '1,3p'