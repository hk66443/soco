#!/bin/bash
# Hypothesis: the gate closes only when the 600 s licence check FAILS. If that check instead HANGS
# (licence hosts pointed at TEST-NET after startup, so TCP never completes), does service keep working?
set -u
echo "=== date ==="; date -u
HOSTS=/etc/hosts
cp -a "$HOSTS" /root/soco-verified-tests/hosts.before-sni-test
echo "=== start isolated instance (port 19493, mock 18493) ==="
cd /root/soco-verified-tests || exit 1
setsid nohup python3 interval_lab_v4.py --run-id lab-hosts-hang-1 --port 19493 --mock-port 18493 \
  --pull 60 --push 60 --duration 820 --probe-every 15 --fixtures /root/soco-verified-tests/lab-fixtures \
  --cand /root/soco-verified-tests/candidates/verified53-20261121-minimal-v1/soco \
  --so /root/soco-verified-tests/adapter-clean-build-20261121-v1/libsoco-amd64.so \
  > /root/soco-verified-tests/lab-hosts-hang-1.out 2>&1 &
echo "wait 30 s so the startup licence check runs normally"
sleep 30
ss -lnt 'sport' '=' ':19493' | tail -2
grep -ac 'soga key' /root/soco-verified-tests/lab-hosts-hang-1/server.log 2>/dev/null || true
echo "=== point licence hosts at TEST-NET-2 (black hole) AFTER startup ==="
cat >> "$HOSTS" <<'EOF'
198.51.100.1 sksjd.vaxilu.com
198.51.100.1 agdfgkdfg.singledance.xyz
198.51.100.1 boiudihsdfk.singledance.xyz
198.51.100.1 sxp7hu5t.cilema.xyz
EOF
tail -5 "$HOSTS"
echo "=== panel path must stay alive ==="
curl -s -o /dev/null -w "panel_http=%{http_code}\n" --max-time 10 https://<REDACTED>/ || true
echo "=== watch early probes ==="
sleep 75
python3 - <<'PY'
import json
from pathlib import Path
p=Path('/root/soco-verified-tests/lab-hosts-hang-1/result.partial.json')
if p.exists():
    d=json.loads(p.read_text());pr=d['probes']
    print('probes',len(pr),'fails',sum(1 for x in pr if not x['ok']),'last',pr[-1])
else:print('no partial')
PY
echo "=== hosts restored by the caller after the run; this script leaves the rule in place ==="
exit 0