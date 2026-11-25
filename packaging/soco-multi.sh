#!/bin/bash
# soco 多实例管理脚本（对齐 soga-cmd 的命令集，配置目录沿用 soga 的 /etc/soga）
#
# 布局：
#   /usr/local/soco/soco                 主程序（soga 2.18.1 后端 + soco 适配层）
#   /usr/local/soco/libsoco.so           LD_PRELOAD 适配层
#   /etc/soga/soga.conf                  主实例配置（soco.service / 无 -c 时的默认路径）
#   /etc/soga/<name>.conf                其它实例配置（soco@<name>.service -c 指向它）
#   /etc/soga/instances/<name>/          实例私有运行目录（log_file_dir / ip_user_cache_save_dir / access_log_dir）
#   /etc/soga/routes.toml                流媒体路由（所有实例共享，nfu / soga 工具直接改这里）
#   /etc/systemd/system/soco@.service    实例模板
#
# 实例隔离：每个实例独立 log_file_dir、ip_user_cache_save_dir、access_log_dir，
# 避免同机多实例共用 /etc/soga 下的日志与 IP-用户缓存文件互相覆盖。
set -u

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[0;33m'; PLAIN='\033[0m'
SOCo_BIN="${SOCO_BIN:-/usr/local/soco/soco}"
SOCo_LIB="${SOCO_LIB:-/usr/local/soco/libsoco.so}"
CONF_DIR="${SOCO_CONF_DIR:-/etc/soga}"
INST_DIR="$CONF_DIR/instances"
UNIT_DIR="/etc/systemd/system"
MAIN_CONF="$CONF_DIR/soga.conf"
TEMPLATE_UNIT="$UNIT_DIR/soco@.service"

msg()  { echo -e "$*"; }
ok()   { echo -e "${GREEN}$*${PLAIN}"; }
warn() { echo -e "${YELLOW}$*${PLAIN}"; }
err()  { echo -e "${RED}$*${PLAIN}" >&2; }

need_root() { [[ $EUID -eq 0 ]] || { err "必须用 root 运行"; exit 1; }; }

names() { ls -1 "$CONF_DIR" 2>/dev/null | sed -n 's/^\(.*\)\.conf$/\1/p' | grep -Ev '^(soga|soco)$' ; }

conf_of() { echo "$CONF_DIR/$1.conf"; }

ensure_layout() {
    mkdir -p "$CONF_DIR" "$INST_DIR"
    [[ -f "$MAIN_CONF" ]] || { err "缺少主配置 $MAIN_CONF（先装好 soga/soco 配置）"; exit 1; }
    [[ -x "$SOCo_BIN" ]] || { err "缺少主程序 $SOCo_BIN"; exit 1; }
    if [[ ! -f "$TEMPLATE_UNIT" ]]; then
        err "缺少实例模板 $TEMPLATE_UNIT（先跑 install-soco.sh）"; exit 1
    fi
}

set_kv() { # set_kv <file> <key> <value>
    local f="$1" k="$2" v="$3"
    local esc
    esc=$(printf '%s\n' "$v" | sed -e 's/[\/&|]/\\&/g')
    if grep -Eq "^[[:space:]]*${k}[[:space:]]*=" "$f"; then
        sed -i -E "s|^[[:space:]]*${k}[[:space:]]*=.*|${k}=${v}|" "$f"
    else
        printf '%s=%s\n' "$k" "$v" >> "$f"
    fi
}

get_kv() { # get_kv <file> <key>
    sed -n -E "s/^[[:space:]]*$2[[:space:]]*=[[:space:]]*//p" "$1" | tail -n1
}

isolate_conf() { # isolate_conf <name> <file>
    local name="$1" f="$2" d="$INST_DIR/$1"
    mkdir -p "$d/access_log"
    set_kv "$f" log_file_dir "$d/"
    set_kv "$f" ip_user_cache_save_dir "$d/"
    set_kv "$f" access_log_dir "$d/access_log"
}

cmd_list() {
    ensure_layout
    printf '%-16s %-12s %-10s %s\n' NAME STATUS RESTARTS LOGDIR
    for n in $(names); do
        local st nu
        st=$(systemctl is-active "soco@$n" 2>/dev/null || true)
        nu=$(systemctl show "soco@$n" -p NRestarts --value 2>/dev/null || echo '?')
        printf '%-16s %-12s %-10s %s\n' "$n" "${st:-unknown}" "$nu" "$(get_kv "$(conf_of "$n")" log_file_dir)"
    done
    local st
    st=$(systemctl is-active soco 2>/dev/null || true)
    [[ -n "$st" ]] && printf '%-16s %-12s %-10s %s\n' '(main)' "$st" "$(systemctl show soco -p NRestarts --value 2>/dev/null)" "$(get_kv "$MAIN_CONF" log_file_dir || echo /etc/soga/)"
}

cmd_status() {
    local name="${1:-}"
    if [[ -z "$name" ]]; then
        systemctl status soco --no-pager
    else
        systemctl status "soco@$name" --no-pager
    fi
}

cmd_new() {
    ensure_layout
    local name="${1:-}"; shift || true
    [[ -n "$name" ]] || { err "用法: soco new <name> [k=v ...]"; exit 1; }
    [[ "$name" =~ ^[A-Za-z0-9_-]+$ ]] || { err "实例名只能用字母数字 _ -"; exit 1; }
    local f; f=$(conf_of "$name")
    if [[ -f "$f" ]]; then err "实例 $name 已存在：$f"; exit 1; fi
    cp -a "$MAIN_CONF" "$f"
    isolate_conf "$name" "$f"
    for kv in "$@"; do
        case "$kv" in *=*) set_kv "$f" "${kv%%=*}" "${kv#*=}" ;; *) warn "忽略无效参数: $kv" ;; esac
    done
    chmod 600 "$f"
    systemctl daemon-reload
    systemctl enable --now "soco@$name" >/dev/null 2>&1
    sleep 2
    local st; st=$(systemctl is-active "soco@$name" 2>/dev/null || true)
    if [[ "$st" == "active" ]]; then
        ok "实例 $name 已创建并启动：$f"
        ok "  私有目录: $INST_DIR/$name/"
        ok "  日志:     $INST_DIR/$name/"
    else
        warn "实例 $name 已创建但未进入 active（$st），看：soco log $name"
    fi
    warn "面板下发的服务端口必须与已有实例/进程不冲突（ss -lntp 自查）"
}

