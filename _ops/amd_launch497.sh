#!/bin/bash
set -u
TS=$(date +%Y%m%d-%H%M%S)
LOG=/root/soco-verified-tests/probe497-amd-$TS.log
mkdir -p /tmp/probe-multi
cd /root/soco-pkg || exit 1
echo "== pre-run state"
systemctl show soco -p MainPID -p NRestarts -p ActiveState --value | paste -sd'|'
journalctl -u soco -n 200 -o cat | grep 'current user num' | tail -1
free -m | head -2 | tail -1
echo "== launching full 497 run (detached)"
setsid bash -c "python3 -u /root/soco-pkg/probe_many.py 497 > $LOG 2>&1" < /dev/null > /dev/null 2>&1 &
sleep 4
echo "$LOG" > /root/soco-verified-tests/probe497-amd.current
echo "LOG=$LOG"
echo "== pids"
pgrep -af 'probe_many.py 497' || echo "no pid"
echo "== first lines"
head -5 "$LOG" 2>/dev/null || true
echo "== start ts"
date -Is