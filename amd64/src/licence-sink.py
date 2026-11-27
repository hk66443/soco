#!/usr/bin/env python3
"""Licence endpoint sink: accept TLS, let the handshake fail, drop the connection.

soga checks a licence host every 600 s. When that check hangs or gets a real network failure the
data plane is closed ~600 s after start (new connections are accepted then immediately closed).
When it fails fast locally (handshake rejected here) the data plane keeps serving: verified with a
single process over 30 minutes / 90 handshakes / 0 failures.

监听地址由 --listen 决定（默认 0.0.0.0:38443）。**不要写死 443**：443 要留给网站/证书用，
sink 只负责被 nft 从 127.0.0.1:443 dnat 过来，自己监听 38443 即可。

以前证书缺失 / 端口被占用时直接抛 Python traceback（systemd 日志里只有 FileNotFoundError），
这里改成一句人话 + 明确的退出码，systemd 侧照旧 Restart=always 重试。
"""
import argparse
import errno
import os
import socket
import ssl
import sys

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
    try:
        ctx.load_cert_chain(a.cert, a.key)
    except (OSError, ssl.SSLError) as e:
        print('licence sink: 证书加载失败 —— cert=%s key=%s（%s）' % (a.cert, a.key, e),
              file=sys.stderr, flush=True)
        print('  生成一对自签证书：openssl req -x509 -newkey rsa:2048 -nodes -days 3 '
              '-keyout %s -out %s -subj "/CN=sksjd.vaxilu.com" '
              '-addext "subjectAltName=DNS:sksjd.vaxilu.com"' % (a.key, a.cert),
              file=sys.stderr, flush=True)
        return 2

    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        srv.bind((host, port))
    except OSError as e:
        print('licence sink: 绑定 %s:%d 失败（端口被别的进程占了？）：%s（errno=%s）'
              % (host, port, e, e.errno), file=sys.stderr, flush=True)
        print('  看谁占了端口：ss -lntp | grep %d' % port, file=sys.stderr, flush=True)
        return 3
    srv.listen(64)
    print('licence sink listening on %s:%d' % (host, port), flush=True)

    while True:
        try:
            c, _ = srv.accept()
        except OSError as e:
            if e.errno == errno.EINTR:
                continue
            print('licence sink: accept 失败：%s（errno=%s）' % (e, e.errno),
                  file=sys.stderr, flush=True)
            return 4
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
    sys.exit(main())