cmd_remove() {
    ensure_layout
    [[ $# -gt 0 ]] || { err "用法: soco remove <name> [name...]"; exit 1; }
    for name in "$@"; do
        local f; f=$(conf_of "$name")
        [[ -f "$f" ]] || { warn "实例不存在: $name"; continue; }
        systemctl disable --now "soco@$name" >/dev/null 2>&1
        rm -f "$f"
        warn "配置已删：$f（私有目录 $INST_DIR/$name 保留，手动确认后再删）"
    done
    systemctl daemon-reload
}

cmd_rename() {
    ensure_layout
    local old="${1:-}" new="${2:-}"
    [[ -n "$old" && -n "$new" ]] || { err "用法: soco rename <old> <new>"; exit 1; }
    [[ -f "$(conf_of "$old")" ]] || { err "实例不存在: $old"; exit 1; }
    [[ -f "$(conf_of "$new")" ]] && { err "目标实例已存在: $new"; exit 1; }
    systemctl disable --now "soco@$old" >/dev/null 2>&1
    mv "$(conf_of "$old")" "$(conf_of "$new")"
    [[ -d "$INST_DIR/$old" ]] && mv "$INST_DIR/$old" "$INST_DIR/$new"
    set_kv "$(conf_of "$new")" log_file_dir "$INST_DIR/$new/"
    set_kv "$(conf_of "$new")" ip_user_cache_save_dir "$INST_DIR/$new/"
    set_kv "$(conf_of "$new")" access_log_dir "$INST_DIR/$new/access_log"
    systemctl enable --now "soco@$new" >/dev/null 2>&1
    ok "已重命名 $old -> $new"
}

cmd_ctl() { # start|stop|restart|enable|disable
    local act="$1" name="${2:-}"
    ensure_layout
    if [[ -z "$name" ]]; then
        if [[ "$act" == "stop" || "$act" == "restart" ]]; then
            systemctl "$act" soco >/dev/null 2>&1 || true
        fi
        for n in $(names); do systemctl "$act" "soco@$n" >/dev/null 2>&1 || true; done
        ok "已对所有实例执行 $act"
        return
    fi
    [[ -f "$(conf_of "$name")" ]] || { err "实例不存在: $name"; exit 1; }
    systemctl "$act" "soco@$name"
}

cmd_log() {
    ensure_layout
    local name="${1:-}"; shift || true
    local fflag=""
    for a in "$@"; do [[ "$a" == "-f" ]] && fflag="-f"; done
    if [[ -z "$name" || "$name" == "-f" ]]; then
        journalctl -u soco -n 1000 $fflag
        return
    fi
    [[ -f "$(conf_of "$name")" ]] || { err "实例不存在: $name"; exit 1; }
    local d; d=$(get_kv "$(conf_of "$name")" log_file_dir)
    local logfile
    logfile=$(ls -1t "$d"/soga-*.log 2>/dev/null | head -n1 || true)
    if [[ -n "$logfile" ]]; then
        tail -n 1000 $fflag "$logfile"
    else
        journalctl -u "soco@$name" -n 1000 $fflag
    fi
}

cmd_config() {
    ensure_layout
    local name="${1:-}"; shift || true
    if [[ -z "$name" ]]; then
        msg "# $MAIN_CONF"; cat "$MAIN_CONF"; return
    fi
    local f; f=$(conf_of "$name")
    [[ -f "$f" ]] || { err "实例不存在: $name"; exit 1; }
    if [[ $# -eq 0 ]]; then cat "$f"; return; fi
    for kv in "$@"; do
        case "$kv" in
            *=*) set_kv "$f" "${kv%%=*}" "${kv#*=}"; ok "已写入 $kv" ;;
            *) warn "忽略: $kv" ;;
        esac
    done
    systemctl restart "soco@$name" >/dev/null 2>&1 && ok "已重启 soco@$name"
}

cmd_update() {
    ensure_layout
    local src="${1:-}"
    [[ -n "$src" ]] || { err "用法: soco update <本地文件|http(s)://...> [libsoco路径]"; exit 1; }
    local tmp; tmp=$(mktemp -d)
    case "$src" in
        http://*|https://*) curl -fsSL "$src" -o "$tmp/soco" || { err "下载失败"; exit 1; } ;;
        *) cp -f "$src" "$tmp/soco" ;;
    esac
    chmod +x "$tmp/soco"
    "$tmp/soco" -v >/dev/null 2>&1 || { err "新二进制无法运行（-v 失败）"; exit 1; }
    local ts; ts=$(date +%Y%m%d%H%M%S)
    cp -a "$SOCo_BIN" "$SOCo_BIN.bak.$ts"
    install -m755 "$tmp/soco" "$SOCo_BIN"
    if [[ -n "${2:-}" && -f "${2}" ]]; then
        cp -a "$SOCo_LIB" "$SOCo_LIB.bak.$ts"
        install -m700 "$2" "$SOCo_LIB"
    fi
    systemctl restart soco >/dev/null 2>&1 || true
    for n in $(names); do systemctl restart "soco@$n" >/dev/null 2>&1 || true; done
    ok "已更新 $SOCo_BIN（备份 .bak.$ts）并重启全部实例"
}

cmd_uninstall() {
    warn "这会停止并禁用所有 soco 实例，删除 /usr/local/soco 与 systemd 单元；/etc/soga 配置保留。"
    read -r -p "确认卸载？输入 yes: " a
    [[ "$a" == "yes" ]] || { warn "已取消"; return; }
    systemctl disable --now soco >/dev/null 2>&1 || true
    for n in $(names); do systemctl disable --now "soco@$n" >/dev/null 2>&1 || true; done
    rm -f "$UNIT_DIR/soco.service" "$UNIT_DIR/soco@.service" /usr/bin/soco
    rm -rf /usr/local/soco
    systemctl daemon-reload
    ok "已卸载；/etc/soga 下的配置与实例目录未删除"
}

menu() {
    msg "soco 管理菜单"
    msg "  soco list                          - 列出实例及状态"
    msg "  soco new <name> [k=v ...]          - 新建实例"
    msg "  soco remove <name> [name...]       - 删除实例"
    msg "  soco rename <old> <new>            - 重命名实例"
    msg "  soco start|stop|restart [name]     - 启停实例（省略 name = 全部）"
    msg "  soco status [name]                 - 看 systemd 状态"
    msg "  soco enable|disable [name]         - 开机自启"
    msg "  soco log [name] [-f]               - 看实例日志"
    msg "  soco config [name] [k=v ...]       - 读/改实例配置"
    msg "  soco update <文件|URL> [lib]       - 更新主程序/适配层"
    msg "  soco uninstall                     - 卸载"
    msg "  soco version                       - 版本"
}

cmd_version() { "$SOCo_BIN" -v 2>/dev/null | head -n1; }

main() {
    need_root
    local sub="${1:-}"; shift || true
    case "$sub" in
        list|ls)        cmd_list ;;
        new|add)        cmd_new "$@" ;;
        remove|rm|del)  cmd_remove "$@" ;;
        rename|mv)      cmd_rename "$@" ;;
        start|stop|restart|enable|disable) cmd_ctl "$sub" "$@" ;;
        status)         cmd_status "$@" ;;
        log|logs)       cmd_log "$@" ;;
        config|conf)    cmd_config "$@" ;;
        update|upgrade) cmd_update "$@" ;;
        uninstall)      cmd_uninstall ;;
        version|v)      cmd_version ;;
        ''|menu|help|-h|--help) menu ;;
        *) menu ;;
    esac
}

main "$@"