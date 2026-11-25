set -u
echo "=== date ==="; date -u
echo "=== production single-process ==="
systemctl show soco.service --property=MainPID,ActiveState,NRestarts,ExecMainStartTimestamp
echo -n "uptime_s="; ps -o etimes= -p $(systemctl show soco.service --property=MainPID --value) 2>/dev/null || echo "?"
ss -lntup 'sport' '=' ':49989' | tail -2
echo -n "key errors since start: "; journalctl -b _PID=$(systemctl show soco.service --property=MainPID --value) --no-pager -o cat 2>/dev/null | grep -ac 'soga key' || true
echo "=== soak probe (45 min, every 20 s) ==="
python3 - <<'PY'
import json
from pathlib import Path
base=Path('/root/soco-verified-tests/final-soak-1')
for f in ('result.json','result.partial.json'):
    p=base/f
    if p.exists():
        d=json.loads(p.read_text());pr=d['probes']
        fails=[x for x in pr if not x['ok']]
        print(f,'probes',len(pr),'fails',len(fails),'first_failure',d.get('first_failure'))
        ts=[x['t'] for x in pr]
        print('span_s=',(max(ts)-min(ts)) if ts else 0,'last',pr[-1] if pr else None)
        print('after 540:',[(x['t'],x['ok']) for x in pr if x['t']>540][:12])
        break
PY
echo "=== sink + hosts ==="
systemctl is-active soco-licence-sink.service; grep -cE 'vaxilu|singledance|cilema' /etc/hosts
echo "=== watchdog ==="; systemctl is-active soco-watchdog.service; tail -2 /var/log/soco-watchdog.log
exit 0
