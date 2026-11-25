#!/usr/bin/env python3
"""Concurrent VLESS probe driver: fire N parallel TLS-less VLESS handshakes at the lab
instance and report the pass rate.  Reuses the same wire format as /tmp/probe_vless.py.

usage: probe_conc.py <port> <uuid> <concurrency> [target_ip] [target_port]
"""
import socket, struct, sys, time, uuid
from concurrent.futures import ThreadPoolExecutor

port = int(sys.argv[1])
uid = uuid.UUID(sys.argv[2])
conc = int(sys.argv[3])
tgt = sys.argv[4] if len(sys.argv) > 4 else '127.0.0.1'
tport = int(sys.argv[5]) if len(sys.argv) > 5 else 22
UUID_B = uid.bytes


def one(_i):
    t0 = time.time()
    s = socket.socket()
    s.settimeout(10.0)
    try:
        s.connect(('127.0.0.1', port))
        req = (bytes([0]) + UUID_B + bytes([0]) + bytes([1])
               + struct.pack('>H', tport) + bytes([1]) + socket.inet_aton(tgt))
        s.sendall(req)
        data = s.recv(512)
    except Exception as e:
        return ('FAIL', type(e).__name__, time.time() - t0)
    finally:
        try: s.close()
        except Exception: pass
    if not data:
        return ('FAIL', 'EMPTY_CLOSE', time.time() - t0)
    addon = data[1] if len(data) >= 2 else 0
    payload = data[2 + addon:]
    return ('OK' if payload else 'FAIL', 'HEADER_ONLY' if not payload else '', time.time() - t0)


t0 = time.time()
with ThreadPoolExecutor(max_workers=conc) as ex:
    res = list(ex.map(one, range(conc)))
ok = [r for r in res if r[0] == 'OK']
fail = [r for r in res if r[0] != 'OK']
lat = sorted(r[2] for r in ok)
print('concurrency=%d OK=%d FAIL=%d wall=%.1fs' % (conc, len(ok), len(fail), time.time() - t0))
if lat:
    print('latency_ms  min=%.0f p50=%.0f p95=%.0f max=%.0f' % (
        lat[0] * 1000, lat[len(lat)//2] * 1000, lat[min(len(lat)-1, int(len(lat)*0.95))] * 1000, lat[-1] * 1000))
if fail:
    from collections import Counter
    print('failures:', Counter(r[1] for r in fail))
sys.exit(0 if not fail else 1)
