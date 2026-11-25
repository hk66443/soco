#!/bin/bash
set -u
LOG=$(cat /root/soco-verified-tests/probe497-amd.current)
echo "== now $(date -Is)"
PID=$(pgrep -f 'probe_many.py 497' | head -1 || true)
if [ -n "${PID:-}" ]; then echo "RUNNING pid=$PID etime=$(ps -o etime= -p "$PID" | tr -d ' ')"; else echo "NOT RUNNING (finished or died)"; fi
OK=$(grep -c ' OK$' "$LOG" || true); FAIL=$(grep -c 'FAIL (idx' "$LOG" || true)
echo "done_lines=$((OK+FAIL)) ok=$OK fail=$FAIL"
echo "== tail"; tail -3 "$LOG"
echo "== mem"; free -m | head -2 | tail -1
echo "== soco"; systemctl show soco -p MainPID -p NRestarts -p ActiveState --value | paste -sd'|'
echo "== auth_failed_15min=$(journalctl -u soco --since '-15min' -o cat | grep -c 'auth failed' || true)"
echo "== users $(journalctl -u soco -n 300 -o cat | grep 'current user num' | tail -1)"