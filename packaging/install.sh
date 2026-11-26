#!/bin/bash
# ============================================================
#  soco 0.1.0 一键安装脚本
#  用法：
#    远程： bash <(curl -Ls https://raw.githubusercontent.com/<OWNER>/soco/main/install.sh)
#    本地： bash install.sh            (目录里有 arch/<arch>/ 就优先用本地文件)
# ============================================================
set -e
# Validated AMD Debian13 package; local install explicitly unlocked after test evidence.
RELEASE_STATE=APPROVED
case "${1:-}" in
    --dry-run) DRY_RUN=1 ;;
    "") DRY_RUN=0 ;;
    *) echo "用法: bash install.sh [--dry-run]"; exit 2 ;;
esac
# Stop before downloads, dependency installation or service/filesystem changes.
if [ "$DRY_RUN" -eq 0 ] && [ "$RELEASE_STATE" != "APPROVED" ]; then
    echo "发布状态尚未APPROVED，安装早停；可用 --dry-run 仅检查本地文件/架构/ABI。"
    exit 2
fi

# ---------- 可改配置 ----------
REPO="${SOCO_REPO:-OWNER/soco}"          # 改成你的 GitHub 仓库，例如 yourname/soco
VERSION="${SOCO_VERSION:-0.1.0}"
# ------------------------------

DEST=/usr/local/soco
CONF_DIR=/etc/soco
CONF=$CONF_DIR/soco.conf

# 各架构的期望哈希
EXPECT_arm64_bin=1b280c886ae8c608af7acef5fb78114f1e3dff1ad12abfe1b61e6c1f8039e171
EXPECT_arm64_so=f5fc39df4f988cb4a8eb4c683f914a07d5836b1807720aab7b010736cf83293a
EXPECT_amd64_bin=c463791ac4bf9ba82f28b8e87b148976f13397e1407ddab04d366579e4c80fed
EXPECT_amd64_so=2f60b5f881c9ae462a9de843eaea4471bd4a386a467c4e4c82042355c7998ab7

if [ "$DRY_RUN" -eq 0 ]; then [ "$(id -u)" -eq 0 ] || { echo "必须以 root 运行"; exit 1; }; fi

echo "=============================================="
echo " soco $VERSION 一键安装"
echo "=============================================="

# ---------- 1. 识别架构 ----------
MACHINE=$(uname -m)
case "$MACHINE" in
    aarch64|arm64) ARCH=arm64 ;;
    x86_64|amd64)  ARCH=amd64 ;;
    *) echo "不支持的架构: $MACHINE"; exit 1 ;;
esac
echo "架构: $MACHINE  ->  $ARCH"

# 默认不注入用户数量限制；发布状态、文件哈希及ABI在任何部署动作前校验。

# ---------- 2. 判断本地文件还是远程下载 ----------
SELF="${BASH_SOURCE[0]:-}"
HERE=""
if [ -n "$SELF" ] && [ -f "$SELF" ]; then
    HERE=$(cd "$(dirname "$SELF")" && pwd)
fi

LOCAL_BIN=""
LOCAL_SO=""
if [ -n "$HERE" ] && [ -f "$HERE/arch/$ARCH/soco-$ARCH" ]; then
    LOCAL_BIN="$HERE/arch/$ARCH/soco-$ARCH"
    LOCAL_SO="$HERE/arch/$ARCH/libsoco-$ARCH.so"
    echo "模式: 本地文件"
else
    echo "模式: 从 GitHub Releases 下载"
fi


