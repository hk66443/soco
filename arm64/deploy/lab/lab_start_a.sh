set -u
D=/root/lab88
L=/etc/soga/soga-vless-$(date +%Y-%m-%d).log

pkill -f 'lab88/mock_panel.py' 2>/dev/null || true
pkill -f 'lab_a.conf' 2>/dev/null || true
sleep 0.6

nohup python3 "$D/mock_panel.py" > "$D/mock.out" 2>&1 &
sleep 1.2
head -1 "$D/mock.out"

start=$(wc -l < "$L" 2>/dev/null || echo 0)
LD_PRELOAD=/usr/local/soco/libsoco.so nohup /usr/local/soco/soco -c "$D/lab_a.conf" > "$D/A.out" 2>&1 &
sleep 9

seg=$(tail -n +$((start + 1)) "$L" 2>/dev/null)
echo "add user 总次数 : $(printf '%s' "$seg" | grep -ac 'add user' || true)"
echo "current user num: $(printf '%s' "$seg" | grep -a 'current user num' | tail -1 | sed 's/.*INFO[[:space:]]*//' || true)"
echo "listen          : $(ss -lnt 2>/dev/null | grep ':19599 ' | head -1)"
echo "reality 参数    : $(head -1 "$D/mock.out" | python3 -c 'import sys,json;d=json.load(sys.stdin);print("pbk="+d["pbk"],"sid="+d["sid"],"port="+str(d["ports"]["1100"]))')"
echo "mock 收到请求   : $(wc -l < "$D/mock-access.log" 2>/dev/null || echo 0) 条"
cat "$D/mock-access.log" 2>/dev/null | head -5