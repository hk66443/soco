#!/usr/bin/env python3
"""soco routes guard：让 nfu / soga 重新生成 /etc/soga/routes.toml 后，
Netflix/OpenAI 的台湾出口补丁自动补回（幂等）。

背景：`nfu soga` 会直接用模板覆盖 /etc/soga/routes.toml，再 `soga restart`。
本守卫由 systemd path unit 监听文件变化触发：
  - 检测到补丁标记 `# soco-route-tw` 存在 → 直接退出；
  - 不存在 → 在 `enable=true` 之后插入补丁块（password 沿用文件里第一个 ss 出站的密码，
    即 nfu 替换后的 UUID），并触发 soco 重新加载路由（若 soco 自身 watch 已生效则自动加载）。

避坑：
  - path unit 在「文件被改动」时会连续触发；守卫自己写文件又会触发一次。用 flock 串行化，
    否则两个实例都读到「没有补丁」→ 各插一份 → routes 里出现两份 TW 规则；
  - 插入的是 `type="ss"` 出站。如果文件里根本没有 ss 出站（客户换成纯 vless），注入后整份
    routes 会解析失败 → soco **静默**退化成 0 条分流（历史上踩过一次）。所以先校验再动手；
  - 覆盖写要保留原文件权限，否则 600 变 644（里面有 password）。
"""
import os
import re
import sys
import time
from pathlib import Path

ROUTES = Path('/etc/soga/routes.toml')
MARK = '# soco-route-tw'
LOG = Path('/var/log/soco-routes-guard.log')
LOCK = Path('/var/lock/soco-routes-guard.lock')
TW_SERVER = 'node-tw.nfdns.xyz'
TW_PORT = 20558
TW_CIPHER = 'chacha20-ietf-poly1305'

RULES = [
    'geosite:netflix',
    'domain:netflix.com',
    'domain:nflxvideo.net',
    'domain:nflximg.net',
    'domain:nflxso.net',
    'geosite:openai',
    'domain:chatgpt.com',
    'domain:chatgpt.site',
    'domain:chat.com',
    'domain:openai.com',
    'domain:oaistatic.com',
    'domain:oaiusercontent.com',
    'domain:oaistatsig.com',
]


def log(msg):
    try:
        with LOG.open('a') as f:
            f.write('%s %s\n' % (time.strftime('%Y-%m-%d %H:%M:%S'), msg))
    except Exception:
        pass
    print(msg, flush=True)


def take_lock():
    """避免 path unit 并发触发造成的重复插入。拿不到锁返回 'busy'，非 Linux 返回 None。"""
    try:
        import fcntl
    except ImportError:
        return None
    try:
        LOCK.parent.mkdir(parents=True, exist_ok=True)
        f = LOCK.open('a+')
    except OSError:
        return None
    try:
        fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        f.close()
        return 'busy'
    return f


TYPE_SS = re.compile(r'^\s*type\s*=\s*"ss"\s*$', re.M)
PW_QUOTED = re.compile(r'^\s*password\s*=\s*"([^"]*)"', re.M)
PW_BARE = re.compile(r'^\s*password\s*=\s*([^\s#]+)', re.M)


def outbound_blocks(text):
    """把 routes.toml 切成出站块列表（只取 `[[routes.Outs]]` 头之后的正文）。

    以前是「全文正则找第一个 password=」：客户把 trojan/vmess 排在 ss 前面时，
    拿到的是别的出站的密码 → 注入的 ss 出站必然认证失败 → 分流静默失效。
    所以必须按块配对。
    """
    blocks = []
    for chunk in re.split(r'(?m)^\s*\[\[routes', text)[1:]:
        head, sep, body = chunk.partition(']]')
        if sep and 'Outs' in head:
            blocks.append(body)
    return blocks


def find_ss_password(text):
    """第一个 ss 出站块里的 password；没有 ss 出站或还没写密码 → None。"""
    for body in outbound_blocks(text):
        if TYPE_SS.search(body) is None:
            continue
        m = PW_QUOTED.search(body) or PW_BARE.search(body)
        if m:
            return m.group(1).strip('"')
    return None


