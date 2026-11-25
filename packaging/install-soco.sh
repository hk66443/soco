#!/bin/bash
# soco 安装 / 更新脚本（soga 兼容布局）
#
# 用法：
#   install-soco.sh [--bin <本地文件|URL>] [--lib <本地文件|URL>] [--no-restart] [--with-watchdog]
#
# 行为：
#   1. 安装 /usr/local/soco/soco 与 libsoco.so（缺失时必填 --bin/--lib）；
#   2. 写入 systemd 单元：soco.service（主实例，无 -c）+ soco@.service（多实例模板）；
#   3. 写入管理脚本 /usr/bin/soco；
#   4. 配置目录保持 soga 布局：/etc/soga/soga.conf、/etc/soga/routes.toml、/etc/soga/{blockList,whiteList,dns.yml,geoip.dat,geosite.dat}；
#      若只有 /etc/soco/soco.conf，会复制成 /etc/soga/soga.conf（已有则不动）；
#   5. 多实例目录 /etc/soga/instances/<name>/ 用于隔离日志与缓存。
set -u

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[0;33m'; PLAIN='\033[0m'
ok()   { echo -e "${GREEN}$*${PLAIN}"; }
warn() { echo -e "${YELLOW}$*${PLAIN}"; }
err()  { echo -e "${RED}$*${PLAIN}" >&2; }

BIN_SRC=""; LIB_SRC=""; NO_RESTART=0; WITH_WATCHDOG=0
while [[ $# -gt 0 ]]; do
    case "$1" in
        --bin) BIN_SRC="${2:-}"; shift 2 ;;
        --lib) LIB_SRC="${2:-}"; shift 2 ;;
        --no-restart) NO_RESTART=1; shift ;;
        --with-watchdog) WITH_WATCHDOG=1; shift ;;
        *) err "未知参数: $1"; exit 1 ;;
    esac
done

[[ $EUID -eq 0 ]] || { err "必须用 root 运行"; exit 1; }

DST_DIR=/usr/local/soco
BIN=$DST_DIR/soco
LIB=$DST_DIR/libsoco.so
CONF_DIR=/etc/soga
UNIT_DIR=/etc/systemd/system
SELF_DIR=$(cd "$(dirname "$0")" && pwd)

fetch() { # fetch <src> <dst>
    local src="$1" dst="$2"
    case "$src" in
        http://*|https://*) curl -fsSL "$src" -o "$dst" || return 1 ;;
        *) cp -f "$src" "$dst" || return 1 ;;
    esac
}

install_unit_from() { # install_unit_from <file> <name>
    local src="$1" dst="$2"
    if [[ -f "$src" ]]; then
        install -m644 "$src" "$UNIT_DIR/$dst"
    else
        err "缺少 unit 模板：$src（请与 install-soco.sh 放在同一目录）"; exit 1
    fi
}

mkdir -p "$DST_DIR" "$CONF_DIR" "$CONF_DIR/instances"

# 1. 二进制
if [[ -n "$BIN_SRC" ]]; then
    tmp=$(mktemp); fetch "$BIN_SRC" "$tmp" || { err "获取 soco 失败: $BIN_SRC"; exit 1; }
    chmod +x "$tmp"
    "$tmp" -v >/dev/null 2>&1 || { err "新 soco 无法执行（-v 失败），可能是架构不匹配"; exit 1; }
    if [[ -x "$BIN" ]]; then cp -a "$BIN" "$BIN.bak.$(date +%Y%m%d%H%M%S)"; fi
    install -m755 "$tmp" "$BIN"; rm -f "$tmp"
    ok "已安装 $("$BIN" -v): $BIN"
elif [[ -x "$BIN" ]]; then
    ok "已存在 $BIN（$("$BIN" -v 2>/dev/null | head -n1)），跳过二进制安装"
else
    err "缺少 $BIN，请用 --bin <文件|URL> 指定"; exit 1
fi

# 2. 适配层
if [[ -n "$LIB_SRC" ]]; then
    tmp=$(mktemp); fetch "$LIB_SRC" "$tmp" || { err "获取 libsoco.so 失败: $LIB_SRC"; exit 1; }
    if [[ -f "$LIB" ]]; then cp -a "$LIB" "$LIB.bak.$(date +%Y%m%d%H%M%S)"; fi
    install -m700 "$tmp" "$LIB"; rm -f "$tmp"
    ok "已安装适配层: $LIB"
elif [[ -f "$LIB" ]]; then
    ok "已存在适配层: $LIB"
