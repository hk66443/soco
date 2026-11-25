set -u
D=/root/lab88
N=$1
L=/etc/soga/soga-vless-$(date +%Y-%m-%d).log

echo "$N" > "$D/n_users"
pkill -f 'soco -c /root/lab88/lab_a.conf' 2>/dev/null || true
sleep 1
pgrep -f 'lab88/mock_panel.py' >/dev/null || { nohup python3 "$D/mock_panel.py" > "$D/mock.out" 2>&1 & sleep 1.2; }

LD_PRELOAD=/usr/local/soco/libsoco.so nohup /usr/local/soco/soco -c "$D/lab_a.conf" > "$D/A-$N.out" 2>&1 &
sleep 11
PID=$(pgrep -f 'soco -c /root/lab88/lab_a.conf' | head -1)
echo "n=$N pid=$PID listen=$(ss -lnt 2>/dev/null | grep -c ':19599 ') users=$(grep -a 'current user num' "$L" | tail -1 | sed 's/.*INFO[[:space:]]*//')"

python3 "$D/dump_mem.py" "$PID" 0x3554650 199088   "$D/mem-$N-data.bin"
python3 "$D/dump_mem.py" "$PID" 0x87cf4c0 279760   "$D/mem-$N-data2.bin"

kill "$PID" 2>/dev/null || true
sleep 1
kill -9 "$PID" 2>/dev/null || true