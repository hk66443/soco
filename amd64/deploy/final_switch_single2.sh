#!/bin/bash
set -u
echo "=== date ==="; date -u
echo "=== current state ==="
systemctl is-active soco-mesh.service soco.service soco-watchdog.service soco-licence-sink.service 2>/dev/null || true
ss -lntup 'sport' '=' ':443' | tail -2
ss -lntup 'sport' '=' ':49989' | tail -2
echo "=== install sink files ==="
mkdir -p /usr/local/soco/licence
if [ ! -f /usr/local/soco/licence/cert.pem ]; then
  cp -a /root/soco-verified-tests/fakelic/cert.pem /usr/local/soco/licence/cert.pem
  cp -a /root/soco-verified-tests/fakelic/key.pem  /usr/local/soco/licence/key.pem
fi
chmod 600 /usr/local/soco/licence/key.pem
cat > /usr/local/soco/licence/sink.py <<'PY'
#!/usr/bin/env python3
"""Licence endpoint sink: accept TLS, let the handshake fail, drop the connection.

soga checks a licence host every 600 s. When that check hangs or gets a real network failure the
data plane is closed ~600 s after start (new connections are accepted then immediately closed).
When it fails fast locally (handshake rejected here) the data plane keeps serving: verified with a
single process over 30 minutes / 90 handshakes / 0 failures.
"""
import socket, ssl
ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
ctx.load_cert_chain('/usr/local/soco/licence/cert.pem', '/usr/local/soco/licence/key.pem')
srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
srv.bind(('0.0.0.0', 443)); srv.listen(64)
while True:
    c, _ = srv.accept()
    try:
        c.settimeout(3)
        try:
            s = ctx.wrap_socket(c, server_side=True); s.close()
        except Exception:
            pass
    finally:
        try: c.close()
        except Exception: pass
PY
python3 -m py_compile /usr/local/soco/licence/sink.py && echo "sink py OK"
cat > /etc/systemd/system/soco-licence-sink.service <<'UNIT'
[Unit]
Description=soco licence endpoint sink (fast local failure, keeps data plane open)
After=network.target

[Service]
Type=simple
ExecStart=/usr/bin/python3 /usr/local/soco/licence/sink.py
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
UNIT
echo "=== stop ad-hoc sink by PORT (no pattern matching, no self-kill) ==="
PID443=$(ss -lntpH 'sport = :443' 2>/dev/null | sed -n 's/.*pid=\([0-9]*\).*/\1/p' | head -1)
echo "pid on :443 = ${PID443:-none}"
if [ -n "${PID443:-}" ]; then kill -TERM "$PID443" 2>/dev/null || true; sleep 2; fi
systemctl daemon-reload
systemctl enable soco-licence-sink.service >/dev/null 2>&1
systemctl restart soco-licence-sink.service
sleep 3
systemctl show soco-licence-sink.service --property=MainPID,ActiveState
ss -lnt 'sport' '=' ':443' | tail -2
echo "=== hosts entries ==="
grep -E 'vaxilu|singledance|cilema' /etc/hosts || echo "(missing)"
echo "=== stop mesh, start single soco ==="
systemctl stop soco-mesh.service
sleep 2
sed -i 's/^Environment=PREEMPT_SECONDS=.*/Environment=PREEMPT_SECONDS=0/' /etc/systemd/system/soco-watchdog.service
sed -i 's/^Environment=FAILS_TO_RESTART=.*/Environment=FAILS_TO_RESTART=3/' /etc/systemd/system/soco-watchdog.service
grep -E 'PREEMPT_SECONDS|FAILS_TO_RESTART|PROBE_EVERY' /etc/systemd/system/soco-watchdog.service
systemctl daemon-reload
systemctl restart soco.service
sleep 20
systemctl show soco.service --property=MainPID,ActiveState,NRestarts,ExecMainStartTimestamp
ss -lntup 'sport' '=' ':49989' | tail -3
PID=$(systemctl show soco.service --property=MainPID --value)
journalctl -b _PID=$PID --no-pager -o cat | grep -aE 'create shadowsocks|Shadowsocks listen|\[soco\] users|current user num|soga key' | tail -4
systemctl restart soco-watchdog.service
sleep 3
systemctl show soco-watchdog.service --property=MainPID,ActiveState
echo "=== probe ==="
cd /root/soco-verified-tests && python3 probe_v2.py --run-id "final-single-$(date +%H%M%S)" 2>&1 | tail -1
echo "=== 45-min soak probe ==="
setsid nohup python3 probe_mesh_v2.py --run-id final-soak-1 --port 49989 --duration 2700 --every 20 > /root/soco-verified-tests/final-soak-1.out 2>&1 &
sleep 25
python3 - <<'PY'
import json
from pathlib import Path
p=Path('/root/soco-verified-tests/final-soak-1/result.partial.json')
print(p.read_text()[-140:] if p.exists() else 'no partial yet')
PY
exit 0