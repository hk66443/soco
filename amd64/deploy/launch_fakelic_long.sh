set -u
echo "=== date ==="; date -u
echo "=== 30-min confirmation run (licence hosts -> 127.0.0.1, fake TLS server rejects cert) ==="
cd /root/soco-verified-tests || exit 1
setsid nohup python3 interval_lab_v4.py --run-id lab-fakelic-long --port 19497 --mock-port 18497 \
  --pull 60 --push 60 --duration 1800 --probe-every 20 --fixtures /root/soco-verified-tests/lab-fixtures \
  --cand /root/soco-verified-tests/candidates/verified53-20261121-minimal-v1/soco \
  --so /root/soco-verified-tests/adapter-clean-build-20261121-v1/libsoco-amd64.so \
  > /root/soco-verified-tests/lab-fakelic-long.out 2>&1 &
echo launched
sleep 50
ss -lnt 'sport' '=' ':19497' | tail -2
grep -ac 'soga key' /root/soco-verified-tests/lab-fakelic-long/server.log 2>/dev/null || true
echo "=== production mesh status ==="
systemctl is-active soco-mesh.service; grep -ac 'relay_no_backend' /var/log/soco-mesh.log || true
grep -ac '"event": "rotate"' /var/log/soco-mesh.log || true
cat /run/soco-mesh-state.json; echo
exit 0
