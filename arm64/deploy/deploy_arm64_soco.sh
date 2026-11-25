#!/bin/bash
# ============================================================================
# deploy_arm64_soco.sh —— 在「全新 arm64 服务器」上部署 soco
#   soco = soga v2.18.1 (arm64) + 43 字节破解 + LD_PRELOAD 面板适配层
#
# 用法（在目标机上，root）：
#   NODE_ID=644 WEBAPI_KEY=xxxx SOGA_KEY=xxxx ./deploy_arm64_soco.sh
#   或先编辑下面 4 个变量再直接跑
#   加 -n 只做预检不落地：./deploy_arm64_soco.sh -n
#
# 需要与本脚本同目录下（或 ART_DIR 指定）有两个文件：
#   soco            (sha256 37332960…73f1d3a，大小 91634064)
#   libsoco.so      (sha256 f5fc39df…f83293a，大小 19336)
# 它们来自工程包 arm64/bin/soga-arm64.crack-soga10 与 arm64/bin/libsoco-arm64.so
# ============================================================================
set -uo pipefail

NODE_ID="${NODE_ID:-}"
PANEL_URL="${PANEL_URL:-https://<REDACTED>}"
WEBAPI_KEY="${WEBAPI_KEY:-}"
SOGA_KEY="${SOGA_KEY:-}"
COUNTRY_LABEL="${COUNTRY_LABEL:-}"          # 仅用于打印提示，可留空
ART_DIR="${ART_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}"

BIN_SHA="3733296060ddb4047495ea0eb67e0449eee07e8ce375a7e969b28d36773f1d3a"
SO_SHA="f5fc39df4f988cb4a8eb4c683f914a07d5836b1807720aab7b010736cf83293a"

BIN_DST=/usr/local/soco/soco
SO_DST=/usr/local/soco/libsoco.so
CONF=/etc/soco/soco.conf
UNIT=/etc/systemd/system/soco.service

DRY=0
[ "${1:-}" = "-n" ] && DRY=1

ok()   { printf '  \033[32m✔\033[0m %s\n' "$*"; }
bad()  { printf '  \033[31m✘\033[0m %s\n' "$*"; }
info() { printf '  · %s\n' "$*"; }
die()  { printf '\n\033[31m[停止]\033[0m %s\n' "$*" >&2; exit 1; }

echo "=============================================="
echo " soco arm64 部署  (node_id=${NODE_ID:-<未填>})"
echo "=============================================="

# ---------- 1. 预检 ----------
echo "[1/7] 预检"
[ "$(id -u)" = 0 ] || die "必须 root 运行"
ARCH=$(uname -m)
[ "$ARCH" = "aarch64" ] || die "本机架构是 $ARCH，不是 aarch64（amd64 请用 amd64/ 那套，做法不同）"
ok "架构 $ARCH"
[ -n "$NODE_ID" ]    || die "NODE_ID 未填（面板里该节点的 node_id）"
[ -n "$WEBAPI_KEY" ] || die "WEBAPI_KEY 未填（面板给节点的 webapi_key）"
[ -n "$SOGA_KEY" ]   || die "SOGA_KEY 未填（面板里的 soga_key）"
ok "参数齐备"

F_SRC="$ART_DIR/soco";        [ -f "$F_SRC" ] || F_SRC="$ART_DIR/soga-arm64.crack-soga10"
S_SRC="$ART_DIR/libsoco.so";  [ -f "$S_SRC" ] || S_SRC="$ART_DIR/libsoco-arm64.so"
[ -f "$F_SRC" ] || die "找不到 soco 二进制（在 $ART_DIR 下找不到 soco / soga-arm64.crack-soga10）"
[ -f "$S_SRC" ] || die "找不到适配层（在 $ART_DIR 下找不到 libsoco.so / libsoco-arm64.so）"

H=$(sha256sum "$F_SRC" | cut -d' ' -f1)
if [ "$H" = "$BIN_SHA" ]; then ok "soco 二进制 hash 正确"; else
  die "soco hash 不符：$H
  期望 $BIN_SHA
  注意：不能用 1b280c88…（98区域/174字节那版，认证能过但从不 dial）"
