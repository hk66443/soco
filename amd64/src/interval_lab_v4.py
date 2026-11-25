#!/usr/bin/env python3
"""Lab: run an isolated candidate instance against a mock panel (works with no internet).

Panel config/user JSON can come from --fixtures (pre-captured files) so the instance also runs inside
`unshare -n`, where the external world (e.g. a licence endpoint) is unreachable.
"""
import argparse,base64,importlib.util,json,os,shutil,subprocess,threading,time,uuid
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
ROOT=Path('/root/soco-verified-tests')
ap=argparse.ArgumentParser()
ap.add_argument('--run-id',required=True);ap.add_argument('--port',type=int,required=True)
ap.add_argument('--mock-port',type=int,required=True);ap.add_argument('--pull',type=int,default=60)
ap.add_argument('--push',type=int,default=60);ap.add_argument('--duration',type=int,default=300)
ap.add_argument('--probe-every',type=float,default=10.0)
ap.add_argument('--fixtures',default='')
ap.add_argument('--cand',default='/root/soco-verified-tests/candidates/verified53-20261121-minimal-v1/soco')
ap.add_argument('--so',default='/root/soco-verified-tests/adapter-clean-build-20261121-v1/libsoco-amd64.so')
a=ap.parse_args()
HOME=ROOT/a.run_id
assert not HOME.exists();HOME.mkdir(mode=0o700);os.umask(0o077)
if a.fixtures:
    fx=Path(a.fixtures);node_raw=(fx/'config.json').read_text();user_raw=(fx/'user.json').read_text()
else:
    spec=importlib.util.spec_from_file_location('m',ROOT/'real_node341_v2.py')
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    values=m.values_from_config(Path('/etc/soco/soco.conf').read_text())
    node_raw=m.fetch(values,'config')[1];user_raw=m.fetch(values,'user')[1]
mock_node=json.loads(node_raw);mock_node['server_port']=a.port
mock_node['base_config']={'push_interval':a.push,'pull_interval':a.pull}
users=json.loads(user_raw)
server_key=mock_node['server_key'];method=mock_node['cipher']
uk=base64.b64encode(str(uuid.UUID(users['users'][0]['uuid'])).encode('utf-8')[:32]).decode()
class Mock(BaseHTTPRequestHandler):
    def do_GET(self):
        body=json.dumps(mock_node if '/config' in self.path else users).encode()
        self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
    def log_message(self,*x):pass
class MK(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200);self.send_header('Content-Length','1');self.end_headers();self.wfile.write(b'M')
    def log_message(self,*x):pass
class Srv(ThreadingHTTPServer):daemon_threads=True
mock=Srv(('127.0.0.1',a.mock_port),Mock);threading.Thread(target=mock.serve_forever,daemon=True).start()
marker=Srv(('127.0.0.1',a.mock_port+1),MK);threading.Thread(target=marker.serve_forever,daemon=True).start()
lines=[]
for line in Path('/etc/soco/soco.conf').read_text().splitlines():
    k=line.split('=',1)[0].strip() if '=' in line and not line.lstrip().startswith('#') else None
    if k=='webapi_url':lines.append('webapi_url=http://127.0.0.1:%d'%a.mock_port)
    elif k=='webapi_key':lines.append('webapi_key=local-test-token')
    else:lines.append(line)
cand=HOME/'soco';shutil.copy2(a.cand,cand);cand.chmod(0o755)
so=HOME/'libsoco.so';shutil.copy2(a.so,so);so.chmod(0o600)
cfg=HOME/'test.conf';cfg.write_text('\n'.join(lines)+'\n');cfg.chmod(0o600)
sbgport=a.mock_port+100
sbgcfg=HOME/'client.json'
sbgcfg.write_text(json.dumps({'log':{'level':'error'},
  'inbounds':[{'type':'socks','tag':'in','listen':'127.0.0.1','listen_port':sbgport}],
  'outbounds':[{'type':'shadowsocks','tag':'ss','server':'127.0.0.1','server_port':a.port,'method':method,'password':server_key+':'+uk,'network':'tcp'}],
  'route':{'final':'ss'}}),encoding='utf-8');sbgcfg.chmod(0o600)
env={'PATH':'/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin','LD_PRELOAD':str(so),'HOME':str(HOME)}
srvlog=(HOME/'server.log').open('wb')
server=subprocess.Popen([str(cand),'-c',str(cfg)],cwd=str(HOME),env=env,stdin=subprocess.DEVNULL,stdout=srvlog,stderr=srvlog)
clog=(HOME/'client.log').open('wb')
client=subprocess.Popen(['/tmp/sing-box','run','-c',str(sbgcfg)],stdin=subprocess.DEVNULL,stdout=clog,stderr=clog)
def cycles():return (HOME/'server.log').read_text(errors='replace').count('current user num')
def probe():
    c=subprocess.run(['curl','-sS','-x','socks5h://127.0.0.1:%d'%sbgport,'--max-time','10','http://127.0.0.1:%d/'%(a.mock_port+1)],capture_output=True,text=True,timeout=20)
    return c.returncode==0 and c.stdout.strip()=='M',c.returncode
res={'run_id':a.run_id,'cand':a.cand,'so':a.so,'pull':a.pull,'push':a.push,'port':a.port,'fixtures':bool(a.fixtures),'probes':[],'first_failure':None}
t0=time.time()
while time.time()-t0<25:
    o=subprocess.run(['ss','-lnt','sport','=',':%d'%a.port],capture_output=True,text=True).stdout
    if ':%d'%a.port in o:break
    time.sleep(0.5)
try:
    while time.time()-t0<a.duration:
        ok,code=probe()
        rec={'t':round(time.time()-t0,1),'cycles':cycles(),'ok':ok,'curl':code}
        res['probes'].append(rec)
        if not ok:
            res['first_failure']=rec
            for _ in range(2):
                time.sleep(5);ok2,c2=probe()
                res['probes'].append({'t':round(time.time()-t0,1),'cycles':cycles(),'ok':ok2,'curl':c2})
            break
        (HOME/'result.partial.json').write_text(json.dumps(res,indent=2),encoding='utf-8')
        time.sleep(a.probe_every)
finally:
    for p in (client,server):
        if p.poll() is None:
            p.terminate()
            try:p.wait(timeout=5)
            except subprocess.TimeoutExpired:p.kill()
    mock.shutdown();marker.shutdown();srvlog.close();clog.close()
    (HOME/'result.json').write_text(json.dumps(res,indent=2),encoding='utf-8')
    print(json.dumps({'run_id':a.run_id,'pull':a.pull,'probes':len(res['probes']),
        'fails':sum(1 for x in res['probes'] if not x['ok']),'first_failure':res['first_failure'],
        'final_cycles':res['probes'][-1]['cycles'] if res['probes'] else 0},ensure_ascii=False))