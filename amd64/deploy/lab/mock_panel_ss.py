#!/usr/bin/env python3
"""SS2022 mock é¢æ¿ï¼šå†’å…… xboard UniProxyï¼Œä¸‹å‘ N ä¸ªç”¨æˆ· + å›ºå®š server_keyã€‚

- node_id=1100 -> server_port 19589
- users æ•°é‡ç”± /root/labss/n_users æŽ§åˆ¶ï¼ˆé»˜è®¤ 100ï¼‰
- å­—æ®µåä¸Ž soga è¯»å–çš„ä¸€è‡´ï¼šserver_key / cipher
"""
import base64
import json
import os
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

SERVER_KEY = base64.b64encode(bytes(range(32))).decode()   # å›ºå®šï¼Œä¾¿äºŽå®¢æˆ·ç«¯å¤çŽ°
CIPHER = '2022-blake3-aes-256-gcm'
BASE = uuid.UUID('<REDACTED-PANEL-UUID>')
USERS = [
    {"id": i + 1,
     "uuid": str(uuid.UUID(int=(BASE.int ^ (i * 0x0123456789ABCDEF0123456789ABCDEF)) & ((1 << 128) - 1))),
     "speed_limit": None,
     "device_limit": None}
    for i in range(500)
]
USERS[0]["uuid"] = str(BASE)
PORTS = {'1100': 19589}


def n_users():
    try:
        return max(1, min(500, int(open('/root/labss/n_users').read().strip())))
    except Exception:
        return 100


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
            with open('/root/labss/mock-access.log', 'a') as f:
                f.write('%s %s %s\n' % (time.strftime('%H:%M:%S'), self.command, self.path[:160]))
        except Exception:
            pass

        if 'config' in p or act == 'config':
            self._send({
                "server_port": PORTS.get(node, 19589),
                "network": "tcp",
                "tls": 0,
                "server_key": SERVER_KEY,
                "cipher": CIPHER,
                "base_config": {"push_interval": 60, "pull_interval": 60},
            })
        elif 'user' in p or act == 'user':
            self._send({"users": USERS[:n_users()]})
        elif 'status' in p or act == 'status':
            self._send({"code": 200, "message": "ok", "data": {}})
        else:
            self._send({"code": 200, "message": "ok", "data": {}})

    do_GET = _do
    do_POST = _do

    def log_message(self, *a):
        pass


if __name__ == '__main__':
    print(json.dumps({"users": n_users(), "server_key": SERVER_KEY, "cipher": CIPHER, "port": 19589}), flush=True)
    ThreadingHTTPServer(('127.0.0.1', 18080), H).serve_forever()