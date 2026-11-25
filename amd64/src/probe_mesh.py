#!/usr/bin/env python3
"""Probe client for the mesh test: real SS2022 handshake through a given local port, every N seconds."""
import argparse,base64,importlib.util,json,os,socket,struct,subprocess,threading,time,uuid
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
ROOT=Path('/root/soco-verified-tests')
ap=argparse.ArgumentParser()
ap.add_argument('--run-id',required=True);ap.add_argument('--port',type=int,required=True)
ap.add_argument('--duration',type=int,default=900);ap.add_argument('--every',type=int,default=15)
a=ap.parse_args()
HOME=ROOT/a.run_id
assert not HOME.exists();HOME.mkdir(mode=0o700);os.umask(0o077)
spec=importlib.util.spec_from_file_location('m',ROOT/'real_node341_v2.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
values=m.values_from_config(Path('/etc/soco/soco.conf').read_text())
node,_,_=m.fetch(values,'config');users,_,_=m.fetch(values,'user')
sk=node['server_key'];method=node['cipher'];user=users['users'][0]
uk=base64.b64encode(str(uuid.UUID(user['uuid'])).encode()[:32]).decode()
MARK='M'
class MK(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200);self.send_header('Content-Length','1');self.end_headers();self.wfile.write(b'M')
    def log_message(self,*x):pass
class Srv(ThreadingHTTPServer):daemon_threads=True
mkport=18900+a.port%1000
marker=Srv(('127.0.0.1',mkport),MK);threading.Thread(target=marker.serve_forever,daemon=True).start()
socks=a.port%1000+18800
cfg=HOME/'client.json'
cfg.write_text(json.dumps({'log':{'level':'error'},
  'inbounds':[{'type':'socks','tag':'in','listen':'127.0.0.1','listen_port':socks}],
  'outbounds':[{'type':'shadowsocks','tag':'ss','server':'127.0.0.1','server_port':a.port,'method':method,'password':sk+':'+uk,'network':'tcp'}],
  'route':{'final':'ss'}}),encoding='utf-8');cfg.chmod(0o600)
clog=(HOME/'client.log').open('wb')
client=subprocess.Popen(['/tmp/sing-box','run','-c',str(cfg)],stdin=subprocess.DEVNULL,stdout=clog,stderr=clog)
time.sleep(3)
res={'run_id':a.run_id,'port':a.port,'probes':[],'first_failure':None}
t0=time.time()
def probe():
    c=subprocess.run(['curl','-sS','-x','socks5h://127.0.0.1:%d'%socks,'--max-time','12','http://127.0.0.1:%d/'%mkport],
                     capture_output=True,text=True,timeout=20)
    return (c.returncode==0 and c.stdout.strip()=='M'),c.returncode
try:
    while time.time()-t0<a.duration:
        ok,code=probe()
        rec={'t':round(time.time()-t0,1),'ok':ok,'curl':code}
        try:
            rec['mesh']=json.loads(Path('/run/soco-mesh-state.json').read_text()) if Path('/run/soco-mesh-state.json').exists() else None
        except Exception:
            pass
        res['probes'].append(rec)
        if not ok and res['first_failure'] is None:
            res['first_failure']=rec
        (HOME/'result.partial.json').write_text(json.dumps(res,indent=2),encoding='utf-8')
        time.sleep(a.every)
finally:
    client.terminate()
    try:client.wait(timeout=5)
    except subprocess.TimeoutExpired:client.kill()
    marker.shutdown();clog.close()
    (HOME/'result.json').write_text(json.dumps(res,indent=2),encoding='utf-8')
    fails=[p for p in res['probes'] if not p['ok']]
    print(json.dumps({'run_id':a.run_id,'port':a.port,'probes':len(res['probes']),'fails':len(fails),
                      'first_failure':res['first_failure'],
                      'fail_times':[p['t'] for p in fails][:10]},ensure_ascii=False))