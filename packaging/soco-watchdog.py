#!/usr/bin/env python3
"""soco watchdog（ARM / VLESS+REALITY 版）：真实握手探活 + 停摆自动重启。

和 AMD 的 SS2022 版同一思路：
  - 每 PROBE_EVERY 秒，用 sing-box 起一个 socks 入口 → VLESS/REALITY 打到本机 49999，
    请求本地 marker（127.0.0.1:18089），必须回 "M" 才算健康（端口在听不算）；
  - 连续 FAILS_TO_RESTART 次失败 → systemctl restart soco；
  - 面板拉不到用户/配置 → 视为 unknown，不重启；
  - 进程启动 30 秒内不判。
参数从 /etc/soga/soga.conf 读，REALITY 参数实时从面板拉（避免手上参数过期）。
"""
import base64
import json
import os
import re
import socket
import subprocess
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

CONF_CANDIDATES = [Path('/etc/soga/soga.conf'), Path('/etc/soco/soco.conf')]
SBOX = Path('/usr/local/soco/sing-box-probe')
CFGPATH = Path('/usr/local/soco/watchdog-client.json')
LOG = Path('/var/log/soco-watchdog.log')
MARKER_PORT = 18089
SOCKS_PORT = 11009
PROBE_EVERY = int(os.environ.get('PROBE_EVERY', '30'))
FAILS_TO_RESTART = int(os.environ.get('FAILS_TO_RESTART', '3'))
PREEMPT = float(os.environ.get('PREEMPT_SECONDS', '0'))


