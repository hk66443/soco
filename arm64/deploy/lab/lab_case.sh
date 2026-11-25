set -u
n=${1:-100}
pre=${2:-1}
L=/etc/soga/soga-vless-$(date +%Y-%m-%d).log

echo "$n" > /root/lab88/n_users
pkill -f 'soco -c /root/lab88/lab_a.conf' 2>/dev/null || true
sleep 0.8

start=$(wc -l < "$L" 2>/dev/null || echo 0)
if [ "$pre" = "1" ]; then
  LD_PRELOAD=/usr/local/soco/libsoco.so nohup /usr/local/soco/soco -c /root/lab88/lab_a.conf > /root/lab88/A.out 2>&1 &
else
  nohup /usr/local/soco/soco -c /root/lab88/lab_a.conf > /root/lab88/A.out 2>&1 &
fi
sleep 8

seg=$(tail -n +$((start + 1)) "$L" 2>/dev/null)
echo "CASE n=$n preload=$pre"
echo "  add_user    : $(printf '%s' "$seg" | grep -ac 'add user' || true)"
echo "  user_num    : $(printf '%s' "$seg" | grep -a 'current user num' | tail -1 | sed 's/.*INFO[[:space:]]*//' || true)"
echo "  listen      : $(ss -lnt 2>/dev/null | grep -c ':19599 ' || true)"
echo "  pid         : $(pgrep -f 'soco -c /root/lab88/lab_a.conf' | head -1 || true)"
echo "  preload_env : $(tr '\0' '\n' < /proc/$(pgrep -f 'soco -c /root/lab88/lab_a.conf' | head -1)/environ 2>/dev/null | grep -c LD_PRELOAD || echo 0)"