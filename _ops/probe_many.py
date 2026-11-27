#!/usr/bin/env python3
"""多用户真实握手抽检：从面板取用户，逐个用 sing-box 客户端打本机节点。

用法：probe_many.py <count> [--idx 1,50,89,91,100,150,200,300,400,497]
协议自动识别：server_type=ss -> SS2022；vless -> VLESS+REALITY（参数从面板 config 拉）。
"""
import base64
import json
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path

CONF = (Path(os.environ['SO_PROBE_CONF']) if os.environ.get('SO_PROBE_CONF')
        else next((p for p in [Path('/etc/soga/soga.conf'), Path('/etc/soco/soco.conf')]
                   if p.is_file()), None))
SBOX = Path('/usr/local/soco/sing-box-probe')
# 每次运行用独立目录 + 独立端口段：两个 probe 同时跑（或实例部署的验证和手动 probe 撞上）
# 会抢同一个 socks 端口，表现为随机 FAIL。
# 目录放 /var/tmp（根分区）而不是 /tmp：/tmp 常是 tmpfs，写满时 sing-box 配置写不进去，
# 表现为 `OSError: [Errno 28] No space left on device`（AMD 上实测过，tmpfs 只有 482 MB）。
WORK = Path('/var/tmp/probe-multi-%d' % os.getpid())
PORT_BASE = 13000 + (os.getpid() % 1000)
TRACE = 'https://www.cloudflare.com/cdn-cgi/trace'


def kv(path):
    d = {}
    for line in path.read_text(errors='replace').splitlines():
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            k, v = line.split('=', 1)
            d[k.strip()] = v.strip()
    return d


def panel(conf, what):
    missing = [k for k in ('webapi_url', 'node_id', 'webapi_key') if not conf.get(k)]
    if missing:
        raise SystemExit('配置缺少 %s（conf=%s）' % (', '.join(missing), CONF))
    base = conf['webapi_url'].rstrip('/')
    node = conf['node_id']
    stype = conf.get('server_type', 'vless')
    node_type = {'ss': 'shadowsocks', 'v2ray': 'vmess'}.get(stype, stype)
    url = '%s/api/v1/server/UniProxy/%s?node_id=%s&node_type=%s&token=%s' % (
        base, what, node, node_type, conf['webapi_key'])
    out = subprocess.run(['curl', '-sS', '--max-time', '20', url], capture_output=True, text=True)
    if out.returncode != 0:
        raise SystemExit('panel fetch failed: %s' % out.stderr[:200])
    try:
        return json.loads(out.stdout)
    except ValueError:
        raise SystemExit('面板返回的不是 JSON（前 160 字节：%s）—— 查 webapi_url 是否正确、面板是否在维护'
                         % out.stdout[:160].replace('\n', ' '))


def build_cfg(conf, node, user, port):
    stype = conf.get('server_type', 'vless')
    if stype == 'ss':
        for k in ('cipher', 'server_key', 'server_port'):
            if not node.get(k):
                raise SystemExit('面板 config 缺少 %s（ss 节点）；查面板侧该节点的 ss 配置' % k)
        if not user.get('uuid'):
            raise SystemExit('面板用户缺少 uuid')
        uk = base64.b64encode(str(uuid.UUID(user['uuid'])).encode('utf-8')[:32]).decode()
        out = {'type': 'shadowsocks', 'tag': 'node', 'server': '127.0.0.1',
               'server_port': int(node['server_port']), 'method': node['cipher'],
               'password': node['server_key'] + ':' + uk, 'network': 'tcp'}
    else:
        tls = node.get('tls_settings') or {}
        if not tls.get('public_key'):
            # REALITY 必须要有 public_key；面板没配好时以前会生成非法配置 → sing-box 起不来 → 全 FAIL
            raise SystemExit('节点是 %s + REALITY，但面板 config 没有 tls_settings.public_key'
                             '（面板侧这个节点没配 REALITY？）' % stype)
        out = {'type': 'vless', 'tag': 'node', 'server': '127.0.0.1',
               'server_port': int(node['server_port']), 'uuid': user['uuid'],
               'flow': node.get('flow') or 'xtls-rprx-vision',
               'tls': {'enabled': True, 'server_name': tls.get('server_name') or 'www.apple.com',
                       'utls': {'enabled': True, 'fingerprint': 'chrome'},
                       'reality': {'enabled': True, 'public_key': tls.get('public_key'),
                                   'short_id': tls.get('short_id') or ''}}}
    return {'log': {'level': 'error'},
            'inbounds': [{'type': 'socks', 'tag': 'in', 'listen': '127.0.0.1', 'listen_port': port}],
            'outbounds': [out], 'route': {'final': 'node'}}


