#!/usr/bin/env python3
"""soco watchdog（统一版）：**协议自适应**的真实握手探活 + 停摆自动重启。

背景：AMD 跑 SS2022、ARM 跑 VLESS+REALITY，旧版把「VLESS 专用」脚本装到 AMD，
      REALITY 参数对 ss 节点无意义 → 探针永远失败 → 每 ~2 min 把健康的 soco 重启一次。

做法（两架构同一份，靠 soga.conf 的 server_type 自适应）：
  - 每 PROBE_EVERY 秒，从面板拉 config + user（node_type 按 server_type 自动映射）；
  - 用 sing-box 在本机 127.0.0.1:<空闲端口，默认 11009> 起 socks 入口，经本机节点打到 marker
    http://127.0.0.1:18089/，必须回 "M" 才算健康（端口在听不算）；
  - 连续 FAILS_TO_RESTART 次失败 → systemctl restart soco；
  - 面板拉不到用户 / 网络异常 → unknown，不重启；
  - 进程启动 30 s 内不判；PREEMPT_SECONDS>0 时按运行时长兜底先行重启（默认 0 = 关）；
  - 退出（SIGTERM/SIGINT/SIGHUP）时把自己拉起的 sing-box 一起收掉，不留孤儿占端口。

配置路径候选：/etc/soga/soga.conf（现行）→ /etc/soco/soco.conf（旧路径）。
"""
import atexit
import base64
import json
import os
import signal
import socket
import subprocess
import sys
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

CONF_CANDIDATES = [Path('/etc/soga/soga.conf'), Path('/etc/soco/soco.conf')]
SBOX = Path('/usr/local/soco/sing-box-probe')
CFGPATH = Path('/usr/local/soco/watchdog-client.json')
LOG = Path('/var/log/soco-watchdog.log')
SERVICE = 'soco.service'
MARKER_PORT = 18089
SOCKS_PORT = 11009
PROBE_EVERY = int(os.environ.get('PROBE_EVERY', '30'))
FAILS_TO_RESTART = int(os.environ.get('FAILS_TO_RESTART', '3'))
PREEMPT = float(os.environ.get('PREEMPT_SECONDS', '0'))
MAX_LOG = 5 * 1024 * 1024
STORM_LIMIT = int(os.environ.get('STORM_LIMIT', '5'))   # 连续重启这么多次就停手