else
    err "缺少 $LIB，请用 --lib <文件|URL> 指定"; exit 1
fi

# 3. 配置迁移（只补缺，不覆盖）
if [[ ! -f "$CONF_DIR/soga.conf" ]]; then
    if [[ -f /etc/soco/soco.conf ]]; then
        cp -a /etc/soco/soco.conf "$CONF_DIR/soga.conf"
        chmod 600 "$CONF_DIR/soga.conf"
        ok "已把 /etc/soco/soco.conf 复制为 $CONF_DIR/soga.conf"
    else
        warn "没有找到 soga.conf；请先放一份配置到 $CONF_DIR/soga.conf"
    fi
else
    ok "保留现有配置: $CONF_DIR/soga.conf"
fi

# 4. 流媒体与基础数据（缺失时从 /etc/soco 或工程模板补齐）
for f in routes.toml blockList whiteList dns.yml geoip.dat geosite.dat; do
    if [[ ! -f "$CONF_DIR/$f" ]]; then
        if [[ -f "/etc/soco/$f" ]]; then cp -a "/etc/soco/$f" "$CONF_DIR/$f"; ok "补齐 $CONF_DIR/$f"; fi
    fi
done

# 5. systemd 单元
install_unit_from "$SELF_DIR/soco.service" soco.service
install_unit_from "$SELF_DIR/soco@.service" soco@.service
[[ -f "$SELF_DIR/soco-multi.sh" ]] || { err "缺少 soco-multi.sh"; exit 1; }
install -m755 "$SELF_DIR/soco-multi.sh" /usr/bin/soco
systemctl daemon-reload
ok "systemd: soco.service / soco@.service 已就绪，管理脚本 /usr/bin/soco"

# 6. 主实例
if systemctl list-unit-files | grep -q '^soco\.service'; then
    systemctl enable soco >/dev/null 2>&1 || true
fi
if [[ "$NO_RESTART" -eq 0 ]]; then
    if systemctl is-active soco >/dev/null 2>&1; then
        systemctl restart soco
        sleep 3
        ok "soco 状态: $(systemctl is-active soco)"
    else
        systemctl enable --now soco >/dev/null 2>&1 || true
        sleep 3
        ok "soco 状态: $(systemctl is-active soco || echo inactive)"
    fi
else
    warn "--no-restart：单元已更新，下次重启生效（当前进程仍按旧配置运行）"
fi

# 7. nfu / soga 生态兼容：soga 命令 + routes 守卫（幂等，无副作用）
if [[ -f "$SELF_DIR/soga-compat.sh" ]]; then
    install -m755 "$SELF_DIR/soga-compat.sh" /usr/bin/soga
    ok "已安装 soga 兼容入口: /usr/bin/soga -> soco"
fi
if [[ -f "$SELF_DIR/routes-guard.py" && -f "$SELF_DIR/soco-routes-guard.path" ]]; then
    install -m755 "$SELF_DIR/routes-guard.py" "$DST_DIR/routes-guard.py"
    install -m644 "$SELF_DIR/soco-routes-guard.service" "$UNIT_DIR/soco-routes-guard.service"
    install -m644 "$SELF_DIR/soco-routes-guard.path" "$UNIT_DIR/soco-routes-guard.path"
    systemctl daemon-reload
    systemctl enable --now soco-routes-guard.path >/dev/null 2>&1 || true
    ok "已启用路由守卫: soco-routes-guard.path（nfu 覆盖 routes.toml 后自动补回 Netflix/OpenAI 分流）"
fi

# 8. watchdog（可选，需 --with-watchdog 且已有 sing-box-probe）
if [[ "$WITH_WATCHDOG" -eq 1 ]]; then
    if [[ -x "$DST_DIR/sing-box-probe" && -f "$SELF_DIR/soco-watchdog.py" ]]; then
        install -m755 "$SELF_DIR/soco-watchdog.py" "$DST_DIR/soco-watchdog.py"
        install -m644 "$SELF_DIR/soco-watchdog.service" "$UNIT_DIR/soco-watchdog.service"
        systemctl daemon-reload
        systemctl enable --now soco-watchdog.service >/dev/null 2>&1 || true
        ok "已启用 watchdog: soco-watchdog.service（真实握手探活，连续 3 次失败重启 soco）"
    else
        warn "--with-watchdog：缺少 $DST_DIR/sing-box-probe 或 soco-watchdog.py，跳过"
    fi
fi

echo
soco list