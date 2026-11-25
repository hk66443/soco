set -u
echo "=== date ==="; date -u
echo "=== production probe (49989, 16 min) ==="
python3 - <<'PY'
import json
from pathlib import Path
base=Path('/root/soco-verified-tests/mesh-prod-probe-1')
for f in ('result.json','result.partial.json'):
    p=base/f
    if p.exists():
        d=json.loads(p.read_text());pr=d['probes']
        fails=[x for x in pr if not x['ok']]
        print(f,'probes',len(pr),'fails',len(fails),'first_failure',d.get('first_failure'))
        print('fail times',[x['t'] for x in fails][:10])
        print('after 480s:',[(x['t'],x['ok']) for x in pr if x['t']>480][:20])
        break
PY
echo "=== mesh rotations (production) ==="
grep -aE 'rotate|active_switch|backend_stop|no_backend' /var/log/soco-mesh.log | tail -12
echo "=== current state ==="; cat /run/soco-mesh-state.json; echo
echo "=== services ==="; systemctl is-active soco-mesh.service soco.service soco-watchdog.service
echo "=== listeners ==="; ss -lntup | grep -E ':49989|:510|:520' | head -6
exit 0
