#!/usr/bin/env bash
# soco 一键部署引导：拉项目 → 进交互控制台
#
#   bash <(curl -fsSL https://raw.githubusercontent.com/hk66443/soco/main/install.sh)
#   curl -fsSL https://raw.githubusercontent.com/hk66443/soco/main/install.sh | bash
#
# 带参数则直接执行对应命令（不进菜单）：
#   ... | bash -s -- install --node-id 12 --type ss --url https://panel.example.com
#
# 可用环境变量覆盖：
#   SO_REPO=user/repo   SO_BRANCH=main   SO_DEST=/root/so
set -euo pipefail

REPO="${SO_REPO:-hk66443/soco}"
BRANCH="${SO_BRANCH:-main}"
DEST="${SO_DEST:-/root/so}"
TARBALL="https://codeload.github.com/${REPO}/tar.gz/refs/heads/${BRANCH}"

say() { printf '%s\n' "$*"; }
die() { printf '!! %s\n' "$*" >&2; exit 1; }

[ "$(id -u)" = "0" ] || die "请用 root 执行（安装要写 /usr/local/soco 与 systemd 单元）"
command -v curl >/dev/null 2>&1 || die "缺 curl，先 apt install -y curl"
command -v tar  >/dev/null 2>&1 || die "缺 tar"

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
        # 覆盖式复制（保留 DEST 里已有的东西，比如你放进去的二进制）
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
say "== 进入控制台（菜单里选 1 install 开始安装）"
exec "${DEST}/console/so-console" "$@"