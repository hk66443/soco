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
#   SO_SKIP_PULL=1      （不拉/不更新项目文件，沿用现有的 ${SO_DEST}）
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
say "== 拉取/更新 ${REPO}@${BRANCH} → ${DEST}"
if [ "${SO_SKIP_PULL:-0}" = "1" ] && [ -x "${DEST}/console/so-console" ]; then
    say "   跳过拉取（SO_SKIP_PULL=1），沿用现有 ${DEST}"
elif [ "${SO_SKIP_PULL:-0}" = "1" ]; then
    die "SO_SKIP_PULL=1，但 ${DEST}/console/so-console 不存在"
else
    # 默认「拉最新并覆盖程序文件」：以前的逻辑是「DEST 里已有 console 就跳过」，
    # 结果老机器永远停在第一次装的版本，修好的补丁一条都到不了客户手里。
    # /etc 下的配置与面板参数不受影响（配置在 /etc/soga/soga.conf）。
    say "   覆盖更新程序文件（/etc 下的配置不动；要保留本地改动可设 SO_SKIP_PULL=1）"
    tmp="$(mktemp -d)"
    if curl -fsSL --retry 3 --max-time 120 "$TARBALL" -o "${tmp}/so.tgz"; then
        tar xzf "${tmp}/so.tgz" -C "$tmp"
        src="$(find "$tmp" -maxdepth 1 -type d -name 'soco-*' | head -1)"
        [ -n "$src" ] || die "解包后找不到项目目录"
        mkdir -p "$DEST"
        # 用 tar 覆盖（保留 DEST 里多出来的文件），并**排除 install.sh 自身**：
        # 用户很可能就在 /root/so 里 `bash install.sh`，旧逻辑会在执行途中把这个文件覆盖掉，
        # bash 继续按已打开的 fd 读新内容 → 后半段行为错乱（实测：新版脚本跑出旧版行为）。
        ( cd "$src" && tar cf - --exclude='./install.sh' . ) | ( cd "$DEST" && tar xf - ) \
            || die "复制项目到 ${DEST} 失败"
    elif command -v git >/dev/null 2>&1; then
        say "   tarball 失败，改用 git clone（先克隆到临时目录，成功后再覆盖 ${DEST}）"
        clone_root="$(mktemp -d /var/tmp/so-clone.XXXXXX 2>/dev/null || mktemp -d)"
        if git clone --depth 1 -b "$BRANCH" "https://github.com/${REPO}.git" "${clone_root}/so"; then
            # 以前是 rm -rf "$DEST" 再 clone：clone 一失败，已经装好的目录就没了
            mkdir -p "$DEST"
            ( cd "${clone_root}/so" && tar cf - --exclude='./.git' --exclude='./install.sh' . ) \
                | ( cd "$DEST" && tar xf - ) || { rm -rf "$clone_root"; die "复制项目到 ${DEST} 失败"; }
            rm -rf "$clone_root"
        else
            rm -rf "$clone_root"
            die "git clone 失败：https://github.com/${REPO}.git（${BRANCH}）"
        fi
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
    # 空间预检：soco 解出来 ~82 MB + libsoco + tarball，临时目录太小会在解包一半时炸。
    # /tmp 常是 tmpfs（实测这台只有 482 MB），所以临时目录优先放 /var/tmp（根分区）。
    need_mb=350
    avail_mb=$(df -Pm "$(dirname "$BIN_DIR")" 2>/dev/null | awk 'NR==2{print $4}')
    if [ -n "${avail_mb:-}" ] && [ "$avail_mb" -lt "$need_mb" ]; then
        die "磁盘空间不足：$(dirname "$BIN_DIR") 只剩 ${avail_mb} MB，装这套二进制至少要 ${need_mb} MB
   先清理：du -sh /tmp/* /root/* | sort -h | tail"
    fi
    tmpb="$(mktemp -d /var/tmp/so-bin.XXXXXX 2>/dev/null || mktemp -d)"
    tball="${tmpb}/soco-bin-${ARCH}.tar.gz"
    url="https://github.com/${REPO}/releases/download/${VER}/soco-bin-${ARCH}.tar.gz"
    if ! curl -fL --retry 3 --max-time 600 --progress-bar "$url" -o "$tball"; then
        rm -rf "$tmpb"
        die "二进制下载失败：$url
   可手动下载后放到 ${BIN_DIR}/（soco + libsoco.so），或用 SO_SKIP_BIN=1 跳过"
    fi
    # 完整性校验：release 里带 SHA256SUMS。下载被截断/被中间页替换时，
    # 以前会照样"装"上去，然后服务起不来自查半天。
    sums_url="https://github.com/${REPO}/releases/download/${VER}/SHA256SUMS"
    if curl -fsSL --max-time 60 "$sums_url" -o "${tmpb}/SHA256SUMS.raw" 2>/dev/null \
       && [ -s "${tmpb}/SHA256SUMS.raw" ]; then
        # release 里的 SHA256SUMS 是 CRLF 行尾（实测 `…tar.gz^M$`）：
        # 不先去掉 \r，`grep '…tar\.gz$'` 永远匹配不到，校验会静默「跳过」。
        tr -d '\r' < "${tmpb}/SHA256SUMS.raw" > "${tmpb}/SHA256SUMS" 2>/dev/null || true
        line="$(grep -E "soco-bin-${ARCH}\.tar\.gz$" "${tmpb}/SHA256SUMS" 2>/dev/null || true)"
        if [ -z "$line" ]; then
            say "   （SHA256SUMS 里没有 ${ARCH} 条目，跳过校验）"
        elif printf '%s\n' "$line" | ( cd "$tmpb" && sha256sum -c - >/dev/null 2>&1 ); then
            say "   sha256 校验通过（SHA256SUMS）"
        else
            rm -rf "$tmpb"
            die "sha256 校验失败：$url（下载损坏或版本对不上；重试或用 SO_FORCE_BIN=1）"
        fi
    else
        say "   （release 里没有 SHA256SUMS，跳过校验）"
    fi
    tar xzf "$tball" -C "$tmpb" || {
        rm -rf "$tmpb"
        die "解包失败（多数是磁盘空间不足，看上面 tar 的报错）：$tball"
    }
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

# ── 3. 同步运行期脚本（探针 / watchdog / 路由守卫 / licence sink）───────────
# 只拉项目不更新这几支脚本的话，机器上跑的永远是第一次 install 时拷进去的旧版
# （ARM 上实测：console 已是新版，probe_many.py 还是旧的）。旧文件先备份。
if [ -d "${BIN_DIR}" ]; then
    synced=0
    for pair in \
        "${DEST}/_ops/probe_many.py|${BIN_DIR}/probe_many.py" \
        "${DEST}/packaging/soco-watchdog.py|${BIN_DIR}/soco-watchdog.py" \
        "${DEST}/packaging/routes-guard.py|${BIN_DIR}/routes-guard.py" \
        "${DEST}/amd64/src/licence-sink.py|${BIN_DIR}/licence/sink.py"; do
        src="${pair%%|*}"; dst="${pair##*|}"
        [ -f "$src" ] || continue
        mkdir -p "$(dirname "$dst")" 2>/dev/null || true
        if [ -f "$dst" ] && cmp -s "$src" "$dst"; then continue; fi
        if [ -f "$dst" ]; then
            cp -a "$dst" "$dst.bak.$(date +%Y%m%d%H%M%S)" 2>/dev/null || true
        fi
        if install -m 755 "$src" "$dst"; then
            say "   同步 $(basename "$dst")"
            synced=$((synced+1))
        else
            say "   !! 同步失败（权限/只读？）：$dst"
        fi
    done
    if [ "$synced" = "0" ]; then
        say "== 运行期脚本已是最新"
    fi
    if command -v systemctl >/dev/null 2>&1 && systemctl is-active --quiet soco-watchdog 2>/dev/null; then
        say "   （watchdog 已更新，新的探针逻辑在 systemctl restart soco-watchdog 后生效）"
    fi
fi

say "== 进入控制台（菜单里选 1 install 开始安装）"
exec "${DEST}/console/so-console" "$@"