#!/usr/bin/env python3
"""Single-host, pinned-key SSH/SFTP wrapper for isolated compatibility tests.
Secrets are read only from this process environment. No credential files or shell argv.
New local evidence only in this directory; remote writes only in verified test root.
"""
import argparse
import hashlib
import json
import os
import posixpath
import re
import stat
import sys
import time
from pathlib import Path

import paramiko

HERE=Path(__file__).resolve().parent
HOST='AMD_IP'
REMOTE_ROOT='/root/soco-verified-tests'
KNOWN_HOSTS=HERE.parent/'vps_known_hosts_141_148_139_236'


def check_remote(path):
    normalized=posixpath.normpath(path)
    if normalized != path or not (normalized==REMOTE_ROOT or normalized.startswith(REMOTE_ROOT+'/')):
        raise ValueError('Exact approved test-root path required')
    return normalized


def check_local(path, existing=False):
    p=Path(path).resolve()
    if HERE not in p.parents: raise ValueError('Local artifacts limited to own implementation directory')
    if existing and not p.is_file(): raise ValueError('Existing regular local file required')
    return p


def connection():
    if os.environ.get('SOGA_SSH_HOST')!=HOST: raise ValueError('Exact amd64 host environment required')
    password=os.environ.get('SOGA_SSH_PASSWORD')
    if not password: raise ValueError('Password process environment missing')
    if not KNOWN_HOSTS.is_file(): raise ValueError('Pre-existing pinned host-key file missing')
    c=paramiko.SSHClient(); c.load_host_keys(str(KNOWN_HOSTS)); c.set_missing_host_key_policy(paramiko.RejectPolicy())
    c.connect(HOST,port=22,username='root',password=password,look_for_keys=False,allow_agent=False,
              timeout=20,banner_timeout=40,auth_timeout=40)
    c.get_transport().set_keepalive(15)
    return c


def sanitize(data):
    text=data.decode('utf-8','replace')
    for key in ('SOGA_SSH_PASSWORD','SOCO_TEST_PASSWORD','SOCO_MOCK_TOKEN','SOCO_TEST_SERVER_KEY'):
        value=os.environ.get(key)
        if value: text=text.replace(value,'<redacted>')
    text=re.sub(r'(?i)([?&](?:token|key|api_key|password)=)[^\s&"\']+',r'\1<redacted>',text)
    return text.encode('utf-8')


def ensure_dirs(s,path):
    path=check_remote(path)
    pieces=path.strip('/').split('/'); current=''
    for piece in pieces:
        current+='/'+piece
        try:
            mode=s.stat(current).st_mode
            if not stat.S_ISDIR(mode): raise ValueError('Remote directory component not directory')
        except FileNotFoundError:
            check_remote(current); s.mkdir(current,0o700)


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('mode',choices=['exec-file','put','get','stat'])
    ap.add_argument('first'); ap.add_argument('second',nargs='?')
    ap.add_argument('--timeout',type=float,default=450)
    args=ap.parse_args(); c=connection()
    try:
        if args.mode=='exec-file':
            script=check_local(args.first,existing=True).read_text(encoding='utf-8')
            output=check_local(args.second)
            if output.exists() or output.with_suffix(output.suffix+'.stderr').exists(): raise FileExistsError('Unique execution evidence path required')
            chan=c.get_transport().open_session(); chan.exec_command(script)
            out,err=bytearray(),bytearray(); deadline=time.monotonic()+args.timeout
            while True:
                while chan.recv_ready(): out.extend(chan.recv(65536))
                while chan.recv_stderr_ready(): err.extend(chan.recv_stderr(65536))
                if chan.exit_status_ready():
                    while chan.recv_ready(): out.extend(chan.recv(65536))
                    while chan.recv_stderr_ready(): err.extend(chan.recv_stderr(65536))
                    break
                if time.monotonic()>deadline:
                    with output.open('xb') as f: f.write(sanitize(out))
                    with output.with_suffix(output.suffix+'.stderr').open('xb') as f: f.write(sanitize(err))
                    chan.close()
                    raise TimeoutError('SSH channel deadline; inspect exact run PID/state before considering another run')
                time.sleep(0.04)
            rc=chan.recv_exit_status(); out=sanitize(out);err=sanitize(err)
            with output.open('xb') as f:f.write(out)
            with output.with_suffix(output.suffix+'.stderr').open('xb') as f:f.write(err)
            sys.stdout.buffer.write(out);sys.stderr.buffer.write(err);sys.stdout.flush();sys.stderr.flush()
            print('\nREMOTE_EXIT_CODE',rc,flush=True)
            return rc
        s=c.open_sftp()
        try:
            if args.mode=='put':
                local=check_local(args.first,existing=True);remote=check_remote(args.second)
                ensure_dirs(s,posixpath.dirname(remote))
                try:
                    s.stat(remote); raise FileExistsError('Remote existing artifact never overwritten')
                except FileNotFoundError: pass
                s.put(str(local),remote);s.chmod(remote,0o700 if local.name=='soco' else 0o600)
                print(json.dumps(dict(uploaded=remote,bytes=s.stat(remote).st_size,local_sha256=hashlib.sha256(local.read_bytes()).hexdigest())))
            elif args.mode=='get':
                remote=check_remote(args.first);local=check_local(args.second)
                if local.exists():raise FileExistsError('New local evidence path required')
                mode=s.stat(remote).st_mode
                if not stat.S_ISREG(mode):raise ValueError('Remote regular file required')
                if local.suffix in ('.json','.jsonl','.txt','.log','.md','.py','.sh'):
                    with s.open(remote,'rb') as f:data=sanitize(f.read())
                    with local.open('xb') as f:f.write(data)
                else:
                    s.get(remote,str(local))
                print(json.dumps(dict(downloaded=remote,local=str(local),bytes=local.stat().st_size,sha256=hashlib.sha256(local.read_bytes()).hexdigest())))
            else:
                remote=check_remote(args.first); st=s.stat(remote)
                print(json.dumps(dict(path=remote,size=st.st_size,mode=oct(stat.S_IMODE(st.st_mode)))))
        finally:s.close()
        return 0
    finally:c.close()

if __name__=='__main__':sys.exit(main())
