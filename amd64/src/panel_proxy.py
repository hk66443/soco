#!/usr/bin/env python3
"""Logging/rewriting HTTP proxy in front of the soga panel, to expose the periodic key-check exchange.

Forwards every request to the real panel over HTTPS, records method/path/status/bodies (masked) into
proxy-log.jsonl, and can rewrite selected responses:
  --rewrite-config-port N   rewrite the node config's server_port (so a lab instance can use its own port)
  --rewrite-key-ok          answer "success" for any non config/user endpoint (candidate key-check fix)
"""
import argparse,hashlib,json,base64,os,ssl,urllib.request,urllib.error
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
ap=argparse.ArgumentParser()
ap.add_argument('--port',type=int,required=True);ap.add_argument('--target',required=True)
ap.add_argument('--log',required=True);ap.add_argument('--rewrite-config-port',type=int,default=0)
ap.add_argument('--rewrite-key-ok',action='store_true')
a=ap.parse_args()
LOG=Path(a.log);LOG.parent.mkdir(parents=True,exist_ok=True)
CTX=ssl.create_default_context()
def mask(s):
    s=str(s)
    s=s.replace(os.environ.get('P_MASK1','\x00'),'\x00')
    return s[:600]
class H(BaseHTTPRequestHandler):
    protocol_version='HTTP/1.1'
    def _do(self):
        n=int(self.headers.get('Content-Length') or 0)
        body=self.rfile.read(n) if n else b''
        path=self.path
        url=a.target.rstrip('/')+path
        hdrs={k:v for k,v in self.headers.items() if k.lower() not in ('host','content-length','connection','accept-encoding')}
        out=b'';status=502;rewritten=None
        try:
            req=urllib.request.Request(url,data=body if body else None,headers=hdrs,method=self.command)
            with urllib.request.urlopen(req,timeout=20,context=CTX) as r:
                status=r.status;out=r.read()
        except urllib.error.HTTPError as e:
            status=e.code;out=e.read()
        except Exception as e:
            status=599;out=('proxy error: %s'%type(e).__name__).encode()
        low=path.lower()
        is_cfg='/config' in low;is_user='/user' in low
        if status==200 and out:
            try:j=json.loads(out)
            except Exception:j=None
            if j is not None:
                if is_cfg and a.rewrite_config_port:
                    j['server_port']=a.rewrite_config_port;out=json.dumps(j).encode();rewritten='config.server_port'
                if a.rewrite_key_ok and not is_cfg and not is_user:
                    out=json.dumps({'code':200,'message':'ok','data':{}}).encode();rewritten='key_ok'
        rec={'utc':__import__('time').strftime('%Y-%m-%dT%H:%M:%SZ',__import__('time').gmtime()),
             'method':self.command,'path':path[:200],'status':status,
             'req_sha256':hashlib.sha256(body).hexdigest()[:16] if body else None,
             'req_len':len(body),
             'resp_sha256':hashlib.sha256(out).hexdigest()[:16],'resp_len':len(out),
             'rewritten':rewritten,
             'req_preview':mask(body.decode('utf-8','replace')) if body else '',
             'resp_preview':mask(out.decode('utf-8','replace'))}
        with LOG.open('a') as f:f.write(json.dumps(rec)+'\n')
        self.send_response(status)
        self.send_header('Content-Type','application/json')
        self.send_header('Content-Length',str(len(out)))
        self.end_headers();self.wfile.write(out)
    do_GET=_do
    do_POST=_do
    do_PUT=_do
    def log_message(self,*x):pass
srv=ThreadingHTTPServer(('127.0.0.1',a.port),H);srv.daemon_threads=True
print(json.dumps({'proxy':a.port,'target':a.target,'rewrite_config_port':a.rewrite_config_port,'rewrite_key_ok':a.rewrite_key_ok}),flush=True)
srv.serve_forever()