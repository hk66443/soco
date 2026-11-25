#!/usr/bin/env bash
# switch_stream_area.sh — 切换 routes.toml 中「#Main / 跨国」出口的地区
# 用法: ./switch_stream_area.sh [us|hk|tw|jp|kr|sg|uk]
# 说明: 只改第一个 [[routes.Outs]] 块（Netflix/ChatGPT/Disney/HBO/Spotify 等共用），
#       其余地区块不动；改动同 inode + 同长度，soco 的 fs watcher 会即时重载。
set -euo pipefail

declare -A NODE=(
  [us]="node-us.nfdns.xyz 38383"
  [hk]="node-hk.nfdns.xyz 38888"
  [tw]="node-tw.nfdns.xyz 20558"
  [jp]="node-jp.nfdns.xyz 38123"
  [kr]="node-kr.nfdns.xyz 23355"
  [sg]="node-sg.nfdns.xyz 20955"
  [uk]="node-uk.nfdns.xyz 25253"
)

area="${1:-us}"
if [[ -z "${NODE[$area]:-}" ]]; then
  echo "usage: $0 us|hk|tw|jp|kr|sg|uk" >&2
  exit 2
fi
read -r srv port <<<"${NODE[$area]}"

P=/etc/soga/routes.toml
[[ -r $P ]] || { echo "missing $P" >&2; exit 1; }

mkdir -p /root/rollback
cp -a "$P" "/root/rollback/routes.toml.bak.$(date -u +%Y%m%dT%H%M%SZ)"

python3 - "$srv" "$port" "$P" <<'PY'
import re, sys
srv, port, p = sys.argv[1], sys.argv[2], sys.argv[3]
d = open(p, 'rb').read()
i = d.find(b'[[routes.Outs]]')
if i < 0:
    sys.exit('no [[routes.Outs]] found')
j = d.find(b'[[routes]]', i)
if j < 0:
    j = len(d)
seg = d[i:j]
new = re.sub(rb'server="[^"]*"', ('server="%s"' % srv).encode(), seg, count=1)
new = re.sub(rb'port=\d+', ('port=%s' % port).encode(), new, count=1)
if len(new) != len(seg):
    # 长度变化时改为整文件重写（会换 inode，之后由 touch 触发重载）
    open(p, 'wb').write(d[:i] + new + d[j:])
else:
    with open(p, 'r+b') as f:
        f.write(d[:i] + new + d[j:])
print('patched first Outs ->', srv, port)
PY

touch "$P"
sleep 3
L="/etc/soga/soga-vless-$(date +%Y-%m-%d).log"
grep -a 'load routes config' "$L" | tail -1 || true
echo "--- 当前出口 ---"
awk '/\[\[routes.Outs\]\]/{n++} n==1 && /^(server|port|password)=/{print}' "$P" | head -3