def log(rec):
    rec['utc'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
    try:
        with LOG.open('a') as f:
            f.write(json.dumps(rec, ensure_ascii=False) + '\n')
    except Exception:
        pass


class Marker(BaseHTTPRequestHandler):
    def do_GET(self):
        body = b'M'
        self.send_response(200)
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


def read_conf():
    for p in CONF_CANDIDATES:
        if p.is_file():
            text = p.read_text(errors='replace')
            kv = {}
            for line in text.splitlines():
                line = line.strip()
                if not line or line.startswith('#') or '=' not in line:
                    continue
                k, v = line.split('=', 1)
                kv[k.strip()] = v.strip()
            return p, kv
    return None, {}


def panel_fetch(kv, what):
    base = (kv.get('webapi_url') or '').rstrip('/')
    key = kv.get('webapi_key') or ''
    node = kv.get('node_id') or ''
    stype = kv.get('server_type') or 'vless'
    if not (base and key and node):
        raise RuntimeError('webapi_url/webapi_key/node_id missing')
    node_type = {'ss': 'shadowsocks', 'v2ray': 'vmess'}.get(stype, stype)
    url = '%s/api/v1/server/UniProxy/%s?node_id=%s&node_type=%s&token=%s' % (
        base, what, node, node_type, key)
    out = subprocess.run(['curl', '-sS', '--max-time', '15', url],
                         capture_output=True, text=True, timeout=25)
    if out.returncode != 0:
        raise RuntimeError('panel curl rc=%d %s' % (out.returncode, out.stderr.strip()[:100]))
    return json.loads(out.stdout)


def service_state():
    try:
        o = subprocess.run(['systemctl', 'show', 'soco.service',
                            '--property=MainPID,ActiveState,NRestarts'],
                           capture_output=True, text=True).stdout
        return dict(l.split('=', 1) for l in o.splitlines() if '=' in l)
    except Exception:
        return {}


def soco_uptime():
    try:
        mono = int(subprocess.run(
            ['systemctl', 'show', 'soco.service', '--property=ActiveEnterTimestampMonotonic', '--value'],
            capture_output=True, text=True).stdout.strip() or 0)
        if mono <= 0:
            return None
        now = int(float(Path('/proc/uptime').read_text().split()[0]) * 1_000_000)
        return max(0.0, (now - mono) / 1_000_000)
    except Exception:
        return None


def restart(reason, extra=None):
    rec = {'event': 'restart', 'reason': reason}
    if extra:
        rec.update(extra)
    log(rec)
    subprocess.run(['systemctl', 'restart', 'soco.service'], capture_output=True)
    time.sleep(25)


def build_client(cfg):
    tls = cfg.get('tls_settings') or {}
    return {
        'log': {'level': 'error'},
        'inbounds': [{'type': 'socks', 'tag': 'in', 'listen': '127.0.0.1', 'listen_port': SOCKS_PORT}],
        'outbounds': [{
            'type': 'vless', 'tag': 'vless', 'server': '127.0.0.1',
            'server_port': int(cfg['server_port']), 'uuid': cfg['_uuid'],
            'flow': cfg.get('flow') or 'xtls-rprx-vision',
            'tls': {
                'enabled': True,
                'server_name': tls.get('server_name') or 'www.apple.com',
                'utls': {'enabled': True, 'fingerprint': 'chrome'},
                'reality': {
                    'enabled': True,
                    'public_key': tls.get('public_key'),
                    'short_id': tls.get('short_id') or '',
                },
            },
        }],
        'route': {'final': 'vless'},
    }


def main():
    srv = ThreadingHTTPServer(('127.0.0.1', MARKER_PORT), Marker)
    srv.daemon_threads = True
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    conf_path, kv = read_conf()
    log({'event': 'watchdog_start', 'conf': str(conf_path), 'probe_every': PROBE_EVERY,
         'fails_to_restart': FAILS_TO_RESTART, 'preempt_seconds': PREEMPT})
    client = None
    client_key = None
    fails = 0
    restarts = 0
    last_preempt = 0.0
    logged_ok = False
    while True:
        try:
            up = soco_uptime()
            if up is not None and PREEMPT > 0 and up >= PREEMPT and (time.time() - last_preempt) > 60:
                last_preempt = time.time()
                restarts += 1
                restart('preemptive_before_key_check', {'soco_uptime_s': round(up, 1)})
            if up is not None and up < 30:
                time.sleep(PROBE_EVERY)
                continue

            conf_path, kv = read_conf()
            node = panel_fetch(kv, 'config')
            users = panel_fetch(kv, 'user').get('users') or []
            if not users:
                log({'event': 'panel_no_users', 'action': 'skip'})
                time.sleep(PROBE_EVERY)
                continue
            cfg = dict(node)
            cfg['_uuid'] = users[0]['uuid']
            key = (cfg['server_port'], cfg['_uuid'], (cfg.get('tls_settings') or {}).get('short_id'))

            if client is None or client.poll() is not None or client_key != key:
                if client is not None and client.poll() is None:
                    client.terminate()
                    try:
                        client.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        client.kill()
                CFGPATH.write_text(json.dumps(build_client(cfg)), encoding='utf-8')
                CFGPATH.chmod(0o600)
                client = subprocess.Popen([str(SBOX), 'run', '-c', str(CFGPATH)],
                                          stdin=subprocess.DEVNULL,
                                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                client_key = key
                time.sleep(3)

            c = subprocess.run(['curl', '-sS', '-x', 'socks5h://127.0.0.1:%d' % SOCKS_PORT,
                                '--max-time', '10',
                                'http://127.0.0.1:%d/' % MARKER_PORT],
                               capture_output=True, text=True, timeout=20)
            ok = c.returncode == 0 and c.stdout.strip() == 'M'
            if ok:
                if fails:
                    log({'event': 'recovered', 'fails_before': fails})
                elif not logged_ok:
                    log({'event': 'probe_ok', 'server_port': cfg['server_port'],
                         'uuid': str(cfg['_uuid'])[:8] + '…'})
                    logged_ok = True
                fails = 0
            else:
                fails += 1
                log({'event': 'probe_failed', 'fails': fails, 'curl_exit': c.returncode,
                     'err': c.stderr.strip()[:120], 'service': service_state(),
                     'soco_uptime_s': round(up or -1, 1)})
                if fails >= FAILS_TO_RESTART:
                    restarts += 1
                    fails = 0
                    restart('vless_probe_failed', {'restarts': restarts})
                    c2 = subprocess.run(['curl', '-sS', '-x', 'socks5h://127.0.0.1:%d' % SOCKS_PORT,
                                         '--max-time', '10',
                                         'http://127.0.0.1:%d/' % MARKER_PORT],
                                        capture_output=True, text=True, timeout=20)
                    log({'event': 'after_restart',
                         'ok': c2.returncode == 0 and c2.stdout.strip() == 'M',
                         'curl_exit': c2.returncode, 'restarts': restarts,
                         'service': service_state()})
        except Exception as e:
            log({'event': 'probe_error', 'type': type(e).__name__, 'message': str(e)[:200],
                 'action': 'skip'})
        time.sleep(PROBE_EVERY)


if __name__ == '__main__':
    main()