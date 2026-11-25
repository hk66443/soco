#!/usr/bin/env python3
"""soco-mesh v3 - keep a soco node serving with zero interruption, no restarts of live instances.

Facts this design relies on (measured): ~600 s after process start this build denies *new* connections
while already-established sessions keep working; a fresh instance has a full 600 s budget.

Design
  * relay owns the panel port (default 49989, TCP+UDP) and is always up;
  * one active backend + at most one successor, each on its own (never reused) internal port, fronted by a
    local panel proxy that rewrites server_port and swallows /push /alive for non-primary backends;
  * every ROTATE seconds a successor is started; once it is listening the relay points *new* connections
    at it, and the predecessor is retired only when it has no established connections (or after GRACE).
"""
import json,os,signal,socket,socketserver,ssl,subprocess,sys,threading,time,urllib.request,urllib.error
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path

BASE_CONF = Path('/etc/soco/soco.conf')
BINARY    = Path('/usr/local/soco/soco')
ADAPTER   = Path('/usr/local/soco/libsoco.so')
RUNDIR    = Path('/run/soco-mesh')
LOGF      = Path('/var/log/soco-mesh.log')
STATE_F   = Path('/run/soco-mesh-state.json')
LISTEN_PORT   = int(os.environ.get('MESH_LISTEN', '49989'))
PORT_BASE     = int(os.environ.get('MESH_PORT_BASE', '51000'))     # internal ports 51000+seq
PROXY_BASE    = int(os.environ.get('MESH_PROXY_BASE', '52000'))    # proxy ports 52000+seq
ROTATE_S      = int(os.environ.get('MESH_ROTATE', '480'))
GRACE_S       = int(os.environ.get('MESH_GRACE', '1800'))          # force-retire after this
READY_TIMEOUT = int(os.environ.get('MESH_READY_TIMEOUT', '45'))
CHECK_EVERY   = int(os.environ.get('MESH_CHECK', '20'))

lock = threading.Lock()
active = {'b': None}
ACTIVE_IDX = {'v': None}
backends = []          # list[Backend], all alive
seq = {'v': 0}
PANEL = None


def log(event, **kw):
    rec = {'utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), 'event': event}
    rec.update(kw)
    try:
        with LOGF.open('a') as f:
            f.write(json.dumps(rec, ensure_ascii=False) + '\n')
    except Exception:
        pass
    print(json.dumps(rec, ensure_ascii=False), flush=True)


def dump_state():
    with lock:
        st = {'utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), 'listen': LISTEN_PORT,
              'active': (active['b'].idx if active['b'] else None),
              'backends': [{'idx': b.idx, 'internal': b.internal, 'proxy': b.proxy_port, 'pid': b.proc.pid if b.proc else None,
                            'born_s_ago': round(time.time() - b.born, 1), 'retired': b.retired,
                            'established': established_count(b.internal)} for b in backends]}
    try:
        STATE_F.write_text(json.dumps(st))
    except Exception:
        pass


def panel_url():
    global PANEL
    for line in BASE_CONF.read_text().splitlines():
        if line.strip().startswith('webapi_url'):
            PANEL = line.split('=', 1)[1].strip().rstrip('/')
            return PANEL
    raise SystemExit('no webapi_url')


class ProxyHandler(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'
    upstream = ''
    rewrite_port = 0
    forward_posts = True
    idx = 0

    def _do(self):
        n = int(self.headers.get('Content-Length') or 0)
        body = self.rfile.read(n) if n else b''
        low = self.path.lower()
        is_primary = self.forward_posts and (ACTIVE_IDX['v'] == self.idx)
        if not is_primary and self.command == 'POST' and ('/push' in low or '/alive' in low or '/status' in low):
            out = b'{"data":true,"code":0,"message":"success"}'
            self.send_response(200); self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(out))); self.end_headers(); self.wfile.write(out); return
        hdrs = {k: v for k, v in self.headers.items() if k.lower() not in ('host', 'content-length', 'connection', 'accept-encoding')}
        status, out = 502, b''
        try:
            req = urllib.request.Request(self.upstream + self.path, data=body or None, headers=hdrs, method=self.command)
            with urllib.request.urlopen(req, timeout=25, context=ssl.create_default_context()) as r:
                status = r.status; out = r.read()
        except urllib.error.HTTPError as e:
            status = e.code; out = e.read()
        except Exception as e:
            status = 599; out = ('proxy error: %s' % type(e).__name__).encode()
        if status == 200 and out and '/config' in low and self.rewrite_port:
            try:
                j = json.loads(out); j['server_port'] = self.rewrite_port; out = json.dumps(j).encode()
            except Exception:
                pass
        self.send_response(status); self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(out))); self.end_headers()
        try:
            self.wfile.write(out)
        except Exception:
            pass

    do_GET = _do
    do_POST = _do
    do_PUT = _do

    def log_message(self, *a):
        pass


class ProxyServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def established_count(port):
    try:
        out = subprocess.run(['ss', '-Htn', 'state', 'established', '( sport = :%d )' % port],
                             capture_output=True, text=True, timeout=5).stdout
        return len([l for l in out.splitlines() if l.strip()])
    except Exception:
        return -1


def port_open(port):
    try:
        s = socket.create_connection(('127.0.0.1', port), timeout=1); s.close(); return True
    except Exception:
        return False


class Backend:
    def __init__(self, idx, internal, proxy_port, primary):
        self.idx = idx; self.internal = internal; self.proxy_port = proxy_port
        self.primary = primary; self.born = time.time(); self.ready = False; self.retired = False
        self.proc = None; self.srv = None; self.fh = None
        RUNDIR.mkdir(parents=True, exist_ok=True)
        self.conf = RUNDIR / ('mesh-%d.conf' % idx)
        self.logfile = RUNDIR / ('backend-%d.log' % idx)

    def start(self):
        text = []
        for line in BASE_CONF.read_text().splitlines():
            k = line.split('=', 1)[0].strip() if '=' in line and not line.lstrip().startswith('#') else None
            text.append('webapi_url=http://127.0.0.1:%d' % self.proxy_port if k == 'webapi_url' else line)
        self.conf.write_text('\n'.join(text) + '\n'); os.chmod(self.conf, 0o600)
        handler = type('H%d' % self.idx, (ProxyHandler,),
                       {'upstream': PANEL, 'rewrite_port': self.internal, 'forward_posts': True, 'idx': self.idx})
        for attempt in range(3):
            try:
                self.srv = ProxyServer(('127.0.0.1', self.proxy_port), handler); break
            except OSError as e:
                log('proxy_bind_retry', idx=self.idx, port=self.proxy_port, err=str(e))
                time.sleep(1)
        if not self.srv:
            return False
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        env = dict(os.environ); env['LD_PRELOAD'] = str(ADAPTER)
        self.fh = self.logfile.open('ab')
        self.proc = subprocess.Popen([str(BINARY), '-c', str(self.conf)], env=env,
                                     stdin=subprocess.DEVNULL, stdout=self.fh, stderr=self.fh)
        deadline = time.time() + READY_TIMEOUT
        while time.time() < deadline:
            if self.proc.poll() is not None:
                break
            if port_open(self.internal):
                self.ready = True; break
            time.sleep(0.4)
        log('backend_start', idx=self.idx, internal=self.internal, proxy=self.proxy_port,
            pid=self.proc.pid, ready=self.ready, primary=self.primary)
        dump_state()
        return self.ready

    def stop(self, why):
        try:
            if self.srv: self.srv.shutdown()
        except Exception:
            pass
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try: self.proc.wait(timeout=8)
            except subprocess.TimeoutExpired: self.proc.kill()
        try:
            if self.fh: self.fh.close()
        except Exception:
            pass
        log('backend_stop', idx=self.idx, reason=why)
        dump_state()


def next_ports():
    with lock:
        seq['v'] += 1
        s = seq['v']
    return s, PORT_BASE + s, PROXY_BASE + s


def launch(primary=False):
    idx, internal, proxy = next_ports()
    b = Backend(idx, internal, proxy, primary)
    if not b.start():
        b.stop('start_failed'); return None
    with lock:
        backends.append(b)
    if primary:
        with lock:
            old = active['b']; active['b'] = b
        ACTIVE_IDX['v'] = b.idx
        if old is not None:
            old.retired = True
        log('active_switch', new=b.idx, old=(old.idx if old else None))
        dump_state()
    return b


def pick():
    with lock:
        b = active['b']
        if b and b.ready and b.proc and b.proc.poll() is None:
            return b
        live = [x for x in backends if x.ready and x.proc and x.proc.poll() is None and not x.retired]
        if not live:
            live = [x for x in backends if x.ready and x.proc and x.proc.poll() is None]
        active['b'] = live[-1] if live else None
        return active['b']


