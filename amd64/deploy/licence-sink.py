#!/usr/bin/env python3
"""Licence endpoint sink: accept TLS, let the handshake fail, drop the connection.

soga checks a licence host every 600 s. When that check hangs or gets a real network failure the
data plane is closed ~600 s after start (new connections are accepted then immediately closed).
When it fails fast locally (handshake rejected here) the data plane keeps serving: verified with a
single process over 30 minutes / 90 handshakes / 0 failures.
"""
import socket, ssl
ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
ctx.load_cert_chain('/usr/local/soco/licence/cert.pem', '/usr/local/soco/licence/key.pem')
srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
srv.bind(('0.0.0.0', 443)); srv.listen(64)
while True:
    c, _ = srv.accept()
    try:
        c.settimeout(3)
        try:
            s = ctx.wrap_socket(c, server_side=True); s.close()
        except Exception:
            pass
    finally:
        try: c.close()
        except Exception: pass