fi
H=$(sha256sum "$S_SRC" | cut -d' ' -f1)
[ "$H" = "$SO_SHA" ] && ok "适配层 hash 正确" || die "libsoco.so hash 不符：$H（期望 $SO_SHA）"

# ---------- 2. 依赖 ----------
echo "[2/7] 依赖 (libcurl4 / libjson-c5 / ca-certificates)"
MISSING_LIBS=$(ldd "$S_SRC" 2>/dev/null | awk '/not found/{print $1}' | tr '\n' ' ')
if [ -z "$MISSING_LIBS" ]; then
  ok "适配层动态库可解析（libcurl / libjson-c / libc）"
else
  bad "缺动态库: $MISSING_LIBS"
  if [ "$DRY" = 1 ]; then
    info "dry-run 不安装；请先: apt-get install -y libcurl4 libjson-c5 ca-certificates"
  else
    apt-get update -qq && DEBIAN_FRONTEND=noninteractive apt-get install -y libcurl4 libjson-c5 ca-certificates >/dev/null
    MISSING_LIBS=$(ldd "$S_SRC" 2>/dev/null | awk '/not found/{print $1}' | tr '\n' ' ')
    [ -z "$MISSING_LIBS" ] && ok "依赖已补齐" || die "装完仍缺: $MISSING_LIBS（装 libcurl4 + libjson-c5 后重试）"
  fi
fi

if [ "$DRY" = 1 ]; then
  echo; info "dry-run 结束，未做任何改动"; exit 0
fi

# ---------- 3. 目录与文件 ----------
echo "[3/7] 安装文件"
install -d -m 0755 /usr/local/soco /etc/soco /etc/soga
install -m 0700 "$F_SRC" "$BIN_DST"
install -m 0700 "$S_SRC" "$SO_DST"
ok "$BIN_DST  (0700)  $(sha256sum "$BIN_DST" | cut -c1-16)"
ok "$SO_DST  (0700)  $(sha256sum "$SO_DST" | cut -c1-16)"

# 主程序运行时会读取 /etc/soga/ 下的这几个文件（缺失会启动告警/失败），按官方包原样补齐
mk_if_absent() {  # $1=路径  $2=内容
  if [ -f "$1" ]; then info "保留已有 $1"; else printf '%s' "$2" > "$1"; ok "创建 $1"; fi
}
mk_if_absent /etc/soga/blockList  '# 每行一个审计规则
'
mk_if_absent /etc/soga/whiteList  '# 每行一个规则
'
mk_if_absent /etc/soga/dns.yml    '# dns配置
'
mk_if_absent /etc/soga/routes.toml '# 出站路由配置，默认本机出站，无需配置
'

# ---------- 4. 配置 ----------
echo "[4/7] 写 $CONF"
if [ -f "$CONF" ]; then cp -a "$CONF" "$CONF.bak.$(date -u +%Y%m%dT%H%M%SZ)"; ok "已备份旧配置"; fi
umask 077
cat > "$CONF" <<EOF
# soco 面板配置（type=xboard）
type=xboard
server_type=vless
node_id=${NODE_ID}
soga_key=${SOGA_KEY}

# 面板对接（二选一，用 webapi）
api=webapi
webapi_url=${PANEL_URL}
webapi_key=${WEBAPI_KEY}

# db 方式留空
db_host=
db_port=
db_name=
db_user=
db_password=

# 证书（reality 不需要，由面板下发）
cert_file=
key_file=
cert_mode=
cert_domain=
cert_key_length=ec-256
dns_provider=

# 代理协议
proxy_protocol=false
udp_proxy_protocol=false

# 全局 IP 限制（需 Redis 8.0+）
redis_ip_limit_enable=false
redis_ip_limit_addr=
redis_ip_limit_password=
redis_ip_limit_db=0
redis_ip_limit_tls=false
redis_ip_limit_expiry=60

# 动态限速
dy_limit_enable=false
dy_limit_duration=
dy_limit_trigger_time=60
dy_limit_trigger_speed=100
dy_limit_speed=30
dy_limit_time=600
dy_limit_white_user_id=

