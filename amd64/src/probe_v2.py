#!/usr/bin/env python3
"""Single cheap health probe for the deployed service: SS2022 auth + relay to a local marker.

Writes one JSON line to /root/soco-verified-tests/probe-health.log. No external network dependency.
Usage: probe_v2.py --run-id <id>
"""
import argparse,base64,importlib.util,json,os,subprocess,threading,time,uuid
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
ROOT=Path('/root/soco-verified-tests')
ap=argparse.ArgumentParser();ap.add_argument('--run-id',required=True);args=ap.parse_args()
HOME=ROOT/'probes'/args.run_id
assert not HOME.exists();HOME.mkdir(parents=True,mode=0o700);os.umask(0o077)
spec=importlib.util.spec_from_file_location('m',ROOT/'real_node341_v2.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
conf_path=Path('/etc/soga/soga.conf')
if not conf_path.is_file(): conf_path=Path('/etc/soco/soco.conf')
values=m.values_from_config(conf_path.read_text())
node,_,_=m.fetch(values,'config');users,_,_=m.fetch(values,'user')
server_key=node['server_key'];method=node['cipher'];user=users['users'][0]
uk=base64.b64encode(str(uuid.UUID(user['uuid'])).encode('utf-8')[:32]).decode()
MARK='PROBE-%s'%args.run_id
class H(BaseHTTPRequestHandler):
    def do_GET(self):
        b=MARK.encode();self.send_response(200);self.send_header('Content-Length',str(len(b)));self.end_headers();self.wfile.write(b)
    def log_message(self,*a):pass
srv=ThreadingHTTPServer(('127.0.0.1',18081),H);th=threading.Thread(target=srv.serve_forever,daemon=True);th.start()
cfg=HOME/'c.json'
cfg.write_text(json.dumps({'log':{'level':'error'},
  'inbounds':[{'type':'socks','tag':'in','listen':'127.0.0.1','listen_port':11002}],
  'outbounds':[{'type':'shadowsocks','tag':'ss','server':'127.0.0.1','server_port':49989,'method':method,'password':server_key+':'+uk,'network':'tcp'}],
  'route':{'final':'ss'}}),encoding='utf-8');cfg.chmod(0o600)
pid=int(subprocess.run(['systemctl','show','soco.service','--property=MainPID','--value'],capture_output=True,text=True).stdout.strip())
st=subprocess.run(['systemctl','show','soco.service','--property=ActiveState,NRestarts,ExecMainStartTimestamp'],capture_output=True,text=True).stdout
jl=subprocess.run(['journalctl','-b','_PID=%d'%pid,'--no-pager','-o','cat'],capture_output=True,text=True).stdout
cycles=jl.count('current user num')
log=HOME/'sb.log'
res={'run_id':args.run_id,'utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'pid':pid,'cycles_since_start':cycles,
     'service_state':dict(l.split('=',1) for l in st.splitlines() if '=' in l)}
with log.open('wb') as lf:
    p=subprocess.Popen(['/tmp/sing-box','run','-c',str(cfg)],stdin=subprocess.DEVNULL,stdout=lf,stderr=lf)
    time.sleep(2.5)
    c=subprocess.run(['curl','-sS','-x','socks5h://127.0.0.1:11002','--max-time','12','http://127.0.0.1:18081/'],capture_output=True,text=True,timeout=20)
    p.terminate()
    try:p.wait(timeout=4)
    except subprocess.TimeoutExpired:p.kill()
srv.shutdown()
res.update({'curl_exit':c.returncode,'body':c.stdout.strip()[:80],'err':c.stderr.strip()[:160],
            'PASS':c.returncode==0 and c.stdout.strip()==MARK})
tail=[l for l in log.read_text(errors='replace').splitlines() if 'ERROR' in l or 'FATAL' in l][-3:]
if tail:res['singbox_errors']=tail
jl2=subprocess.run(['journalctl','-b','_PID=%d'%pid,'--no-pager','-o','cat','--since','-30s'],capture_output=True,text=True).stdout
conn=[l.split('\t')[-1] for l in jl2.splitlines() if 'new ss' in l or 'new user conn' in l or 'not exist' in l]
res['server_lines_last_30s']=conn
with open(ROOT/'probe-health.log','a') as f:f.write(json.dumps(res)+'\n')
print(json.dumps(res,ensure_ascii=False))