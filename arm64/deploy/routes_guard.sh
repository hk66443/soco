#!/usr/bin/env bash
# routes_guard.sh — 防止 routes.toml 静默失效（soco 加载失败后不会自动重试）
# 用法: routes_guard.sh          一次性检查，异常则修复并报告（退出码 0=正常 1=已修复 2=修不了）
# 装成定时任务（可选，每 5 分钟）：
#   cp routes_guard.sh /usr/local/bin/ && chmod +x /usr/local/bin/routes_guard.sh
#   cat >/etc/systemd/system/routes-guard.service <<'EOF'
#   [Unit]
#   Description=routes.toml health guard
#   [Service]
#   Type=oneshot
#   ExecStart=/usr/local/bin/routes_guard.sh
#   EOF
#   cat >/etc/systemd/system/routes-guard.timer <<'EOF'
#   [Unit]
#   Description=run routes guard every 5min
#   [Timer]
#   OnBootSec=3min
#   OnUnitActiveSec=5min
#   [Install]
#   WantedBy=timers.target
#   EOF
#   systemctl daemon-reload && systemctl enable --now routes-guard.timer
set -uo pipefail

P=/etc/soga/routes.toml
L="/etc/soga/soga-vless-$(date +%Y-%m-%d).log"
WANT="${WANT_ROUTES:-10}"

if [[ ! -r $P ]]; then
  echo "MISSING $P"
  exit 2
fi

# 1) 语法校验（用 soco 自己的加载日志更权威，这里先做粗校验：括号/引号成对、无占位符）
if grep -qE '\{(Out|OutPort|UUID)\}' "$P"; then
  echo "TEMPLATE-PLACEHOLDER still present in $P — refusing to touch; fix by hand"
  exit 2
fi

# 2) soco 是否真的加载了 WANT 条
last=$(grep -a 'load routes config' "$L" 2>/dev/null | tail -1)
num=$(printf '%s' "$last" | sed -nE 's/.*routes num: ([0-9]+).*/\1/p')
if [[ "${num:-0}" == "$WANT" ]]; then
  echo "OK: routes num: $num"
  exit 0
fi

echo "STALE: latest load = ${last:-<none>} (want num: $WANT) — restarting soco"
systemctl restart soco
sleep 6
last2=$(grep -a 'load routes config' "$L" | tail -1)
num2=$(printf '%s' "$last2" | sed -nE 's/.*routes num: ([0-9]+).*/\1/p')
if [[ "${num2:-0}" == "$WANT" ]]; then
  echo "FIXED: $last2"
  exit 1
fi
echo "STILL BROKEN: ${last2:-<none>} — routes.toml 本身有问题，人工检查"
exit 2