#!/bin/bash
# EMERGENCY restore: put the verified c463 build back and re-enable pre-emptive restarts
set -u
INST=/usr/local/soco/soco
GOOD=/root/soco-verified-tests/candidates/verified53-20261121-minimal-v1/soco
GOOD_SHA=c463791ac4bf9ba82f28b8e87b148976f13397e1407ddab04d366579e4c80fed
echo "=== date ==="; date -u
echo "=== restore verified build ==="
install -m 0755 "$GOOD" "$INST"
sha256sum "$INST"
[ "$(sha256sum "$INST" | cut -d' ' -f1)" = "$GOOD_SHA" ] || { echo "RESTORE HASH MISMATCH"; exit 3; }
echo "=== re-enable pre-emptive restart ==="
sed -i 's/^Environment=PREEMPT_SECONDS=.*/Environment=PREEMPT_SECONDS=540/' /etc/systemd/system/soco-watchdog.service
systemctl daemon-reload
systemctl restart soco-watchdog.service
echo "=== restart soco ==="
systemctl restart soco.service
sleep 20
systemctl show soco.service --property=MainPID,ActiveState,NRestarts,ExecMainStartTimestamp
ss -lntup 'sport' '=' ':49989'
PID=$(systemctl show soco.service --property=MainPID --value)
journalctl -b _PID=$PID --no-pager -o cat | grep -aE 'create shadowsocks|Shadowsocks listen|\[soco\] users|current user num' | tail -4
echo "=== probe ==="
cd /root/soco-verified-tests && python3 probe_v2.py --run-id "restore-$(date +%H%M%S)" 2>&1 | tail -1
exit 0