# Read host libc version only; never run the candidate or use ldd on this ELF.
check_abi() {
    if [ "$ARCH" = amd64 ]; then
        local libc_name libc_ver major minor
        read -r libc_name libc_ver < <(getconf GNU_LIBC_VERSION 2>/dev/null || true)
        if [ "${libc_name:-}" != glibc ] || [[ ! "${libc_ver:-}" =~ ^[0-9]+\.[0-9]+ ]]; then
            echo "ABI检查未取得GLIBC版本；此AMD适配器需求GLIBC>=2.38"; return 1
        fi
        major=${libc_ver%%.*}; minor=${libc_ver#*.}; minor=${minor%%.*}
        if (( major < 2 || (major == 2 && minor < 38) )); then
            echo "ABI不匹配: GLIBC $libc_ver，AMD适配器需求>=2.38"; return 1
        fi
        echo "ABI: GLIBC $libc_ver 满足已记录符号需求>=2.38（不是协议验收）"
    fi
}
check_elf() {
    local path=$1 expected=$2 head
    head=$(od -An -tx1 -N20 "$path" | tr -d ' \n')
    [[ "$head" == 7f454c46020101* ]] || { echo "ELF64 little-endian不匹配: $(basename "$path")"; return 1; }
    [ "${head:36:4}" = "$expected" ] || { echo "ELF machine不匹配: $(basename "$path")"; return 1; }
}
check_abi
if [ "$DRY_RUN" -eq 1 ]; then
    [ -n "$HERE" ] && [ -s "$HERE/arch/$ARCH/soco-$ARCH" ] && [ -s "$HERE/arch/$ARCH/libsoco-$ARCH.so" ] || { echo "dry-run只接受完整本地arch文件"; exit 2; }
    eval "EXP_BIN=\$EXPECT_${ARCH}_bin"; eval "EXP_SO=\$EXPECT_${ARCH}_so"
    [ "$(sha256sum "$HERE/arch/$ARCH/soco-$ARCH" | awk '{print $1}')" = "$EXP_BIN" ] || { echo "dry-run binary hash mismatch"; exit 1; }
    [ "$(sha256sum "$HERE/arch/$ARCH/libsoco-$ARCH.so" | awk '{print $1}')" = "$EXP_SO" ] || { echo "dry-run adapter hash mismatch"; exit 1; }
    if [ "$ARCH" = amd64 ]; then EM=3e00; else EM=b700; fi
    check_elf "$HERE/arch/$ARCH/soco-$ARCH" "$EM"
    check_elf "$HERE/arch/$ARCH/libsoco-$ARCH.so" "$EM"
    echo "dry_run=PASS file_hash_arch_abi_only release_state=$RELEASE_STATE traffic_status=NOT_TESTED"
    exit 0
fi

TMPDIR=$(mktemp -d)
trap 'rm -rf "$TMPDIR"' EXIT

fetch() {
    local name="$1" out="$2"
    local url="https://github.com/$REPO/releases/download/v$VERSION/$name"
    echo "  下载 $name ..."
    if command -v curl >/dev/null 2>&1; then
        curl -fL --retry 3 --connect-timeout 15 -o "$out" "$url"
    else
        wget -O "$out" "$url"
    fi
    [ -s "$out" ] || { echo "下载失败: $url"; exit 1; }
}

if [ -n "$LOCAL_BIN" ]; then
    BIN="$LOCAL_BIN"
    SO="$LOCAL_SO"
else
    BIN="$TMPDIR/soco-$ARCH"
    SO="$TMPDIR/libsoco-$ARCH.so"
    fetch "soco-$ARCH" "$BIN"
    fetch "libsoco-$ARCH.so" "$SO"
fi

# ---------- 3. 校验 ----------
echo ""
echo "=== 校验 ==="
A_BIN=$(sha256sum "$BIN" | awk '{print $1}')
A_SO=$(sha256sum "$SO" | awk '{print $1}')
echo "  soco-$ARCH      $A_BIN"
echo "  libsoco-$ARCH.so $A_SO"

eval "EXP_BIN=\$EXPECT_${ARCH}_bin"
eval "EXP_SO=\$EXPECT_${ARCH}_so"

[[ "$EXP_BIN" =~ ^[0-9a-f]{64}$ && "$EXP_SO" =~ ^[0-9a-f]{64}$ ]] || { echo "发布期望哈希缺失"; exit 1; }
[ "$EXP_BIN" = "$A_BIN" ] || { echo "二进制校验失败（期望 $EXP_BIN）"; exit 1; }
[ "$EXP_SO" = "$A_SO" ] || { echo "适配器校验失败（期望 $EXP_SO）"; exit 1; }
echo "  校验通过"

# ---------- 4. 依赖 ----------
echo ""
echo "=== 依赖检查 ==="
MISSING=""
for lib in libcurl.so.4 libjson-c.so.5; do
    if ldconfig -p 2>/dev/null | grep -q "$lib"; then
        echo "  $lib OK"
    else
        echo "  $lib 缺失"
        MISSING="$MISSING $lib"
    fi
done
if [ -n "$MISSING" ]; then
    echo ""
    echo "缺少依赖，尝试安装..."
    if command -v apt-get >/dev/null 2>&1; then
        apt-get update -qq && apt-get install -y libcurl4 libjson-c5
    elif command -v yum >/dev/null 2>&1; then
        yum install -y libcurl json-c
    else
        echo "请手动安装: libcurl4 / libjson-c5"; exit 1
    fi
fi

# ---------- 5. 停旧服务 ----------
echo ""
echo "=== 检查冲突服务 ==="
for unit in soga soco; do
    if systemctl list-unit-files 2>/dev/null | grep -q "^$unit.service"; then
        if systemctl is-active --quiet "$unit" 2>/dev/null; then
            echo "  停止运行中的 $unit.service（避免端口冲突）"
            systemctl stop "$unit" || true
            systemctl disable "$unit" || true
        fi
    fi
done

# ---------- 6. 备份 ----------
echo ""
echo "=== 备份 ==="
STAMP=$(date +%Y%m%d-%H%M%S)
if [ -d "$DEST" ]; then
    cp -a "$DEST" "/root/soco-backup-$STAMP"
    echo "  $DEST -> /root/soco-backup-$STAMP"
fi
[ -f "$CONF" ] && cp -a "$CONF" "/root/soco.conf-backup-$STAMP" && echo "  $CONF 已备份"

# ---------- 7. 部署 ----------
echo ""
echo "=== 部署 ==="
mkdir -p "$DEST" "$CONF_DIR"
# 安装后统一命名为 soco / libsoco.so（适配器按此名字校验）
install -m 700 "$BIN" "$DEST/soco"
install -m 700 "$SO"  "$DEST/libsoco.so"
echo "  已安装到 $DEST"

# ---------- 8. 配置 ----------
echo ""
echo "=== 配置 ==="
if [ -f "$CONF" ]; then
    echo "  沿用已有 $CONF"
elif [ -f /etc/soga/soga.conf ]; then
    cp -a /etc/soga/soga.conf "$CONF"
    chmod 600 "$CONF"
    echo "  已从 /etc/soga/soga.conf 迁移"
else
    cat > "$CONF" <<'EOF'
type=xboard
server_type=vless
api=webapi
webapi_url=https://你的面板域名/
webapi_key=面板通讯密钥
node_id=1
soga_key=
check_interval=60
submit_interval=60
log_level=info
EOF
    chmod 600 "$CONF"
    echo "  已生成示例 $CONF —— 请改好再启动"
fi

# ---------- 9. systemd ----------
echo ""
echo "=== systemd ==="
cat > /etc/systemd/system/soco.service <<EOF
[Unit]
Description=soco $VERSION (soga backend with panel adapter)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
Environment=LD_PRELOAD=$DEST/libsoco.so
ExecStart=$DEST/soco -c $CONF
Restart=always
RestartSec=5
LimitNOFILE=1048576
LimitNPROC=1048576

[Install]
WantedBy=multi-user.target
EOF

cat > /etc/systemd/system/soco@.service <<EOF
[Unit]
Description=soco $VERSION instance %i
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
Environment=LD_PRELOAD=$DEST/libsoco.so
ExecStart=$DEST/soco -c /etc/soco/%i.conf
Restart=always
RestartSec=5
LimitNOFILE=1048576

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload

# ---------- 10. 辅助命令 ----------
echo ""
echo "=== 辅助命令 ==="
HK_VERIFY="$TMPDIR/verify.sh"
HK_UNINST="$TMPDIR/uninstall.sh"
if [ -n "$HERE" ] && [ -f "$HERE/verify.sh" ]; then
    cp -f "$HERE/verify.sh" "$HK_VERIFY"
    cp -f "$HERE/uninstall.sh" "$HK_UNINST"
    echo "  使用本地脚本"
else
    fetch "verify.sh" "$HK_VERIFY" 2>/dev/null || true
    fetch "uninstall.sh" "$HK_UNINST" 2>/dev/null || true
fi
if [ -s "$HK_VERIFY" ]; then
    install -m 755 "$HK_VERIFY" /usr/bin/soco-verify
    echo "  已安装 /usr/bin/soco-verify"
fi
if [ -s "$HK_UNINST" ]; then
    install -m 755 "$HK_UNINST" /usr/bin/soco-uninstall
    echo "  已安装 /usr/bin/soco-uninstall"
fi

echo ""
echo "=============================================="
echo " 安装完成  ($ARCH)"
echo "=============================================="
echo "启动:   systemctl start soco && systemctl enable soco"
echo "日志:   journalctl -u soco -f"
echo "自检:   soco-verify   （或 bash verify.sh）"
echo "卸载:   soco-uninstall"
echo ""
echo "启动后日志应出现："
echo "  [soco] v$VERSION ready (all-fields users, cap bypass)"
echo "  [soco] users=<数量> out=<字节> bytes"
echo "  INFO  current user num: <数量>"
echo "以上只证明加载/就绪观察；traffic_status=NOT_TESTED，协议验收另行核对。"
echo ""
echo "回滚: cp -a /root/soco-backup-$STAMP/. $DEST/ && systemctl restart soco"