def dial():
    deadline = time.time() + 6
    while time.time() < deadline:
        b = pick()
        if b:
            try:
                return socket.create_connection(('127.0.0.1', b.internal), timeout=3)
            except Exception:
                time.sleep(0.2)
        else:
            time.sleep(0.2)
    return None


def pipe(a, b):
    try:
        while True:
            r, _, _ = select.select([a, b], [], [], 120) if select else ([], [], [])
            if not r:
                break
            for s in r:
                d = s.recv(65536)
                if not d:
                    return
                (b if s is a else a).sendall(d)
    except Exception:
        pass
    finally:
        for s in (a, b):
            try: s.shutdown(socket.SHUT_RDWR)
            except Exception: pass
            try: s.close()
            except Exception: pass


def tcp_relay():
    ls = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    ls.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    ls.bind(('0.0.0.0', LISTEN_PORT)); ls.listen(2048)
    log('relay_tcp_listen', port=LISTEN_PORT)
    while True:
        try:
            c, addr = ls.accept()
        except Exception:
            continue
        c.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        u = dial()
        if u is None:
            log('relay_no_backend', client='%s:%d' % addr)
            try: c.close()
            except Exception: pass
            continue
        threading.Thread(target=pipe, args=(c, u), daemon=True).start()


def udp_relay():
    us = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    us.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    us.bind(('0.0.0.0', LISTEN_PORT))
    log('relay_udp_listen', port=LISTEN_PORT)
    peers = {}
    while True:
        try:
            data, addr = us.recvfrom(65535)
        except Exception:
            continue
        b = pick()
        if b is None:
            continue
        now = time.time(); ent = peers.get(addr)
        if ent is None or now - ent[1] > 30 or ent[2] != b.idx:
            if ent:
                try: ent[0].close()
                except Exception: pass
            ups = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            try:
                ups.connect(('127.0.0.1', b.internal))
            except Exception:
                ups.close(); continue
            peers[addr] = (ups, now, b.idx)
            threading.Thread(target=udp_back, args=(ups, us, addr), daemon=True).start()
            ent = peers[addr]
        try:
            ent[0].send(data); peers[addr] = (ent[0], now, ent[2])
        except Exception:
            pass


def udp_back(ups, us, addr):
    ups.settimeout(45)
    while True:
        try:
            d = ups.recv(65535)
        except Exception:
            return
        try:
            us.sendto(d, addr)
        except Exception:
            return


def reaper():
    while True:
        time.sleep(CHECK_EVERY)
        now = time.time(); victims = []
        with lock:
            act = active['b']
            for b in list(backends):
                if b is act:
                    continue
                if b.proc is None or b.proc.poll() is not None:
                    victims.append((b, 'dead')); continue
                age = now - b.born
                if established_count(b.internal) == 0 and age > 60:
                    victims.append((b, 'idle'))
                elif age > GRACE_S:
                    victims.append((b, 'grace'))
        for b, why in victims:
            b.stop(why)
            with lock:
                if b in backends:
                    backends.remove(b)
        dump_state()


def rotator():
    while True:
        time.sleep(ROTATE_S)
        try:
            b = launch(primary=True)
            log('rotate', new=(b.idx if b else None),
                established={x.idx: established_count(x.internal) for x in backends})
        except Exception as e:
            log('rotate_error', err=type(e).__name__, msg=str(e)[:200])


def health():
    while True:
        time.sleep(10)
        b = pick()
        if b is None:
            log('no_backend_alive', action='spawn')
            launch(primary=True)


def main():
    global select
    import select as _select
    select = _select
    LOGF.parent.mkdir(parents=True, exist_ok=True); RUNDIR.mkdir(parents=True, exist_ok=True)
    panel_url()
    log('mesh_start', listen=LISTEN_PORT, port_base=PORT_BASE, proxy_base=PROXY_BASE,
        rotate=ROTATE_S, grace=GRACE_S, panel=PANEL, pid=os.getpid())
    if not launch(primary=True):
        log('first_backend_failed'); sys.exit(3)
    threading.Thread(target=tcp_relay, daemon=True).start()
    threading.Thread(target=udp_relay, daemon=True).start()
    threading.Thread(target=reaper, daemon=True).start()
    threading.Thread(target=rotator, daemon=True).start()
    threading.Thread(target=health, daemon=True).start()

    def bye(*a):
        log('mesh_stop')
        for b in list(backends):
            try: b.stop('shutdown')
            except Exception: pass
        sys.exit(0)
    signal.signal(signal.SIGTERM, bye); signal.signal(signal.SIGINT, bye)
    while True:
        time.sleep(5)


if __name__ == '__main__':
    main()