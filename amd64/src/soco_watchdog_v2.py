#!/usr/bin/env python3
"""soco watchdog v2: keeps the SS2022 service actually serving.

Background: this amd64 build loads every panel user and relays fine, but the periodic soga key check
(the node has no valid soga key) leaves the listener accepting nothing roughly 10 minutes after start.
Two defences:
  1. pre-emptive restart before the key check can fire (default 540 s of uptime);
  2. real-handshake probe every 30 s; one failure => restart.
Panel/network errors never trigger a restart (treated as unknown).
"""
import base64,importlib.util,json,os,subprocess,threading,time,uuid
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
CONF=Path('/etc/soco/soco.conf')
MODEL=Path('/usr/local/soco/watchdog-model.py')
SBOX=Path('/usr/local/soco/sing-box-probe')
LOG=Path('/var/log/soco-watchdog.log')
MARKER_PORT=18089
SOCKS_PORT=11009
PROBE_EVERY=int(os.environ.get('PROBE_EVERY','30'))
FAILS_TO_RESTART=int(os.environ.get('FAILS_TO_RESTART','1'))
PREEMPT=float(os.environ.get('PREEMPT_SECONDS','540'))
CFGPATH=Path('/usr/local/soco/watchdog-client.json')


def log(rec):
    rec['utc']=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())
    with LOG.open('a') as f:f.write(json.dumps(rec)+'\n')


class Marker(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200);self.send_header('Content-Length','1');self.end_headers();self.wfile.write(b'M')
    def log_message(self,*a):pass


def service_state():
    try:
        o=subprocess.run(['systemctl','show','soco.service','--property=MainPID,ActiveState,NRestarts'],
                         capture_output=True,text=True).stdout
        return dict(l.split('=',1) for l in o.splitlines() if '=' in l)
    except Exception:
        return {}


def soco_uptime():
    try:
        mono=int(subprocess.run(['systemctl','show','soco.service','--property=ActiveEnterTimestampMonotonic','--value'],
                                capture_output=True,text=True).stdout.strip() or 0)
        if mono<=0:return None
        now=int(float(Path('/proc/uptime').read_text().split()[0])*1_000_000)
        return max(0.0,(now-mono)/1_000_000)
    except Exception:
        return None


def restart(reason,extra=None):
    rec={'event':'restart','reason':reason}
    if extra:rec.update(extra)
    log(rec)
    subprocess.run(['systemctl','restart','soco.service'],capture_output=True)
    time.sleep(25)


def main():
    srv=ThreadingHTTPServer(('127.0.0.1',MARKER_PORT),Marker);srv.daemon_threads=True
    threading.Thread(target=srv.serve_forever,daemon=True).start()
    spec=importlib.util.spec_from_file_location('wdmodel',str(MODEL))
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    client=None;client_key=None;fails=0;restarts=0;last_preempt=0.0
    log({'event':'watchdog_start','probe_every':PROBE_EVERY,'fails_to_restart':FAILS_TO_RESTART,'preempt_seconds':PREEMPT})
    while True:
        try:
            up=soco_uptime()
            if up is not None and PREEMPT>0 and up>=PREEMPT and (time.time()-last_preempt)>60:
                last_preempt=time.time();restarts+=1
                restart('preemptive_before_key_check',{'soco_uptime_s':round(up,1),'restarts':restarts})
            if up is not None and up < 30:
                time.sleep(PROBE_EVERY);continue   # service still starting up: never judge it yet
            values=m.values_from_config(CONF.read_text())
            node,_,_=m.fetch(values,'config')
            users,_,_=m.fetch(values,'user')
            if not users.get('users'):
                log({'event':'panel_no_users','action':'skip'});time.sleep(PROBE_EVERY);continue
            method=node['cipher'];port=int(node['server_port']);sk=node['server_key']
            uk=base64.b64encode(str(uuid.UUID(users['users'][0]['uuid'])).encode('utf-8')[:32]).decode()
            password=sk+':'+uk
            if client is None or client.poll() is not None or client_key!=password:
                if client is not None and client.poll() is None:
                    client.terminate()
                    try:client.wait(timeout=5)
                    except subprocess.TimeoutExpired:client.kill()
                cfg={'log':{'level':'error'},
                     'inbounds':[{'type':'socks','tag':'in','listen':'127.0.0.1','listen_port':SOCKS_PORT}],
                     'outbounds':[{'type':'shadowsocks','tag':'ss','server':'127.0.0.1','server_port':port,
                                   'method':method,'password':password,'network':'tcp'}],
                     'route':{'final':'ss'}}
                CFGPATH.write_text(json.dumps(cfg),encoding='utf-8');CFGPATH.chmod(0o600)
                client=subprocess.Popen([str(SBOX),'run','-c',str(CFGPATH)],stdin=subprocess.DEVNULL,
                                        stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
                client_key=password;time.sleep(3)
            c=subprocess.run(['curl','-sS','-x','socks5h://127.0.0.1:%d'%SOCKS_PORT,'--max-time','10',
                              'http://127.0.0.1:%d/'%MARKER_PORT],capture_output=True,text=True,timeout=20)
            ok=c.returncode==0 and c.stdout.strip()=='M'
            if ok:
                if fails:log({'event':'recovered','fails_before':fails})
                fails=0
            else:
                fails+=1
                log({'event':'probe_failed','fails':fails,'curl_exit':c.returncode,
                     'err':c.stderr.strip()[:120],'service':service_state(),'soco_uptime_s':round(up or -1,1)})
                if fails>=FAILS_TO_RESTART:
                    restarts+=1;fails=0
                    restart('ss_probe_failed',{'restarts':restarts})
                    c2=subprocess.run(['curl','-sS','-x','socks5h://127.0.0.1:%d'%SOCKS_PORT,'--max-time','10',
                                       'http://127.0.0.1:%d/'%MARKER_PORT],capture_output=True,text=True,timeout=20)
                    log({'event':'after_restart','ok':c2.returncode==0 and c2.stdout.strip()=='M',
                         'curl_exit':c2.returncode,'restarts':restarts,'service':service_state()})
        except Exception as e:
            log({'event':'probe_error','type':type(e).__name__,'message':str(e)[:200],'action':'skip'})
        time.sleep(PROBE_EVERY)


if __name__=='__main__':
    main()