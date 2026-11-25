#!/usr/bin/env bash
# lab_vless.sh <n_users> — 在 amd 上起 vless/REALITY 隔离实例（19590）
set -u
N=${1:?usage: lab_vless.sh <n_users>}
D=/root/labss

mkdir -p "$D"
echo "$N" > "$D/n_users"

# 按端口清场
for i in 1 2 3; do
  PIDS=$(ss -lntp 2>/dev/null | grep ':19590 ' | grep -oE 'pid=[0-9]+' | cut -d= -f2)
  [ -z "$PIDS" ] && break
  kill -9 $PIDS 2>/dev/null || true
  sleep 1
done

pkill -f 'labss/mock_panel_vless.py' 2>/dev/null || true
sleep 1
nohup python3 "$D/mock_panel_vless.py" > "$D/mock-vless.out" 2>&1 &
sleep 1.5
head -1 "$D/mock-vless.out"
echo -n "mock users = "
curl -s "http://127.0.0.1:18081/api/v1/server/UniProxy/user?node_id=1101&node_type=vless&token=lab" \
  | python3 -c 'import sys,json;print(len(json.load(sys.stdin)["users"]))'

LD_PRELOAD=/usr/local/soco/libsoco.so nohup /usr/local/soco/soco -c "$D/lab_vless.conf" > "$D/v$N.out" 2>&1 &
sleep 11
PID=$(pgrep -f 'soco -c /root/labss/lab_vless.conf' | head -1)
echo "pid=$PID listen=$(ss -lnt 2>/dev/null | grep -c ':19590 ')"
echo "适配层 = $(grep -a '\[soco\] users=' "$D/v$N.out" | tail -1)"
echo "add    = $(grep -ac 'add user' "$D/v$N.out")"
echo "usernum= $(grep -a 'current user num' "$D/v$N.out" | tail -1 | sed 's/.*INFO[[:space:]]*//')"
echo "binderr= $(grep -ac 'address already in use' "$D/v$N.out")"
grep -aE 'VLESS listen' "$D/v$N.out" | sed -n '1p'