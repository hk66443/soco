#!/usr/bin/env python3
"""amd 上的 VLESS + REALITY mock 面板：验证 amd 的 soco 在 100 个 vless 用户下能否转发。

- 监听 127.0.0.1:18081
- node_id=1101 -> server_port 19590
- 固定 REALITY 密钥对（私钥 = bytes(1..32)），客户端用对应 public_key
- users 数量由 /root/labss/n_users 控制
"""
import base64
import json
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

# 私钥 = bytes(range(1,33))，对应公钥（客户端 pbk）
PRIVATE_KEY = base64.urlsafe_b64encode(bytes(range(1, 33))).decode().rstrip('=')
PUBLIC_KEY = 'B6N8vBQgk8i3VdwbEOhstCY3StFqqFPtC9_AsrhtHHw'
SHORT_ID = 'a1b2c3d4e5f6'
SERVER_NAME = 'www.apple.com'
BASE = uuid.UUID('<REDACTED-PANEL-UUID>')
USERS = [
    {"id": i + 1,
     "uuid": str(uuid.UUID(int=(BASE.int + i) & ((1 << 128) - 1))),
     "speed_limit": None,
     "device_limit": None}
    for i in range(500)
]
USERS[0]["uuid"] = str(BASE)
PORTS = {'1101': 19590}


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
        node = (q.get('node_id') or ['1101'])[0]
        act = (q.get('act') or [''])[0]
        p = u.path.lower()
        try:
            with open('/root/labss/mock-vless.log', 'a') as f:
                f.write('%s %s %s\n' % (time.strftime('%H:%M:%S'), self.command, self.path[:160]))
        except Exception:
            pass

        if 'config' in p or act == 'config':
            self._send({
                "server_port": PORTS.get(node, 19590),
                "network": "tcp",
                "tls": 2,
                "flow": "xtls-rprx-vision",
                "tls_settings": {
                    "allow_insecure": True,
                    "server_port": "443",
                    "server_name": SERVER_NAME,
                    "public_key": PUBLIC_KEY,
                    "private_key": PRIVATE_KEY,
                    "short_id": SHORT_ID,
                },
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
    print(json.dumps({"users": n_users(), "pbk": PUBLIC_KEY, "sid": SHORT_ID, "port": 19590}), flush=True)
    ThreadingHTTPServer(('127.0.0.1', 18081), H).serve_forever()