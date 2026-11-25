#!/usr/bin/env bash
# soco-ctl — soco（soga crack + 面板适配层）一体化管理入口
# 这台机器上 soga/soco 都是纯 flag 二进制，没有 start/stop 子命令，管理全靠 systemd + 配置 + 日志。
# 本脚本把常用操作收成一条命令，等价于你以前"进 soga"的那些动作。
set -uo pipefail

SVC=soco
CONF=/etc/soco/soco.conf
ROUTES=/etc/soga/routes.toml
LOGDIR=/etc/soga
PROBE_PORT=$(grep -E '^server_port=' "$CONF" 2>/dev/null | head -1 | cut -d= -f2-)
PROBE_PORT=${PROBE_PORT:-49999}

logf() { echo "$LOGDIR/soga-vless-$(date +%Y-%m-%d).log"; }

hr() { printf '%s\n' "------------------------------------------------------------"; }

need_root() { [[ $(id -u) -eq 0 ]] || { echo "需要 root" >&2; exit 1; }; }

cmd_status() {
  local L; L=$(logf)
  echo "== 服务 =="
  printf '  状态      : %s / %s\n' "$(systemctl is-active $SVC 2>&1)" "$(systemctl is-enabled $SVC 2>&1)"
  printf '  PID       : %s\n' "$(systemctl show $SVC -p MainPID --value 2>/dev/null)"
  printf '  重启次数  : %s\n' "$(systemctl show $SVC -p NRestarts --value 2>/dev/null)"
  printf '  启动时间  : %s\n' "$(systemctl show $SVC -p ExecMainStartTimestamp --value 2>/dev/null)"
  local pid; pid=$(systemctl show $SVC -p MainPID --value 2>/dev/null)
  if [[ -n $pid && -d /proc/$pid ]]; then
    printf '  运行时长  : %s\n' "$(ps -o etime= -p "$pid" | tr -d ' ')"
    printf '  内存      : %s\n' "$(awk '/VmRSS/{printf "%.1f MB", $2/1024}' /proc/$pid/status 2>/dev/null)"
    printf '  适配层    : %s\n' "$(tr '\0' '\n' < /proc/$pid/environ 2>/dev/null | grep -c LD_PRELOAD || true) (1=已加载)"
  fi
  hr
  echo "== 端口 =="
  ss -lntp 2>/dev/null | grep -E ":$PROBE_PORT\b" || echo "  !! 没有在听 :$PROBE_PORT"
  printf '  已建立连接: %s\n' "$(ss -tn 2>/dev/null | grep -c -E "[ :]${PROBE_PORT}\b" || true)"
  hr
  echo "== 面板 =="
  grep -E '^(type|server_type|node_id|api|webapi_url)=' "$CONF" 2>/dev/null | sed 's/^/  /'
  hr
  echo "== 分流（流媒体解锁）=="
  grep -a 'load routes config' "$L" 2>/dev/null | tail -1 | sed 's/^/  /'
  awk '/\[\[routes.Outs\]\]/{n++} n==1 && /^(server|port)=/{print "  #Main 出口: " $0}' "$ROUTES" 2>/dev/null | head -2
  printf '  最近解锁命中: %s\n' "$(grep -ac 'tcp proxy dial' "$L" 2>/dev/null || echo 0) 次（本日累计）"
  hr
  echo "== 用户 =="
  grep -a 'current user num' "$L" 2>/dev/null | tail -1 | sed 's/^/  /'
  echo "== 最近 5 条访问 =="
  grep -a 'access address' "$L" 2>/dev/null | tail -5 | sed -E 's/^([0-9\/]+ [0-9:]+)\t[^\t]*\t/\1  /' | sed 's/^/  /'
}

cmd_log() {
  local L; L=$(logf)
  if [[ ${1:-} == "-f" ]]; then
    tail -n 80 -f "$L"
  else
    tail -n "${1:-60}" "$L"
  fi
}

cmd_restart() {
  need_root
  systemctl restart "$SVC"
  sleep 5
  cmd_status
}