def has_ss_outbound(text):
    """文件里有没有 ss 出站（我们注入的补丁也是 ss：没有的话注入后整份 routes 会解析失败）。

    这里故意用全文匹配而不是分块：它只决定「跳过 vs 等下一次」，
    宁可多等一轮也不要因为块头缺失把该打的补丁漏掉。
    """
    return TYPE_SS.search(text) is not None


def patch_text(text, pw, server=TW_SERVER, port=TW_PORT, cipher=TW_CIPHER):
    """把补丁块插在 enable=true 之后；没有 anchor 返回 None。纯函数，便于单测。"""
    anchor = 'enable=true'
    if anchor not in text:
        return None
    i = text.index(anchor) + len(anchor)
    rules = ',\n    '.join('"%s"' % r for r in RULES)
    block = (
        '\n\n%s (Netflix/OpenAI -> TW; nfu 重生成后自动补回)\n'
        '[[routes]]\n'
        'rules=[\n    %s\n]\n\n'
        '[[routes.Outs]]\n'
        'listen=""\n'
        'type="ss"\n'
        'server="%s"\n'
        'port=%d\n'
        'password="%s"\n'
        'cipher="%s"\n'
        % (MARK, rules, server, port, pw, cipher)
    )
    return text[:i] + block + text[i:]


def stable(path, wait=2.0):
    """文件正在被 nfu 写（wget/sed）时不要动手：mtime 连续不变才算稳定。"""
    try:
        m1 = os.stat(path).st_mtime_ns
        time.sleep(wait)
        m2 = os.stat(path).st_mtime_ns
        return m1 == m2
    except FileNotFoundError:
        return False


def main():
    if not ROUTES.is_file():
        log('routes file missing, skip')
        return 0
    lk = take_lock()
    if lk == 'busy':
        log('another guard instance is running, skip')
        return 0
    try:
        return run()
    finally:
        if lk is not None:
            try:
                lk.close()
            except Exception:
                pass


def run():
    # nfu 是「wget 覆盖 + 3 次 sed」，期间会多次触发；这里最多重试 4 次等它写完
    for attempt in range(4):
        text = ROUTES.read_text(encoding='utf-8', errors='replace')
        if MARK in text:
            return 0                  # 幂等：已打过补丁
        if '{UUID}' in text or '{Out}' in text or '{OutPort}' in text:
            log('template placeholders present (nfu still writing), retry %d' % attempt)
            time.sleep(3)
            continue
        if not stable(ROUTES):
            log('routes file still changing, retry %d' % attempt)
            continue
        # 密码必须取自 **ss 出站块**（补丁里注入的就是 ss）：全文找第一个 password= 会
        # 拿到 trojan/vmess 出站的密码 → 补丁出站认证失败 → 分流静默失效。
        pw = find_ss_password(text)
        if not pw:
            if not has_ss_outbound(text):
                # 没有 ss 出站：注入 ss 补丁会让整份 routes 解析失败（soco 会静默 0 条分流）
                log('no ss outbound in routes.toml (vless-only?), skip TW patch')
                return 0
            log('ss outbound has no password yet, retry %d' % attempt)
            time.sleep(2)
            continue
        new = patch_text(text, pw)
        if new is None:
            log('enable=true missing (partial write?), retry %d' % attempt)
            time.sleep(2)
            continue
        tmp = ROUTES.with_name(ROUTES.name + '.guard.tmp')
        tmp.write_text(new, encoding='utf-8')
        try:
            os.chmod(tmp, os.stat(ROUTES).st_mode & 0o7777)   # 别把 600 写成 644（含 password）
        except OSError:
            pass
        os.replace(str(tmp), str(ROUTES))
        log('patched: inserted TW route after enable=true (password len=%d)' % len(pw))
        # soco 的 fsnotify 只对内容写入（IN_MODIFY）稳定触发；rename/utime 不可靠。
        # 追加一个空行即可触发重新加载，且不影响 TOML。
        time.sleep(0.5)
        try:
            with ROUTES.open('ab') as f:
                f.write(b'\n')
        except Exception:
            pass
        return 0
    log('gave up after retries (file may still be written by nfu)')
    return 0


if __name__ == '__main__':
    sys.exit(main())