#!/usr/bin/env bash
# shard_add.sh — 同机多节点分片：再起一个 soco 实例，把用户摊到 ≤88/节点
#
# 背景：ARM 侧实测「面板用户数 > 88 → 认证通过但不转发」，单实例无法承载 100 用户。
#       分片是零改动、已验证可行的方案：每个实例服务一个 node_id，各自 ≤88 用户。
#
# 用法: shard_add.sh <node_id> <port> [webapi_key] [soga_key]
#   node_id / port 必填；两个 key 省略时从 /etc/soco/soco.conf 继承
#   webapi_url 也继承。
#
# 示例:
#   shard_add.sh 645 50001
#   → /etc/soco/soco-645.conf + soco-645.service + 立即启动
set -euo pipefail

NODE=${1:?usage: shard_add.sh <node_id> <port> [webapi_key] [soga_key]}
PORT=${2:?usage: shard_add.sh <node_id> <port> [webapi_key] [soga_key]}
BASE=/etc/soco/soco.conf
[[ -r $BASE ]] || { echo "缺少 $BASE" >&2; exit 1; }

get() { grep -E "^$1=" "$BASE" | head -1 | cut -d= -f2-; }

WEBAPI_URL=$(get webapi_url)
WEBAPI_KEY=${3:-$(get webapi_key)}
SOGA_KEY=${4:-$(get soga_key)}

CONF="/etc/soco/soco-${NODE}.conf"
UNIT="/etc/systemd/system/soco-${NODE}.service"

cat > "$CONF" <<EOF
# 分片实例 node ${NODE} / port ${PORT}
type=xboard
server_type=vless
node_id=${NODE}
soga_key=${SOGA_KEY}
api=webapi
webapi_url=${WEBAPI_URL}
webapi_key=${WEBAPI_KEY}
cert_file=
key_file=
cert_mode=
cert_domain=
proxy_protocol=false
udp_proxy_protocol=false
user_conn_limit=0
user_speed_limit=0
user_tcp_limit=0
node_speed_limit=0
check_interval=60
submit_interval=60
forbidden_bit_torrent=true
log_level=debug
EOF
chmod 600 "$CONF"

cat > "$UNIT" <<EOF
[Unit]
Description=soco shard node ${NODE} (port ${PORT})
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
Environment=LD_PRELOAD=/usr/local/soco/libsoco.so
ExecStart=/usr/local/soco/soco -c ${CONF}
Restart=always
RestartSec=5
LimitNOFILE=1048576
LimitNPROC=1048576

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable --now "soco-${NODE}.service"

sleep 6
echo "=== soco-${NODE}.service ==="
systemctl show "soco-${NODE}.service" -p ActiveState,MainPID,NRestarts --value 2>&1 | tr '\n' ' '
echo
ss -lnt 2>/dev/null | grep ":${PORT} " || echo "!! :${PORT} 没有监听"
echo "提示：面板里该 node 的端口要与此处 ${PORT} 一致；每节点挂 ≤88 个用户。"