# 其它
user_conn_limit=0
user_speed_limit=0
user_tcp_limit=0
node_speed_limit=0

check_interval=60
submit_interval=60
forbidden_bit_torrent=true
log_level=debug
EOF
chmod 0600 "$CONF"
ok "$CONF (0600)"

# ---------- 5. systemd ----------
echo "[5/7] 写 $UNIT"
cat > "$UNIT" <<'EOF'
[Unit]
Description=soco 0.1.0 (soga backend with panel adapter)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
Environment=LD_PRELOAD=/usr/local/soco/libsoco.so
ExecStart=/usr/local/soco/soco -c /etc/soco/soco.conf
Restart=always
RestartSec=5
LimitNOFILE=1048576
LimitNPROC=1048576

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable soco >/dev/null 2>&1
ok "unit 已写并设为开机自启"

# ---------- 6. 启动 ----------
echo "[6/7] 启动"
systemctl restart soco
sleep 8
systemctl is-active --quiet soco && ok "服务 active" || { systemctl --no-pager -l status soco | tail -20; die "服务没起来"; }

PID=$(systemctl show soco -p MainPID --value)
[ -n "$PID" ] && [ "$PID" != "0" ] && ok "PID=$PID  exe=$(readlink /proc/$PID/exe)"
grep -q libsoco "/proc/$PID/maps" 2>/dev/null && ok "适配层已加载 (LD_PRELOAD 生效)" \
  || bad "适配层未加载 —— 检查 unit 里的 Environment=LD_PRELOAD"

# ---------- 7. 验证 ----------
echo "[7/7] 验证"
LOG="/etc/soga/soga-vless-$(date +%Y-%m-%d).log"
echo
echo "  --- 面板下发的配置 ---"
CFG=$(curl -s --max-time 15 "$PANEL_URL/api/v1/server/UniProxy/config?node_id=${NODE_ID}&node_type=vless&token=<REDACTED>")
echo "$CFG" | head -c 600; echo
case "$CFG" in
  *server_port*) ok "面板 config 接口返回正常" ;;
  *) bad "面板 config 接口异常 —— 检查 node_id / webapi_key / node_type 是否为 vless" ;;
esac

echo
echo "  --- 用户拉取 ---"
if grep -q "add user:" "$LOG" 2>/dev/null || journalctl -u soco --no-pager -n 40 2>/dev/null | grep -q "add user:"; then
  N=$(journalctl -u soco --no-pager -n 80 2>/dev/null | grep -c "add user:")
  ok "已加载用户（日志里 add user 条目 $N 条）"
else
  bad "没看到 add user —— 面板该节点下没有用户，或 API 不通"
fi
journalctl -u soco --no-pager -n 60 2>/dev/null | grep -q "native pull_users entry mismatch" \
  && bad "适配层初始化失败：二进制不是配套那份（换回 37332960…）" \
  || ok "适配层初始化正常（无 entry mismatch）"

PORT=$(echo "$CFG" | sed -n 's/.*"server_port":\([0-9]*\).*/\1/p' | head -1)
if [ -n "$PORT" ]; then
  ss -tlnp 2>/dev/null | grep -q ":$PORT " && ok "已在 :$PORT 监听" || bad "端口 $PORT 未监听"
fi

cat <<NEXT

==============================================
 部署完成。接下来必须做「真实握手」验证（只看端口会骗人）
==============================================
 1) 从客户端（sing-box / v2rayN / NekoBox / Shadowrocket）导入节点或订阅，
    连上去后在本机执行：
        curl https://www.cloudflare.com/cdn-cgi/trace
    出口 IP 应等于本机公网 IP，loc/colo 应是对应国家。

 2) 同时在服务器上看日志，必须出现 tcp relay 才算真的转发：
        L=$LOG
        grep 'tcp direct dial' \$L | tail -3
        grep -c 'tcp relay' \$L

 3) 只看到 'user ... access address' 而紧跟 'handle vless end'（没有 dial）
    = 二进制不对（用了 1b280c88 那版），换回 37332960…。

 备注：日志里 'soga key 错误' 每约 10 分钟出现一次是正常的，不影响转发。
NEXT