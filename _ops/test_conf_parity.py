#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""本地单元测试：so-console 的配置生成 / 合并 / 一致性校验 (不接触真机)"""
import importlib.util
import importlib.machinery
import re
import sys
import tempfile
from pathlib import Path

SRC = Path(__file__).resolve().parent / 'public' / 'console' / 'so-console'
spec = importlib.util.spec_from_loader('socon', importlib.machinery.SourceFileLoader('socon', str(SRC)))
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

# 原版 soga 2.18.1 模板（从 AMD 目标机 /usr/local/soga/soga.conf 抓回来的原文）
ORIG = """# 基础配置
type=
server_type=
node_id=
soga_key=

# webapi 或 db 对接任选一个
api=webapi

# webapi 对接信息
webapi_url=
webapi_key=

# db 对接信息
db_host=
db_port=
db_name=
db_user=
db_password=

# 手动证书配置
cert_file=
key_file=

# 自动证书配置
cert_mode=
cert_domain=
cert_key_length=ec-256
dns_provider=

# proxy protocol 中转配置
proxy_protocol=false
udp_proxy_protocol=false

# 全局限制用户 IP 数配置(需 Redis 8.0+)
redis_ip_limit_enable=false
redis_ip_limit_addr=
redis_ip_limit_password=
redis_ip_limit_db=0
redis_ip_limit_tls=false
redis_ip_limit_expiry=60

# 动态限速配置
dy_limit_enable=false
dy_limit_duration=
dy_limit_trigger_time=60
dy_limit_trigger_speed=100
dy_limit_speed=30
dy_limit_time=600
dy_limit_white_user_id=

# 其它杂项
user_conn_limit=0
user_speed_limit=0
user_tcp_limit=0
node_speed_limit=0

check_interval=60
submit_interval=60
forbidden_bit_torrent=true
log_level=info

# 更多配置项请看文档根据需求自行添加
"""

fails = []


def check(name, cond, detail=''):
    print(('  PASS  ' if cond else '  FAIL  ') + name + (('  ' + detail) if detail and not cond else ''))
    if not cond:
        fails.append(name)


tmp = Path(tempfile.mkdtemp(prefix='soconf-'))

# ---- 1) 全新生成：键集合必须与原版模板完全一致
p1 = tmp / 'new' / 'soga.conf'
m.write_conf(p1, '341', 'ss', 'https://panel.example.com', 'PANELKEY1234', 'SogaKeyRand')
k1 = list(m.parse_conf(p1))
tkeys = re.findall(r'^([A-Za-z_][A-Za-z0-9_]*)=', ORIG, re.M)
check('新生成配置的键集合 == 原版模板', set(k1) == set(tkeys),
      'diff={}'.format(set(k1) ^ set(tkeys)))
check('新生成配置的键顺序 == 原版模板', k1 == tkeys)
check('原版模板 41 个键全在', len(k1) == 41, '实际 %d' % len(k1))

body1 = p1.read_text(encoding='utf-8')
check('值已填入 node_id', 'node_id=AMD_NODE_ID' in body1)
check('webapi_key 保持面板值', 'webapi_key=PANELKEY1234' in body1)
check('log_level=error（固定项）', 'log_level=error' in body1)
check('forbidden_bit_torrent 按原版写 true', 'forbidden_bit_torrent=true' in body1)
check('cert_key_length 按原版 ec-256', 'cert_key_length=ec-256' in body1)

# 注释分节与原版一致
c1 = [l for l in body1.splitlines() if l.startswith('#')]
c0 = [l for l in ORIG.splitlines() if l.startswith('#')]
check('注释分节与原版逐行一致', c1 == c0, 'gen={} orig={}'.format(c1, c0))

# 行数：原版 47 键 + 注释/空行
check('总行数与模板一致（%d）' % len(ORIG.splitlines()),
      len(body1.splitlines()) == len(ORIG.splitlines()),
      'gen=%d orig=%d' % (len(body1.splitlines()), len(ORIG.splitlines())))

# ---- 2) 合并写入：客户在原版上开过的功能不能被覆盖
p2 = tmp / 'old' / 'soga.conf'
p2.parent.mkdir(parents=True)
p2.write_text(ORIG
              .replace('dy_limit_enable=false', 'dy_limit_enable=true')
              .replace('dy_limit_speed=30', 'dy_limit_speed=50')
              .replace('redis_ip_limit_enable=false', 'redis_ip_limit_enable=true')
              .replace('redis_ip_limit_addr=', 'redis_ip_limit_addr=127.0.0.1:6379')
              .replace('user_conn_limit=0', 'user_conn_limit=5')
              .replace('proxy_protocol=false', 'proxy_protocol=true')
              .replace('log_level=info', 'log_level=debug')
              .replace('type=', 'type=xboard') + '\nmy_custom_key=keepme\n', encoding='utf-8')