def log(rec):
    rec['utc'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
    try:
        if LOG.exists() and LOG.stat().st_size > MAX_LOG:
            os.replace(str(LOG), str(LOG) + '.1')
        with LOG.open('a') as f:
            f.write(json.dumps(rec) + '\n')
    except Exception:
        pass


class Marker(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-Length', '1')
        self.end_headers()
        self.wfile.write(b'M')

    def log_message(self, *a):
        pass


def conf_path():
    for p in CONF_CANDIDATES:
        if p.is_file():
            return p
    return None


def kv(path):
    d = {}
    for line in path.read_text(errors='replace').splitlines():
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            k, v = line.split('=', 1)
            d[k.strip()] = v.strip()
    return d


def panel(conf, what):
    base = conf['webapi_url'].rstrip('/')
    stype = conf.get('server_type', 'vless')
    node_type = {'ss': 'shadowsocks', 'v2ray': 'vmess'}.get(stype, stype)
    url = '%s/api/v1/server/UniProxy/%s?node_id=%s&node_type=%s&token=%s' % (
        base, what, conf['node_id'], node_type, conf['webapi_key'])
    out = subprocess.run(['curl', '-sS', '--max-time', '20', url],
                         capture_output=True, text=True, timeout=30)
    if out.returncode != 0:
        raise RuntimeError('panel fetch rc=%d %s' % (out.returncode, out.stderr.strip()[:120]))
    try:
        return json.loads(out.stdout)
    except ValueError:
        # 面板返回 HTML（域名错 / 面板维护）时以前直接抛 ValueError，日志里只有一个类型名
        raise RuntimeError('panel returned non-JSON: %s' % out.stdout[:120].replace('\n', ' '))


def build_cfg(conf, node, user, port):
    stype = conf.get('server_type', 'vless')
    if stype == 'ss':
        uk = base64.b64encode(str(uuid.UUID(str(user['uuid']))).encode('utf-8')[:32]).decode()
        out = {'type': 'shadowsocks', 'tag': 'node', 'server': '127.0.0.1',
               'server_port': int(node['server_port']), 'method': node['cipher'],
               'password': node['server_key'] + ':' + uk, 'network': 'tcp'}
        key = '%s|%s|%s' % (node['cipher'], node['server_port'], uk)
    else:
        tls = node.get('tls_settings') or {}
        out = {'type': 'vless', 'tag': 'node', 'server': '127.0.0.1',
               'server_port': int(node['server_port']), 'uuid': user['uuid'],
               'flow': node.get('flow') or 'xtls-rprx-vision',
               'tls': {'enabled': True,
                       'server_name': tls.get('server_name') or 'www.apple.com',
                       'utls': {'enabled': True, 'fingerprint': 'chrome'},
                       'reality': {'enabled': True,
                                   'public_key': tls.get('public_key'),
                                   'short_id': tls.get('short_id') or ''}}}
        key = '%s|%s|%s|%s' % (node['server_port'], user['uuid'],
                               tls.get('public_key'), tls.get('short_id'))
    cfg = {'log': {'level': 'error'},
           'inbounds': [{'type': 'socks', 'tag': 'in', 'listen': '127.0.0.1',
                         'listen_port': port}],
           'outbounds': [out], 'route': {'final': 'node'}}
    return cfg, key


def service_state():
    try:
        o = subprocess.run(['systemctl', 'show', SERVICE,
                            '--property=MainPID,ActiveState,NRestarts'],
                           capture_output=True, text=True, timeout=15).stdout
        return dict(l.split('=', 1) for l in o.splitlines() if '=' in l)
    except Exception:
        return {}


def soco_uptime():
    try:
        mono = int(subprocess.run(
            ['systemctl', 'show', SERVICE, '--property=ActiveEnterTimestampMonotonic', '--value'],
            capture_output=True, text=True, timeout=15).stdout.strip() or 0)
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
    subprocess.run(['systemctl', 'restart', SERVICE], capture_output=True, timeout=90)
    time.sleep(25)


def probe_once(port=SOCKS_PORT):
    c = subprocess.run(['curl', '-sS', '-x', 'socks5h://127.0.0.1:%d' % port,
                        '--max-time', '10', 'http://127.0.0.1:%d/' % MARKER_PORT],
                       capture_output=True, text=True, timeout=20)
    return (c.returncode == 0 and c.stdout.strip() == 'M'), c


def port_free(port, host='127.0.0.1'):
    """端口是否空闲（用来挑一个能用的 socks 端口）。"""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind((host, port))
        return True
    except OSError:
        return False
    finally:
        s.close()


def pick_socks_port(preferred=SOCKS_PORT, span=50):
    """挑一个空闲的 socks 端口。

    以前固定 11009：遗留的 sing-box（父进程被杀、子进程没回收）会一直占着它，
    重启 watchdog 后探针就永久起不来 —— 要么判成故障去重启健康服务，要么永远 skip。
    """
    for p in range(preferred, preferred + span):
        if port_free(p):
            return p
    return None


def main():
    try:
        srv = ThreadingHTTPServer(('127.0.0.1', MARKER_PORT), Marker)
    except OSError as e:
        # marker 端口被占：整个探针无法工作。以前直接 traceback → systemd 无限重启。
        log({'event': 'marker_bind_failed', 'port': MARKER_PORT, 'err': str(e)[:160],
             'action': 'exit'})
        print('watchdog: marker 端口 %d 被占用（%s）；不启动，避免把健康服务判成故障'
              % (MARKER_PORT, e), file=sys.stderr, flush=True)
        return 1
    srv.daemon_threads = True
    threading.Thread(target=srv.serve_forever, daemon=True).start()

    client = None
    client_key = None
    # 退出时把 sing-box 一起收掉：以前 systemctl stop/kill 只会杀 watchdog 本体，
    # sing-box 变孤儿继续占着 socks 端口和 ~80 MB 内存（实测踩过，下次启动只能换端口）。
    client_box = [None]

    def _cleanup_client():
        p = client_box[0]
        if p is not None and p.poll() is None:
            p.terminate()
            try:
                p.wait(timeout=5)
            except Exception:
                p.kill()

    atexit.register(_cleanup_client)

    def _on_term(signum, _frame):
        log({'event': 'watchdog_signal', 'signal': int(signum), 'action': 'exit'})
        raise SystemExit(0)

    for _sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        try:
            signal.signal(_sig, _on_term)
        except (ValueError, OSError):
            pass

    fails = 0
    restarts = 0
    storm = False
    logged_ok = False
    last_preempt = 0.0
    socks = pick_socks_port()
    if socks is None:
        log({'event': 'no_free_socks_port', 'preferred': SOCKS_PORT, 'action': 'exit'})
        print('watchdog: 11009..%d 全被占用，找不到空闲 socks 端口；不启动'
              % (SOCKS_PORT + 49), file=sys.stderr, flush=True)
        return 1
    cp = conf_path()
    log({'event': 'watchdog_start', 'conf': str(cp), 'probe_every': PROBE_EVERY,
         'fails_to_restart': FAILS_TO_RESTART, 'preempt_seconds': PREEMPT,
         'socks_port': socks, 'sbox': str(SBOX), 'sbox_present': SBOX.is_file()})

    while True:
        try:
            cp = conf_path()
            if cp is None:
                log({'event': 'conf_missing', 'candidates': [str(p) for p in CONF_CANDIDATES],
                     'action': 'skip'})
                time.sleep(PROBE_EVERY)
                continue
            up = soco_uptime()
            if up is not None and PREEMPT > 0 and up >= PREEMPT and (time.time() - last_preempt) > 60:
                last_preempt = time.time()
                restarts += 1
                restart('preemptive_before_key_check',
                        {'soco_uptime_s': round(up, 1), 'restarts': restarts})
            if up is not None and up < 30:
                time.sleep(PROBE_EVERY)
                continue

            conf = kv(cp)
            node = panel(conf, 'config')
            users = (panel(conf, 'user') or {}).get('users') or []
            if not users:
                log({'event': 'panel_no_users', 'action': 'skip'})
                time.sleep(PROBE_EVERY)
                continue

            cfg, key = build_cfg(conf, node, users[0], socks)
            if client is None or client.poll() is not None or client_key != key:
                if client is not None and client.poll() is None:
                    client.terminate()
                    try:
                        client.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        client.kill()
                CFGPATH.write_text(json.dumps(cfg), encoding='utf-8')
                CFGPATH.chmod(0o600)
                client = subprocess.Popen([str(SBOX), 'run', '-c', str(CFGPATH)],
                                          stdin=subprocess.DEVNULL,
                                          stdout=subprocess.DEVNULL,
                                          stderr=subprocess.DEVNULL)
                client_box[0] = client
                client_key = key
                time.sleep(3)

            ok, c = probe_once(socks)
            if ok:
                if fails:
                    log({'event': 'recovered', 'fails_before': fails})
                elif not logged_ok:
                    log({'event': 'probe_ok', 'type': conf.get('server_type'),
                         'server_port': node.get('server_port'),
                         'uuid': str(users[0].get('uuid'))[:8] + '…'})
                    logged_ok = True
                if storm:
                    log({'event': 'storm_cleared', 'restarts_before': restarts})
                    storm = False
                    restarts = 0
                fails = 0
            else:
                fails += 1
                log({'event': 'probe_failed', 'fails': fails, 'curl_exit': c.returncode,
                     'err': (c.stderr or '').strip()[:120], 'service': service_state(),
                     'soco_uptime_s': round(up or -1, 1), 'type': conf.get('server_type')})
                if fails >= FAILS_TO_RESTART:
                    restarts += 1
                    fails = 0
                    if restarts >= STORM_LIMIT:
                        # 重启 5 次还是不通：多半是节点/面板/网络本身的问题，继续重启只会
                        # 把服务来回掐断（每次 restart 都会断一次所有用户）。停手，只记录。
                        if not storm:
                            log({'event': 'restart_storm', 'restarts': restarts,
                                 'action': 'stop_restarting',
                                 'note': '恢复一次探活成功即自动解除并清零'})
                        storm = True
                    if not storm:
                        restart('probe_failed', {'restarts': restarts,
                                                 'type': conf.get('server_type')})
                        ok2, c2 = probe_once(socks)
                        log({'event': 'after_restart', 'ok': ok2, 'curl_exit': c2.returncode,
                             'restarts': restarts, 'service': service_state()})
        except Exception as e:
            log({'event': 'probe_error', 'type': type(e).__name__,
                 'message': str(e)[:200], 'action': 'skip'})
        time.sleep(PROBE_EVERY)


if __name__ == '__main__':
    sys.exit(main())