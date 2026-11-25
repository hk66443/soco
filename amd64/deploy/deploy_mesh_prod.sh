#!/bin/bash
# Deploy soco-mesh on the production port 49989 (keeps soco.service stopped for instant rollback).
set -u
echo "=== date ==="; date -u
echo "=== install ==="
install -m 0755 /root/soco-verified-tests/soco_mesh_v4.py /usr/local/soco/soco-mesh.py
python3 -m py_compile /usr/local/soco/soco-mesh.py && echo "py OK"
cat > /etc/systemd/system/soco-mesh.service <<'UNIT'
[Unit]
Description=soco mesh - relay on 49989 + rotating backends (no restarts of live instances)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
Environment=MESH_LISTEN=49989
Environment=MESH_PORT_BASE=51000
Environment=MESH_PROXY_BASE=52000
Environment=MESH_ROTATE=480
Environment=MESH_GRACE=1800
Environment=MESH_CHECK=20
Environment=MESH_READY_TIMEOUT=45
ExecStart=/usr/bin/python3 /usr/local/soco/soco-mesh.py
Restart=always
RestartSec=5
LimitNOFILE=1048576

[Install]
WantedBy=multi-user.target
UNIT
systemctl daemon-reload
echo "=== stop watchdog + soco (rollback = start them again) ==="
systemctl stop soco-watchdog.service || true
systemctl stop soco.service || true
sleep 3
ss -lntup 'sport' '=' ':49989' | tail -2
echo "=== start mesh ==="
systemctl stop soco-mesh.service 2>/dev/null || true
systemctl start soco-mesh.service
sleep 45
systemctl show soco-mesh.service --property=MainPID,ActiveState,NRestarts,ExecMainStartTimestamp
echo "--- listeners on 49989 ---"; ss -lntup 'sport' '=' ':49989' | tail -3
echo "--- mesh log ---"; tail -8 /var/log/soco-mesh.log
echo "--- state ---"; cat /run/soco-mesh-state.json 2>/dev/null
echo "=== probe production ==="
cd /root/soco-verified-tests && python3 probe_v2.py --run-id "mesh-prod-$(date +%H%M%S)" 2>&1 | tail -1
exit 0