def main():
    try:
        count = int(sys.argv[1]) if len(sys.argv) > 1 else 12
    except ValueError:
        print('count 必须是正整数（或 all）：%s' % sys.argv[1])
        return 2
    if count < 0:
        print('count 不能是负数：%s' % count)
        return 2
    idx_arg = sys.argv[2] if len(sys.argv) > 2 else ''
    if idx_arg and not all(x.strip().isdigit() for x in idx_arg.split(',') if x.strip()):
        print('索引只能是逗号分隔的数字：%s' % idx_arg)
        return 2
    conf = kv(CONF)
    cfg = panel(conf, 'config')
    users = panel(conf, 'user')['users']
    n = len(users)
    if n == 0:
        # 面板这个节点一个用户都没有：以前 idxs 为空 → TOTAL ok=0/0 → rc=0（假成功）
        print('面板没有用户（node_id=%s, type=%s）' % (conf.get('node_id'), conf.get('server_type')))
        return 3
    if idx_arg:
        idxs = [int(x) - 1 for x in idx_arg.split(',') if 1 <= int(x) <= n]
    elif count >= n:
        idxs = list(range(n))
    else:
        step = max(1, n // count)
        idxs = list(range(0, n, step))[:count]
    if not idxs:
        print('索引全部越界（面板只有 %d 个用户）' % n)
        return 3
    try:
        WORK.mkdir(parents=True, exist_ok=True)
        WORK.chmod(0o700)       # 目录里全是含密钥的配置
    except OSError as e:
        print('临时目录不可写：%s（%s）—— 检查 /var/tmp 空间' % (WORK, e))
        return 4
    print('users=%d sample=%d type=%s conf=%s uptime_done'
          % (n, len(idxs), conf.get('server_type'), CONF))
    ok = 0
    fails = []
    for i, ix in enumerate(idxs):
        user = users[ix]
        port = PORT_BASE + i
        p = WORK / ('%d.json' % i)
        p.write_text(json.dumps(build_cfg(conf, cfg, user, port)))
        try:
            p.chmod(0o600)      # 配置里有 server_key + uuid，别让同机其它用户读到
        except OSError:
            pass
        proc = subprocess.Popen([str(SBOX), 'run', '-c', str(p)],
                                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL)
        time.sleep(2.0)
        r = subprocess.run(['curl', '-sS', '-x', 'socks5h://127.0.0.1:%d' % port,
                            '--max-time', '12', TRACE], capture_output=True, text=True)
        good = r.returncode == 0 and 'ip=' in r.stdout
        if good:
            ok += 1
        else:
            fails.append((ix + 1, user['uuid'][:8], r.returncode, r.stderr.strip()[:60]))
        print('  idx=%-4d id=%-6s uuid=%s %s' % (ix + 1, user.get('id', '?'), user['uuid'][:8],
                                                 'OK' if good else 'FAIL'))
        proc.terminate()
        try:
            proc.wait(timeout=4)
        except subprocess.TimeoutExpired:
            proc.kill()
        time.sleep(0.3)
    print('TOTAL ok=%d/%d' % (ok, len(idxs)))
    for f in fails:
        print('  FAIL %s' % (f,))
    # 每次都留下 /tmp/probe-multi-<pid>/ 会越攒越多（每个几十 KB），跑完就清
    import shutil
    shutil.rmtree(WORK, ignore_errors=True)
    return 0 if ok == len(idxs) else 1


if __name__ == '__main__':
    sys.exit(main())