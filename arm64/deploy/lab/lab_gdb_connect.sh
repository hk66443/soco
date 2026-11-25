set -u
D=/root/lab88
L=/etc/soga/soga-vless-$(date +%Y-%m-%d).log

echo 88 > "$D/n_users"
pkill -f 'soco -c /root/lab88/lab_a.conf' 2>/dev/null || true
pkill -f 'lab88/mock_panel.py' 2>/dev/null || true
sleep 0.8

nohup python3 "$D/mock_panel.py" > "$D/mock.out" 2>&1 &
sleep 1
head -1 "$D/mock.out"

LD_PRELOAD=/usr/local/soco/libsoco.so nohup /usr/local/soco/soco -c "$D/lab_a.conf" > "$D/A.out" 2>&1 &
sleep 8

PID=$(pgrep -f 'soco -c /root/lab88/lab_a.conf' | head -1)
echo "lab pid=$PID  listen=$(ss -lnt 2>/dev/null | grep -c ':19599 ')"
echo "users=$(grep -a 'current user num' "$L" | tail -1 | sed 's/.*INFO[[:space:]]*//')"

cat > "$D/gdb-connect.cmd" <<'EOF'
set pagination off
set confirm off
set breakpoint pending on
catch syscall connect
commands
  silent
  printf "=== CONNECT HIT pc=%p ===\n", $pc
  bt 12
  printf "=== END HIT ===\n"
  continue
end
continue
EOF

: > "$D/gdb-connect.log"
nohup timeout 40 gdb -q -p "$PID" -x "$D/gdb-connect.cmd" > "$D/gdb-connect.log" 2>&1 &
echo "gdb started, waiting for client..."
sleep 3
grep -c 'CONNECT HIT' "$D/gdb-connect.log" 2>/dev/null || echo "no hit yet"