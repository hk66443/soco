set -u
D=/root/lab88
N=$1
L=/etc/soga/soga-vless-$(date +%Y-%m-%d).log

echo "$N" > "$D/n_users"
pkill -f 'soco-capfix' 2>/dev/null || true
sleep 1
pgrep -f 'lab88/mock_panel.py' >/dev/null || { nohup python3 "$D/mock_panel.py" > "$D/mock.out" 2>&1 & sleep 1.2; }

LD_PRELOAD=/usr/local/soco/libsoco.so nohup "$D/soco-capfix" -c "$D/lab_a.conf" > "$D/capfix-$N.out" 2>&1 &
sleep 10
PID=$(pgrep -f 'soco-capfix' | head -1)
echo "n=$N pid=$PID listen=$(ss -lnt 2>/dev/null | grep -c ':19599 ')"
echo "users=$(grep -a 'current user num' "$L" | tail -1 | sed 's/.*INFO[[:space:]]*//')"
echo "add_user=$(grep -ac 'add user' "$D/capfix-$N.out" 2>/dev/null || echo 0)"
grep -a 'VLESS listen' "$D/capfix-$N.out" | head -1 | sed 's/^/  /'