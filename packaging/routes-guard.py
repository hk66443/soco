#!/usr/bin/env python3
"""soco routes guard：让 nfu / soga 重新生成 /etc/soga/routes.toml 后，
Netflix/OpenAI 的台湾出口补丁自动补回（幂等）。

背景：`nfu soga` 会直接用模板覆盖 /etc/soga/routes.toml，再 `soga restart`。
本守卫由 systemd path unit 监听文件变化触发：
  - 检测到补丁标记 `# soco-route-tw` 存在 → 直接退出；
  - 不存在 → 在 `enable=true` 之后插入补丁块（password 沿用文件里第一个 ss 出站的密码，
    即 nfu 替换后的 UUID），并触发 soco 重新加载路由（若 soco 自身 watch 已生效则自动加载）。
"""
import os
import re
import subprocess
import sys
import time
from pathlib import Path

ROUTES = Path('/etc/soga/routes.toml')
MARK = '# soco-route-tw'
LOG = Path('/var/log/soco-routes-guard.log')
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
    print(msg)


def find_password(text):
    m = re.search(r'^\s*password\s*=\s*"([^"]+)"', text, re.M)
    if m:
        return m.group(1)
    m = re.search(r'^\s*password\s*=\s*([^\s#]+)', text, re.M)
    return m.group(1).strip('"') if m else None


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
    # nfu 是「wget 覆盖 + 3 次 sed」，期间会多次触发；这里最多重试 3 次等它写完
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
        pw = find_password(text)
        if not pw:
            log('no ss outbound password found, retry %d' % attempt)
            time.sleep(2)
            continue
        anchor = 'enable=true'
        if anchor not in text:
            log('enable=true missing (partial write?), retry %d' % attempt)
            time.sleep(2)
            continue
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
            % (MARK, rules, TW_SERVER, TW_PORT, pw, TW_CIPHER)
        )
        new = text[:i] + block + text[i:]
        tmp = ROUTES.with_suffix('.toml.guard.tmp')
        tmp.write_text(new, encoding='utf-8')
        tmp.replace(ROUTES)
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