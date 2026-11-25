#!/bin/bash
set -u
LOG=$(cat /root/soco-verified-tests/probe497-amd.current)
echo "== log=$LOG"
BIRTH=$(stat -c %w "$LOG" 2>/dev/null | awk '{print $1" "$2}')
if [ -z "${BIRTH:-}" ] || [ "$BIRTH" = "-" ]; then BIRTH="-40 min ago"; fi
echo "== window from $BIRTH"
echo "== RESULT LINES"
sed -n '/TOTAL/p' "$LOG"
grep 'FAIL (idx' "$LOG" | head -40 || true
echo "== done_lines=$(grep -c ' OK$' "$LOG")$(printf ' ok_fail=%s\n' "$(grep -c 'FAIL (idx' "$LOG" || true)")"
echo "== wall"
stat -c 'log_mtime=%y size=%s' "$LOG"
echo "== server side window"
journalctl -u soco --since "$BIRTH" -o cat > /tmp/win497.log 2>/dev/null || true
echo "access_address_lines=$(grep -c 'access address' /tmp/win497.log || true)"
echo "distinct_auth_users=$(grep -oE 'user [0-9]+ access address' /tmp/win497.log | awk '{print $2}' | sort -u | wc -l)"
echo "start_relay_lines=$(grep -c 'start tcp relay' /tmp/win497.log || true)"
echo "distinct_relay_users=$(grep -oE 'start tcp relay: session id: [0-9]+, user: [0-9]+' /tmp/win497.log | awk '{print $NF}' | sort -u | wc -l)"
echo "auth_failed=$(grep -c 'auth failed' /tmp/win497.log || true)"
echo "soga_key_err=$(grep -c 'soga key' /tmp/win497.log || true)"
echo "panic=$(grep -ic 'panic' /tmp/win497.log || true)"
echo "user_num_lines=$(grep -c 'current user num' /tmp/win497.log || true)"
echo "user_num_values=$(grep -oE 'current user num: [0-9]+' /tmp/win497.log | awk '{print $NF}' | sort -u | paste -sd,) "
echo "== final service state"
systemctl show soco -p MainPID -p NRestarts -p ActiveState -p ExecMainStartTimestamp --value | paste -sd'|'
ps -o etime=,rss=,pcpu= -p "$(systemctl show soco -p MainPID --value)" 2>/dev/null || true
echo "== mem/disk"; free -m | head -2 | tail -1; df -h / | tail -1
echo "== probe clients left"; pgrep -af 'probe-multi' || echo none