m.write_conf(p2, '644', 'vless', 'https://panel2.example.com', 'PANELKEY2', 'Soga2')
k2 = m.parse_conf(p2)
check('merge 保留 dy_limit_enable=true', k2.get('dy_limit_enable') == 'true')
check('merge 保留 dy_limit_speed=50', k2.get('dy_limit_speed') == '50')
check('merge 保留 redis_ip_limit_addr', k2.get('redis_ip_limit_addr') == '127.0.0.1:6379')
check('merge 保留 user_conn_limit=5', k2.get('user_conn_limit') == '5')
check('merge 保留 proxy_protocol=true', k2.get('proxy_protocol') == 'true')
check('merge 保留模板外自定义键', k2.get('my_custom_key') == 'keepme')
check('merge 更新 node_id=ARM_NODE_ID', k2.get('node_id') == '644')
check('merge 更新 server_type=vless', k2.get('server_type') == 'vless')
check('merge 固定项 log_level 回到 error', k2.get('log_level') == 'error')
check('merge 后键集合仍含原版全部键', set(tkeys) <= set(k2))
check('merge 后没有重复键行',
      len([l for l in p2.read_text(encoding='utf-8').splitlines()
           if re.match(r'^[A-Za-z_][A-Za-z0-9_]*=', l)]) == len(k2))

# ---- 3) conf_check：缺键必须能查出来
p3 = tmp / 'short' / 'soga.conf'
p3.parent.mkdir(parents=True)
p3.write_text('type=xboard\nserver_type=ss\nnode_id=1\nlog_level=debug\n', encoding='utf-8')
miss, extra, diff = m.conf_check({'conf': str(p3)}, quiet=True)
check('conf_check 查出缺键', len(miss) == 37, 'missing=%d' % len(miss))
check('conf_check 不把标准键当多余键', not extra)

miss1, extra1, diff1 = m.conf_check({'conf': str(p1)}, quiet=True)
check('新生成配置 conf_check 无缺键', not miss1)
check('新生成配置 conf_check 无多余键', not extra1)

# ---- 4) 幂等：同一份配置连跑两次结果相同
before = p1.read_text(encoding='utf-8')
m.write_conf(p1, '341', 'ss', 'https://panel.example.com', 'PANELKEY1234', 'SogaKeyRand')
after = p1.read_text(encoding='utf-8')
check('install 幂等：两次生成完全一致', before == after)

# ---- 5) TLS 证书模式
p4 = tmp / 'tls' / 'soga.conf'
m.write_conf(p4, '9', 'trojan', 'https://p.example.com', 'K', 'S',
             cert={'mode': 'file', 'domain': 'node.example.com',
                   'cert_file': '/etc/ssl/fullchain.pem', 'key_file': '/etc/ssl/privkey.pem'})
k4 = m.parse_conf(p4)
check('cert_mode=file 写入', k4.get('cert_mode') == 'file')
check('cert_file 写入', k4.get('cert_file') == '/etc/ssl/fullchain.pem')
p5 = tmp / 'tls2' / 'soga.conf'
m.write_conf(p5, '9', 'anytls', 'https://p.example.com', 'K', 'S',
             cert={'mode': 'dns', 'domain': 'n.example.com', 'dns_provider': 'cloudflare'})
k5 = m.parse_conf(p5)
check('cert_mode=dns + dns_provider 写入',
      k5.get('cert_mode') == 'dns' and k5.get('dns_provider') == 'cloudflare')
p6 = tmp / 'tls3' / 'soga.conf'
m.write_conf(p6, '9', 'vless', 'https://p.example.com', 'K', 'S',
             cert={'mode': 'panel', 'domain': 'r.example.com'})
k6 = m.parse_conf(p6)
check('cert_mode=panel 不写文件路径',
      k6.get('cert_mode') == 'panel' and k6.get('cert_file') == '' and k6.get('key_file') == '')

# ---- 6) 与原版模板的逐行 diff（只允许值不同，不允许行结构不同）
import difflib
gen = p1.read_text(encoding='utf-8').splitlines()
orig = ORIG.splitlines()
structural = []
for line in difflib.unified_diff(orig, gen, lineterm='', n=0):
    if line.startswith(('---', '+++', '@@')):
        continue
    if line.startswith(('-', '+')) and '=' not in line.lstrip('-+'):
        structural.append(line)
check('与原版模板行结构差异仅限取值', not structural, str(structural[:4]))

print()
print('TOTAL %s / %d 项' % ('OK' if not fails else 'FAIL(%d)' % len(fails), len(fails) + 0 or 0))
print('生成样例：%s' % p1)
sys.exit(0 if not fails else 1)