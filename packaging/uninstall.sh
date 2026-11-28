#!/bin/bash
# soco 卸载脚本（安装为 /usr/bin/soco-uninstall）
#
# 这里只拆「本项目装上去的东西」，而且**只拆自己那几条**：
#   · 停 soco / soco@* / watchdog / licence-sink / sink-redirect / routes-guard；
#   · 删本项目写的 systemd 单元（不动客户自己的单元）；
#   · /etc/hosts 只删本项目的 4 条授权域名（原子写回，中途被杀也不会留空文件）；
#   · nft 只删 ip nat 里的 redir 链与遗留的 ip soco_sink 表，
#     **绝不删整张 ip nat 表**——docker / iptables-nft / 防火墙的 NAT 也在这张表里，
#     早期版本在这里 `nft delete table ip nat`，等于卸载时顺手把同机容器网络打断。
#   · /etc/soga 配置与 instances 目录默认保留（有面板密钥，--purge 才删）。
#
# 用法：soco-uninstall [--purge] [--yes]
set -uo pipefail

PURGE=0
YES=0
for a in "$@"; do
    case "$a" in
        --purge) PURGE=1 ;;
        --yes|-y) YES=1 ;;
        *) echo "用法: $0 [--purge] [--yes]"; exit 2 ;;
    esac
done

[ "$(id -u)" -eq 0 ] || { echo "必须以 root 运行"; exit 1; }

LICENCE_HOSTS="sksjd.vaxilu.com agdfgkdfg.singledance.xyz boiudihsdfk.singledance.xyz sxp7hu5t.cilema.xyz"
UNIT_DIRS="/etc/systemd/system /usr/lib/systemd/system /lib/systemd/system"
BIN_DIR="/usr/local/soco"

echo "=============================================="
echo " soco 卸载"
echo "=============================================="

if [ "$YES" -ne 1 ]; then
    echo ""
    echo "将停止并删除：soco / soco@* / watchdog / licence-sink / sink-redirect / routes-guard"
    echo "将删除：${BIN_DIR}、/usr/bin/soco* 辅助命令、/etc/hosts 里本项目的 4 条授权域名"
    echo "将保留：/etc/soga 配置$( [ "$PURGE" -eq 1 ] && echo '' || echo '（--purge 才删）')"
    printf '确认卸载？输入 yes: '
    read -r ans
    [ "$ans" = "yes" ] || { echo "已取消"; exit 0; }
fi

echo ""
echo "=== 1. 停止并禁用服务 ==="
# 顺序有讲究：soco-watchdog 会把 soco 拉回来，所以先掐 watchdog，再停下游。
# 只碰 LoadState=loaded 的单元（以前对着一堆猜出来的名字 systemctl stop，
# 不存在就刷一屏 "Unit ... not loaded"，看着像卸载失败）。
STOP_ORDER="soco-watchdog soco-routes-guard.path soco-licence-sink soco-sink-redirect soco"
for u in $STOP_ORDER; do
    st="$(systemctl show -p LoadState --value "$u" 2>/dev/null)"
    [ "$st" = "loaded" ] || [ "$st" = "masked" ] || continue
    systemctl stop "$u" 2>/dev/null || true
    systemctl disable "$u" 2>/dev/null || true
    echo "  $u 已停用"
done
# 多实例：按模板实例名逐个停（soco@<name>.service）
for f in /etc/systemd/system/multi-user.target.wants/soco@*.service; do
    [ -e "$f" ] || continue
    n="$(basename "$f" .service)"
    systemctl stop "$n" 2>/dev/null || true
    systemctl disable "$n" 2>/dev/null || true
    echo "  $n 已停用"
done
systemctl reset-failed 2>/dev/null || true

echo ""
echo "=== 2. 删除 unit 文件 ==="
for d in $UNIT_DIRS; do
    for u in soco-watchdog soco-licence-sink soco-sink-redirect soco-routes-guard soco soco@; do
        rm -f "$d/$u.service" 2>/dev/null || true
    done
    rm -f "$d/soco-routes-guard.path" 2>/dev/null || true
    rm -f "$d"/*.target.wants/soco*.service "$d"/*.target.wants/soco-routes-guard.path 2>/dev/null || true
done
systemctl daemon-reload 2>/dev/null || true
echo "  已删除"

echo ""
echo "=== 3. 删除程序文件 ==="
rm -rf "$BIN_DIR"
rm -f /usr/bin/soco /usr/bin/soco-verify /usr/bin/soco-uninstall /usr/bin/soga-compat.sh
echo "  已删除 ${BIN_DIR} 与辅助命令"

echo ""
echo "=== 4. hosts：只删本项目的授权域名（原子写回）==="
if grep -qE "([[:space:]]|^)($(echo "$LICENCE_HOSTS" | tr ' ' '|'))([[:space:]]|$)" /etc/hosts 2>/dev/null; then
    tmp="$(mktemp /etc/.hosts.XXXXXX)" || { echo "  无法在 /etc 建临时文件，跳过"; tmp=""; }
    if [ -n "$tmp" ]; then
        if awk -v list="$LICENCE_HOSTS" '
            BEGIN { n = split(list, a, " "); for (i = 1; i <= n; i++) ours[a[i]] = 1 }
            /^[[:space:]]*#/ { print; next }
            NF >= 2 { for (i = 2; i <= NF; i++) if ($i in ours) next; print; next }
            { print }' /etc/hosts > "$tmp"; then
            chmod --reference=/etc/hosts "$tmp" 2>/dev/null || chmod 644 "$tmp"
            chown --reference=/etc/hosts "$tmp" 2>/dev/null || true
            mv -f "$tmp" /etc/hosts && echo "  已删除授权域名条目"
        else
            rm -f "$tmp"
            echo "  !! 改写 /etc/hosts 失败（原文件未动）"
        fi
    fi
else
    echo "  无本项目条目"
fi
# 让 glibc 丢掉缓存的解析结果（有就执行，没有不影响）
if command -v resolvectl >/dev/null 2>&1; then resolvectl flush-caches >/dev/null 2>&1 || true; fi

echo ""
echo "=== 5. nft：只删本项目自己的链/表 ==="
if command -v nft >/dev/null 2>&1; then
    nft delete chain ip nat redir 2>/dev/null && echo "  已删 ip nat redir 链" || echo "  ip nat redir 不存在"
    nft delete table ip soco_sink 2>/dev/null && echo "  已删 ip soco_sink 表" || echo "  ip soco_sink 不存在"
    echo "  （ip nat 表本身保留：docker / iptables-nft 的 NAT 也在这里）"
else
    echo "  无 nft 命令，跳过"
fi

echo ""
echo "=== 6. 配置文件 ==="
if [ "$PURGE" -eq 1 ]; then
    rm -rf /etc/soga /etc/soco
    echo "  已删除 /etc/soga 与 /etc/soco（--purge）"
elif [ -d /etc/soga ] || [ -d /etc/soco ]; then
    echo "  保留 /etc/soga（面板密钥在里面）；确认不需要后手动：rm -rf /etc/soga /etc/soco"
fi

echo ""
echo "=== 7. 备份目录 ==="
BACKUPS="$(ls -d /root/soco-backup-* 2>/dev/null | tail -5)"
if [ -n "$BACKUPS" ]; then
    echo "$BACKUPS"
else
    echo "  无备份"
fi

echo ""
echo "=============================================="
echo " 卸载完成"
echo "=============================================="
echo "如需回到原版 soga：systemctl start soga"
echo ""
exit 0