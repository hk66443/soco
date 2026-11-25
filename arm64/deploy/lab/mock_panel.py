#!/usr/bin/env python3
"""mock é¢æ¿ï¼šåœ¨æœ¬åœ° 127.0.0.1:18080 å†’å…… xboard/UniProxyï¼Œä¸‹å‘ 100 ä¸ªç”¨æˆ· + ä¸¤å¥—ç«¯å£ã€‚

ç”¨é€”ï¼šéªŒè¯ socoï¼ˆcrack+é€‚é…å±‚ï¼‰ä¸Ž sogaï¼ˆå®˜æ–¹ç‰ˆï¼‰åœ¨ã€Œé¢æ¿æœ‰ 100 ä¸ªç”¨æˆ·ã€æ—¶çš„è¡Œä¸ºå·®å¼‚ã€‚
- node_id=1100 â†’ server_port 19599ï¼ˆç»™ crack å®žä¾‹ Aï¼‰
- node_id=1101 â†’ server_port 19699ï¼ˆç»™å®˜æ–¹å®žä¾‹ Bï¼‰
- å…¶ä½™æŽ¥å£ä¸€å¾‹ {"code":200,...} å…œåº•
è®¿é—®æ—¥å¿—å†™åˆ° /root/lab88/mock-access.log
"""
import base64
import json
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

from cryptography.hazmat.primitives import serialization as _ser
from cryptography.hazmat.primitives.asymmetric import x25519

N_USERS = 100


def _n_users():
    try:
        return max(1, min(500, int(open('/root/lab88/n_users').read().strip())))
    except Exception:
        return N_USERS
BASE = uuid.UUID('<REDACTED-PANEL-UUID>')
USERS = [
    {"id": i + 1,
     "uuid": str(uuid.UUID(int=(BASE.int + i) & ((1 << 128) - 1))),
     "speed_limit": None,
     "device_limit": None}
    for i in range(N_USERS)
]
USERS[0]["uuid"] = str(BASE)          # ç¬¬ 1 ä¸ª = ç”Ÿäº§èŠ‚ç‚¹é‚£ä¸ª uuidï¼Œä¾¿äºŽå¤ç”¨å®¢æˆ·ç«¯é…ç½®

_priv = x25519.X25519PrivateKey.from_private_bytes(bytes(range(1, 33)))
_pub_raw = _priv.public_key().public_bytes(_ser.Encoding.Raw, _ser.PublicFormat.Raw)
_prv_raw = _priv.private_bytes(_ser.Encoding.Raw, _ser.PrivateFormat.Raw, _ser.NoEncryption())
PBK = base64.urlsafe_b64encode(_pub_raw).decode().rstrip('=')
PRV = base64.urlsafe_b64encode(_prv_raw).decode().rstrip('=')
SID = 'a1b2c3d4e5f6'
PORTS = {'1100': 19599, '1101': 19699}


class H(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'

    def _send(self, obj, code=200):
        b = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def _do(self):
        u = urlparse(self.path)
        q = parse_qs(u.query)
        node = (q.get('node_id') or ['1100'])[0]
        act = (q.get('act') or [''])[0]
        p = u.path.lower()
        try:
            with open('/root/lab88/mock-access.log', 'a') as f:
                f.write('%s %s %s\n' % (time.strftime('%H:%M:%S'), self.command, self.path[:180]))
        except Exception:
            pass

        if 'config' in p or act == 'config':
            port = PORTS.get(node, 19599)
            self._send({
                "server_port": port,
                "network": "tcp",
                "tls": 2,
                "flow": "xtls-rprx-vision",
                "tls_settings": {
                    "allow_insecure": True,
                    "server_port": "443",
                    "server_name": "www.apple.com",
                    "public_key": PBK,
                    "private_key": PRV,
                    "short_id": SID,
                },
                "base_config": {"push_interval": 60, "pull_interval": 60},
            })
        elif 'user' in p or act == 'user':
            self._send({"users": USERS[:_n_users()]})
        elif 'alive' in p or act == 'alivelist' or act == 'alive':
            self._send({"users": []})
        else:
            self._send({"code": 200, "message": "ok", "data": {}})

    do_GET = _do
    do_POST = _do

    def log_message(self, *a):
        pass


if __name__ == '__main__':
    print(json.dumps({"users": len(USERS), "pbk": PBK, "sid": SID, "ports": PORTS}), flush=True)
    ThreadingHTTPServer(('127.0.0.1', 18080), H).serve_forever()