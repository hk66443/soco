#!/bin/bash
# Experiment: point the licence host at a local TLS server (self-signed) and see whether soco
# (a) accepts the certificate and sends its request, or (b) rejects it and fails the check.
set -u
echo "=== date ==="; date -u
echo "=== restore /etc/hosts (remove TEST-NET blackhole) ==="
cp -a /root/soco-verified-tests/hosts.before-sni-test /etc/hosts
grep -c 'vaxilu' /etc/hosts || true
echo "=== create self-signed cert for the licence host ==="
mkdir -p /root/soco-verified-tests/fakelic && cd /root/soco-verified-tests/fakelic
openssl req -x509 -newkey rsa:2048 -nodes -keyout key.pem -out cert.pem -days 3 \
  -subj "/CN=sksjd.vaxilu.com" -addext "subjectAltName=DNS:sksjd.vaxilu.com" 2>/dev/null && echo "cert OK"
cat > server.py <<'PY'
import socket, ssl, sys, json, time
ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
ctx.load_cert_chain('/root/soco-verified-tests/fakelic/cert.pem', '/root/soco-verified-tests/fakelic/key.pem')
srv = socket.socket(); srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
srv.bind(('0.0.0.0', 443)); srv.listen(16)
log = open('/root/soco-verified-tests/fakelic/hits.log', 'a', buffering=1)
log.write('listening %s\n' % time.strftime('%H:%M:%S'))
while True:
    c, addr = srv.accept()
    try:
        s = ctx.wrap_socket(c, server_side=True)
        sni = s.server_hostname if hasattr(s, 'server_hostname') else None
        data = b''
        s.settimeout(5)
        try:
            data = s.recv(8192)
        except Exception as e:
            log.write('recv_err %s\n' % type(e).__name__)
        log.write('HIT %s sni=%s bytes=%d\n%s\n' % (addr, sni, len(data), data[:800].decode('latin1')))
        body = b'{"code":0,"data":{},"success":true,"message":"ok"}'
        s.sendall(b'HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: %d\r\nConnection: close\r\n\r\n' % len(body) + body)
        s.close()
    except Exception as e:
        log.write('handshake_err %s: %s\n' % (type(e).__name__, str(e)[:200]))
        try: c.close()
        except Exception: pass
PY
python3 -m py_compile server.py && echo "server py OK"
echo "=== start fake licence server on :443 ==="
setsid nohup python3 server.py > /root/soco-verified-tests/fakelic/server.out 2>&1 &
sleep 2
ss -lnt 'sport' '=' ':443' | tail -2
echo "=== point licence hosts at 127.0.0.1 AFTER a normal startup check ==="
cd /root/soco-verified-tests || exit 1
setsid nohup python3 interval_lab_v4.py --run-id lab-fakelic-1 --port 19495 --mock-port 18495 \
  --pull 60 --push 60 --duration 820 --probe-every 15 --fixtures /root/soco-verified-tests/lab-fixtures \
  --cand /root/soco-verified-tests/candidates/verified53-20261121-minimal-v1/soco \
  --so /root/soco-verified-tests/adapter-clean-build-20261121-v1/libsoco-amd64.so \
  > /root/soco-verified-tests/lab-fakelic-1.out 2>&1 &
sleep 30
cat >> /etc/hosts <<'EOF'
127.0.0.1 sksjd.vaxilu.com
127.0.0.1 agdfgkdfg.singledance.xyz
127.0.0.1 boiudihsdfk.singledance.xyz
127.0.0.1 sxp7hu5t.cilema.xyz
EOF
tail -4 /etc/hosts
echo "=== wait for the t=600 licence check to hit our fake server ==="
sleep 60
echo "--- hits.log ---"; tail -30 /root/soco-verified-tests/fakelic/hits.log 2>/dev/null || echo "(no hits yet)"
echo "--- probes ---"
python3 - <<'PY'
import json
from pathlib import Path
p=Path('/root/soco-verified-tests/lab-fakelic-1/result.partial.json')
if p.exists():
    d=json.loads(p.read_text());pr=d['probes']
    print('probes',len(pr),'fails',sum(1 for x in pr if not x['ok']),'last',pr[-1])
else:print('no partial')
PY
exit 0