cmd_verify() {
  local L; L=$(logf)
  echo "== 1. 进程 / 适配层 =="
  systemctl is-active "$SVC"
  local pid; pid=$(systemctl show $SVC -p MainPID --value)
  echo "  LD_PRELOAD 命中: $(tr '\0' '\n' < /proc/$pid/environ 2>/dev/null | grep -c LD_PRELOAD)"
  echo "  libsoco 已映射: $(grep -c libsoco /proc/$pid/maps 2>/dev/null)"
  hr
  echo "== 2. 面板接口 =="
  local url key node
  url=$(grep -E '^webapi_url=' "$CONF" | cut -d= -f2-)
  key=$(grep -E '^webapi_key=' "$CONF" | cut -d= -f2-)
  node=$(grep -E '^node_id=' "$CONF" | cut -d= -f2-)
  local code; code=$(curl -s -o /tmp/.soco-cfg.json -w '%{http_code}' -A 'sing-box/1.11' --max-time 15 \
    "$url/api/v1/server/UniProxy/config?node_id=$node&node_type=vless&token=$key")
  echo "  config 接口: HTTP $code"
  [[ $code == 200 ]] && sed -E 's/,"private_key":"[^"]*"//' /tmp/.soco-cfg.json | cut -c1-240 | sed 's/^/    /'
  hr
  echo "== 3. 分流是否真的在走解锁节点 =="
  grep -a 'tcp proxy dial' "$L" 2>/dev/null | tail -3 | sed 's/^/  /'
  echo "  （上面应出现 -> node-xx.nfdns.xyz:PORT；只有 direct dial 说明没走解锁，看 routes num 是否 >=10）"
  hr
  echo "== 4. 结论 =="
  if systemctl is-active -q "$SVC" && grep -aq 'load routes config.*routes num: 10' "$L"; then
    echo "  进程在跑 + routes 10 条已加载 → 服务端 OK。最后一步请在客户端实际打开 Netflix/ChatGPT 确认。"
  else
    echo "  !! 进程或 routes 有问题：soco-ctl restart 后仍不行就看 soco-ctl log"
  fi
}

cmd_area() {
  need_root
  [[ -n ${1:-} ]] || { echo "用法: soco-ctl area us|hk|tw|jp|kr|sg|uk"; exit 2; }
  /usr/local/bin/switch_stream_area.sh "$1"
}

cmd_uuid() {
  need_root
  local u=${1:-}
  [[ -n $u ]] || { echo "用法: soco-ctl uuid <你的解锁授权UUID>"; echo "当前: $(grep -m1 '^password=' "$ROUTES" | cut -d'"' -f2)"; exit 2; }
  [[ $u =~ ^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$ ]] || { echo "不是合法 UUID" >&2; exit 2; }
  cp -a "$ROUTES" "/root/rollback/routes.toml.bak.$(date -u +%Y%m%dT%H%M%SZ)"
  python3 - "$u" "$ROUTES" <<'PY'
import re, sys
u, p = sys.argv[1], sys.argv[2]
d = open(p, 'rb').read()
new, n = re.subn(rb'(?m)^password="[^"]*"', ('password="%s"' % u).encode(), d)
open(p, 'r+b').write(new)
print('replaced password in', n, 'blocks ->', u)
PY
  touch "$ROUTES"
  sleep 4
  grep -a 'load routes config' "$(logf)" | tail -1
  echo "提示: 用客户端打开 Netflix 验证这个 uuid 是否被解锁服务授权。"
}

cmd_conf() {
  echo "== $CONF（脱敏）=="
  sed -E 's/((soga|webapi)_?key|token|password)[[:space:]]*=[[:space:]]*.*/\1=***/I' "$CONF"
  hr
  echo "== unit =="
  systemctl cat "$SVC" 2>/dev/null
}

cmd_help() {
  cat <<EOF
soco-ctl — 管理这台机器上的 soco

  soco-ctl status          服务/端口/用户/分流/最近访问 一屏
  soco-ctl log [-f] [N]    看日志（-f 跟随）
  soco-ctl restart         重启并立刻回显状态
  soco-ctl verify          四关自检（进程+适配层 / 面板接口 / 解锁分流 / 结论）
  soco-ctl area <地区>      切换流媒体出口：us hk tw jp kr sg uk
  soco-ctl uuid <UUID>     换成你自己的解锁授权 UUID，并触发重载
  soco-ctl conf            看配置（脱敏）与 systemd unit

等价关系（你以前的习惯 → 现在怎么做）：
  以前 "soga 进 soga"  →  现在 soco-ctl status / log / restart
  改配置               →  现在直接编辑 /etc/soco/soco.conf，然后 soco-ctl restart
  看节点是否在转发      →  现在 soco-ctl verify
EOF
}

case "${1:-status}" in
  status) shift || true; cmd_status ;;
  log)    shift; cmd_log "${1:-60}" ;;
  restart) cmd_restart ;;
  verify) cmd_verify ;;
  area)   shift; cmd_area "${1:-}" ;;
  uuid)   shift; cmd_uuid "${1:-}" ;;
  conf)   cmd_conf ;;
  help|-h|--help) cmd_help ;;
  *) cmd_help; exit 2 ;;
esac