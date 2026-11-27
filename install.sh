#!/usr/bin/env bash
# soco 一键部署引导：拉项目 → 拉二进制 → 进交互控制台
#
#   bash <(curl -fsSL https://raw.githubusercontent.com/hk66443/soco/main/install.sh)
#   curl -fsSL https://raw.githubusercontent.com/hk66443/soco/main/install.sh | bash
#
# 带参数则直接执行对应命令（不进菜单）：
#   ... | bash -s -- install --node-id 12 --type ss --url https://panel.example.com
#
# 可用环境变量覆盖：
#   SO_REPO=user/repo   SO_BRANCH=main   SO_DEST=/root/so
#   SO_VER=v2.18.1      （二进制 release 的 tag）
#   SO_SKIP_BIN=1       （跳过二进制下载，自己放 /usr/local/soco/）
#   SO_FORCE_BIN=1      （即使已有二进制也重新下载覆盖）
set -euo pipefail

REPO="${SO_REPO:-hk66443/soco}"
BRANCH="${SO_BRANCH:-main}"
DEST="${SO_DEST:-/root/so}"
VER="${SO_VER:-v2.18.1}"
BIN_DIR="${SO_BIN_DIR:-/usr/local/soco}"
TARBALL="https://codeload.github.com/${REPO}/tar.gz/refs/heads/${BRANCH}"

say() { printf '%s\n' "$*"; }
die() { printf '!! %s\n' "$*" >&2; exit 1; }

[ "$(id -u)" = "0" ] || die "请用 root 执行（安装要写 /usr/local/soco 与 systemd 单元）"
command -v curl >/dev/null 2>&1 || die "缺 curl，先 apt install -y curl"
command -v tar  >/dev/null 2>&1 || die "缺 tar"

# ── 1. 拉项目 ────────────────────────────────────────────────────────────
say "== 拉取 ${REPO}@${BRANCH} → ${DEST}"
if [ -x "${DEST}/console/so-console" ]; then
    say "   已存在，跳过下载"
else
    tmp="$(mktemp -d)"
    if curl -fsSL --retry 3 --max-time 120 "$TARBALL" -o "${tmp}/so.tgz"; then
        tar xzf "${tmp}/so.tgz" -C "$tmp"
        src="$(find "$tmp" -maxdepth 1 -type d -name 'soco-*' | head -1)"
        [ -n "$src" ] || die "解包后找不到项目目录"
        mkdir -p "$DEST"
        cp -a "${src}/." "$DEST/"
    elif command -v git >/dev/null 2>&1; then
        say "   tarball 失败，改用 git clone"
        rm -rf "$DEST"; mkdir -p "$(dirname "$DEST")"
        git clone --depth 1 -b "$BRANCH" "https://github.com/${REPO}.git" "$DEST"
    else
        die "下载失败，且没有 git 可用"
    fi
    rm -rf "$tmp"
fi

chmod +x "${DEST}/console/so-console" 2>/dev/null || true
[ -x "${DEST}/console/so-console" ] || die "项目里没有 console/so-console"
say "== 项目就绪：${DEST}"

# ── 2. 拉二进制（release 附件，按架构）──────────────────────────────────
case "$(uname -m)" in
    x86_64|amd64)  ARCH=amd64 ;;
    aarch64|arm64) ARCH=arm64 ;;
    *) die "不支持的架构：$(uname -m)（只提供 amd64 / arm64）" ;;
esac

need_bin=0
[ "${SO_FORCE_BIN:-0}" = "1" ] && need_bin=1
[ -x "${BIN_DIR}/soco" ] || need_bin=1
[ -f "${BIN_DIR}/libsoco.so" ] || need_bin=1

if [ "${SO_SKIP_BIN:-0}" = "1" ]; then
    say "== 跳过二进制下载（SO_SKIP_BIN=1），请自行放到 ${BIN_DIR}/"
elif [ "$need_bin" = "1" ]; then
    say "== 下载二进制（${ARCH}, ${VER}）→ ${BIN_DIR}"
    mkdir -p "$BIN_DIR"
    tmpb="$(mktemp -d)"
    url="https://github.com/${REPO}/releases/download/${VER}/soco-bin-${ARCH}.tar.gz"
    if ! curl -fL --retry 3 --max-time 600 --progress-bar "$url" -o "${tmpb}/bin.tgz"; then
        rm -rf "$tmpb"
        die "二进制下载失败：$url
   可手动下载后放到 ${BIN_DIR}/（soco + libsoco.so），或用 SO_SKIP_BIN=1 跳过"
    fi
    tar xzf "${tmpb}/bin.tgz" -C "$tmpb"
    for f in soco libsoco.so; do
        [ -f "${tmpb}/${f}" ] || { rm -rf "$tmpb"; die "包里缺 ${f}"; }
    done
    install -m 755 "${tmpb}/soco"        "${BIN_DIR}/soco"
    install -m 755 "${tmpb}/libsoco.so"  "${BIN_DIR}/libsoco.so"
    rm -rf "$tmpb"
    say "   soco:        $(sha256sum "${BIN_DIR}/soco" | cut -c1-16)…"
    say "   libsoco.so:  $(sha256sum "${BIN_DIR}/libsoco.so" | cut -c1-16)…"
else
    say "== 二进制已存在（${BIN_DIR}），跳过下载（SO_FORCE_BIN=1 可强制覆盖）"
fi

say "== 进入控制台（菜单里选 1 install 开始安装）"
exec "${DEST}/console/so-console" "$@"