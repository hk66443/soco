set -u
D=/root/lab88
L=/etc/soga/soga-vless-$(date +%Y-%m-%d).log

echo 89 > "$D/n_users"
pkill -f 'soco -c /root/lab88/lab_a.conf' 2>/dev/null || true
pkill -f 'lab88/mock_panel.py' 2>/dev/null || true
sleep 1

nohup python3 "$D/mock_panel.py" > "$D/mock.out" 2>&1 &
sleep 1.2
echo -n "mock users="
curl -s "http://127.0.0.1:18080/api/v1/server/UniProxy/user?node_id=1100&node_type=vless&token=lab" \
  | python3 -c 'import sys,json;print(len(json.load(sys.stdin)["users"]))'

LD_PRELOAD=/usr/local/soco/libsoco.so nohup /usr/local/soco/soco -c "$D/lab_a.conf" > "$D/A89.out" 2>&1 &
sleep 9
PID=$(pgrep -f 'soco -c /root/lab88/lab_a.conf' | head -1)
echo "pid=$PID listen=$(ss -lnt 2>/dev/null | grep -c ':19599 ')"
echo "users=$(grep -a 'current user num' "$L" | tail -1 | sed 's/.*INFO[[:space:]]*//')"

cat > "$D/gdb-close.cmd" <<'EOF'
set pagination off
set confirm off
set $cnt = 0
catch syscall close
commands
  silent
  set $cnt = $cnt + 1
  if $cnt <= 8
    set $f1 = *(void**)$x29
    set $f2 = *(void**)$f1
    set $f3 = *(void**)$f2
    set $f4 = *(void**)$f3
    set $f5 = *(void**)$f4
    printf "C%d lr=%p | f1=%p f2=%p f3=%p f4=%p f5=%p\n", $cnt, $x30, *(void**)($x29+8), *(void**)($f1+8), *(void**)($f2+8), *(void**)($f3+8), *(void**)($f4+8)
  end
  continue
end
continue
EOF

: > "$D/gdb-close.log"
nohup timeout 30 gdb -q -p "$PID" -x "$D/gdb-close.cmd" > "$D/gdb-close.log" 2>&1 &
echo "gdb armed"