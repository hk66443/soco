#!/usr/bin/env python3
"""Licence endpoint sink: accept TLS, let the handshake fail, drop the connection.

soga checks a licence host every 600 s. When that check hangs or gets a real network failure the
data plane is closed ~600 s after start (new connections are accepted then immediately closed).
When it fails fast locally (handshake rejected here) the data plane keeps serving: verified with a
single process over 30 minutes / 90 handshakes / 0 failures.

监听地址由 --listen 决定（默认 0.0.0.0:38443）。**不要写死 443**：443 要留给网站/证书用，
sink 只负责被 nft 从 127.0.0.1:443 dnat 过来，自己监听 38443 即可。
"""
import argparse
import os
import socket
import ssl

HERE = os.path.dirname(os.path.abspath(__file__))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--listen', default='0.0.0.0:38443')
    ap.add_argument('--cert', default=os.path.join(HERE, 'cert.pem'))
    ap.add_argument('--key', default=os.path.join(HERE, 'key.pem'))
    a = ap.parse_args()
    host, _, port = a.listen.rpartition(':')
    port = int(port or 38443)
    host = host or '0.0.0.0'

    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(a.cert, a.key)
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((host, port))
    srv.listen(64)
    print('licence sink listening on %s:%d' % (host, port), flush=True)
    while True:
        c, _ = srv.accept()
        try:
            c.settimeout(3)
            try:
                s = ctx.wrap_socket(c, server_side=True)
                s.close()
            except Exception:
                pass
        finally:
            try:
                c.close()
            except Exception:
                pass


if __name__ == '__main__':
    main()