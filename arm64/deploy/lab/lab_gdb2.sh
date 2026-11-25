#!/usr/bin/env bash
# lab_gdb2.sh <n_users> — 起实例并在 close 上抓 x29 帧链（6 层）
set -u
N=${1:?usage: lab_gdb2.sh <n_users>}
D=/root/lab88
L=/etc/soga/soga-vless-$(date +%Y-%m-%d).log

echo "$N" > "$D/n_users"
pkill -f 'soco -c /root/lab88/lab_a.conf' 2>/dev/null || true
sleep 1.2
pgrep -f 'lab88/mock_panel.py' > /dev/null || { nohup python3 "$D/mock_panel.py" > "$D/mock.out" 2>&1 & sleep 1.2; }

LD_PRELOAD=/usr/local/soco/libsoco.so nohup /usr/local/soco/soco -c "$D/lab_a.conf" > "$D/g$N.out" 2>&1 &
sleep 10
PID=$(pgrep -f 'soco -c /root/lab88/lab_a.conf' | head -1)
echo "n=$N pid=$PID add=$(grep -ac 'add user' "$D/g$N.out") listen=$(ss -lnt 2>/dev/null | grep -c ':19599 ')"

cat > "$D/gdb2.cmd" <<'EOF'
set pagination off
set confirm off
set $cnt = 0
catch syscall close
commands
  silent
  set $cnt = $cnt + 1
  if $cnt <= 6
    set $f1 = *(void**)$x29
    set $f2 = *(void**)$f1
    set $f3 = *(void**)$f2
    set $f4 = *(void**)$f3
    set $f5 = *(void**)$f4
    set $f6 = *(void**)$f5
    printf "C%d lr=%p | %p %p %p %p %p %p\n", $cnt, $x30, *(void**)($x29+8), *(void**)($f1+8), *(void**)($f2+8), *(void**)($f3+8), *(void**)($f4+8), *(void**)($f5+8)
  end
  continue
end
continue
EOF

: > "$D/gdb2-$N.log"
nohup timeout 40 gdb -q -p "$PID" -x "$D/gdb2.cmd" > "$D/gdb2-$N.log" 2>&1 &
echo "gdb armed n=$N"