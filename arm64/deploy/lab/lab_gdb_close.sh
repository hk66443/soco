set -u
D=/root/lab88
L=/etc/soga/soga-vless-$(date +%Y-%m-%d).log

echo 89 > "$D/n_users"
pkill -f 'soco -c /root/lab88/lab_a.conf' 2>/dev/null || true
sleep 1

LD_PRELOAD=/usr/local/soco/libsoco.so nohup /usr/local/soco/soco -c "$D/lab_a.conf" > "$D/A89.out" 2>&1 &
sleep 8
PID=$(pgrep -f 'soco -c /root/lab88/lab_a.conf' | head -1)
echo "lab pid=$PID listen=$(ss -lnt 2>/dev/null | grep -c ':19599 ')"
echo "users=$(grep -a 'current user num' "$L" | tail -1 | sed 's/.*INFO[[:space:]]*//')"

cat > "$D/gdb-close.cmd" <<'EOF'
set pagination off
set confirm off
set $cnt = 0
catch syscall close
commands
  silent
  set $cnt = $cnt + 1
  if $cnt <= 12
    printf "=== CLOSE #%d pc=%p lr=%p fp=%p ===\n", $cnt, $pc, $x30, $x29
    printf "  fp[0]=%p fp[1]=%p\n", *(void**)$x29, *(void**)($x29+8)
    printf "  fp2[0]=%p fp2[1]=%p\n", *(void**)*(void**)$x29, *(void**)(*(void**)$x29+8)
    printf "  fp3[0]=%p fp3[1]=%p\n", *(void**)*(void**)*(void**)$x29, *(void**)(*(void**)*(void**)$x29+8)
  end
  continue
end
continue
EOF

: > "$D/gdb-close.log"
nohup timeout 35 gdb -q -p "$PID" -x "$D/gdb-close.cmd" > "$D/gdb-close.log" 2>&1 &
echo "gdb watching close..."
sleep 2