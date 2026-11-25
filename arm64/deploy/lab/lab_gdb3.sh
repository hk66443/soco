#!/usr/bin/env bash
# lab_gdb3.sh <n_users> — 在 0x2e1b8d0（per-user server 创建）上计数
set -u
N=${1:?usage: lab_gdb3.sh <n_users>}
D=/root/lab88

echo "$N" > "$D/n_users"
pkill -f 'soco -c /root/lab88/lab_a.conf' 2>/dev/null || true
sleep 1.2
pgrep -f 'lab88/mock_panel.py' > /dev/null || { nohup python3 "$D/mock_panel.py" > "$D/mock.out" 2>&1 & sleep 1.2; }

LD_PRELOAD=/usr/local/soco/libsoco.so nohup /usr/local/soco/soco -c "$D/lab_a.conf" > "$D/h$N.out" 2>&1 &
sleep 10
PID=$(pgrep -f 'soco -c /root/lab88/lab_a.conf' | head -1)
echo "n=$N pid=$PID add=$(grep -ac 'add user' "$D/h$N.out") listen=$(ss -lnt 2>/dev/null | grep -c ':19599 ')"

cat > "$D/gdb3.cmd" <<'EOF'
set pagination off
set confirm off
set $cnt = 0
set $err = 0
break *0x2e1b8d0
commands
  silent
  set $cnt = $cnt + 1
  finish
  if $x0 != 0
    set $err = $err + 1
  end
  continue
end
continue
EOF

: > "$D/gdb3-$N.log"
nohup timeout 25 gdb -q -p "$PID" -x "$D/gdb3.cmd" > "$D/gdb3-$N.log" 2>&1 &
echo "gdb armed (break 0x2e1b8d0)"