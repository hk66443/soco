set -u
# 88 上限 A/B 实验：crack（+适配层） vs 官方原版，同一个 mock 面板下发 100 个用户
D=/root/lab88
L=/etc/soga/soga-vless-$(date +%Y-%m-%d).log
mkdir -p "$D"

echo "######################## mock 面板自检 ########################"
pkill -f 'lab88/mock_panel.py' 2>/dev/null || true
sleep 0.5
nohup python3 "$D/mock_panel.py" > "$D/mock.out" 2>&1 &
MPID=$!
sleep 1.2
head -1 "$D/mock.out"
for n in 1100 1101; do
  echo -n "node $n users="
  curl -s "http://127.0.0.1:18080/api/v1/server/UniProxy/user?node_id=$n&node_type=vless&token=lab" \
    | python3 -c 'import sys,json;d=json.load(sys.stdin);print(len(d["users"]))'
done
echo -n "node 1100 server_port="
curl -s "http://127.0.0.1:18080/api/v1/server/UniProxy/config?node_id=1100&node_type=vless&token=lab" \
  | python3 -c 'import sys,json;d=json.load(sys.stdin);print(d["server_port"], d["flow"], d["tls_settings"]["short_id"])'

run_one() {
  name=$1; conf=$2; port=$3; mode=$4
  start=0
  [ -f "$L" ] && start=$(wc -l < "$L")
  echo
  echo "######################## $name (port $port) ########################"
  if [ "$mode" = "crack" ]; then
    LD_PRELOAD=/usr/local/soco/libsoco.so /usr/local/soco/soco -c "$conf" > "$D/$name.out" 2>&1 &
  else
    /usr/local/soga/soga -c "$conf" > "$D/$name.out" 2>&1 &
  fi
  pid=$!
  sleep 14
  seg=$(tail -n +$((start + 1)) "$L" 2>/dev/null)
  echo "  add user 次数        : $(printf '%s' "$seg" | grep -ac 'add user' || true)"
  echo "  current user num     : $(printf '%s' "$seg" | grep -a 'current user num' | tail -1 | sed 's/.*INFO[[:space:]]*//' || true)"
  echo "  VLESS listen         : $(printf '%s' "$seg" | grep -a 'VLESS listen' | head -1 | sed 's/.*INFO[[:space:]]*//' || true)"
  echo "  端口在听             : $(ss -lnt 2>/dev/null | grep -c ":$port " || true)"
  echo "  add user 最大 id     : $(printf '%s' "$seg" | grep -ao 'add user: id: [0-9]*' | awk -F': ' '{print $3}' | sort -n | tail -1 || true)"
  echo "  --- 起始 6 行 ---"
  printf '%s' "$seg" | head -6 | sed 's/^/    /'
  kill "$pid" 2>/dev/null || true
  sleep 2
  kill -9 "$pid" 2>/dev/null || true
}

run_one A-crack    "$D/lab_a.conf" 19599 crack
run_one B-official "$D/lab_b.conf" 19699 official

kill "$MPID" 2>/dev/null || true
echo
echo "######################## 收尾 ########################"
ss -lnt 2>/dev/null | grep -E ':(19599|19699|18080) ' || echo "实验端口已全部关闭"
echo "生产 soco 未受影响: $(systemctl is-active soco) pid=$(systemctl show soco -p MainPID --value)"