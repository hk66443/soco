# 一键部署回归 + 两个阻断性缺陷修复（2026-11-27 UTC）

> 现场节点：`AMD_IP`（amd64，Debian 13）。起点是「全量清空 → 用公开仓库一键命令重装」这一步，
> 上个会话留下的最后动作是 `_ops/diag_fail.sh`（`soco.service could not be found`），根因未定位。
> 本文记录：现场事实 → 两个缺陷的复现与修复 → 修复后的完整验收。

## 1. 修复前现场（`amd64/src/diag_20261128.out.txt`）

| 项 | 状态 |
|---|---|
| `soco` / `soco-watchdog` / `soco-licence-sink` / `soco-sink-redirect` | 全部 `inactive` |
| `/etc/systemd/system/soco*.service` | **一个都没有**（单元从未写入） |
| `/usr/local/soco/` | 二进制在：`soco` c463791a…、`libsoco.so` 2f60b5f8…、`licence/{cert,key}.pem` |
| `/etc/so**/so**.conf` | 已写（41 键 / 与原版模板一致），`node_id=AMD_NODE_ID`、`type=xboard`、`server_type=ss` |
| `/etc/hosts` | 4 条 licence 域名 → 127.0.0.1 在 |
| `nft` | `table ip nat` 在 |
| `so-console doctor` | **5 项 ✘**：主服务 active、业务端口监听、sink active、sink 38443、适配层已加载 |
| 最后一次有效运行 | 2026-11-26 07:46（日志 `close shadowsocks server`） |

结论：安装脚本走到「配置/证书/hosts/nft」之后就没再往下走 —— 单元与启动这一段从未执行。

## 2. 缺陷 1：`so-console` 前向引用，安装必崩在 [4/7]

**复现**（`amd64/src/repro_install_20261128.out.txt`）：

```text
  [3/7] 写入配置（主控信息 + 证书） ········ PASS 原版模板结构 41 键
Traceback (most recent call last):
  File "/root/so/console/so-console", line 825, in deploy
    sink_ok, sink_note = sink_up, ''
UnboundLocalError: cannot access local variable 'sink_up' where it is not associated with a value
```

- `deploy()` 的第 4 步（授权 sink + hosts + nft）读取 `sink_up`，而这个变量直到第 5 步（systemd 单元）
  才被赋值；因为函数里存在对该名字的赋值，Python 把它当局部变量 → 第 4 步必抛。
- 后果：异常发生在写单元**之前** → `soco.service` 等 5 个单元永远不落地、服务永远起不来；
  而且每次 `install` 重跑都死在同一点（幂等修复也失效）。
- 这也解释了为什么 `[1/7]`–`[3/7]` 的产物（conf、证书、hosts、nft 表）都在，而单元与进程什么都没有。

**修复**（`_ops/public/console/so-console`）：

1. 第 4 步只报 hosts 结果，sink/nft 的真实验证交给第 5 步（那一步才启动 sink）；
2. 第 5 步改为「sink 真在 38443 监听才算 PASS，否则 `fail` 并计入失败计数」，不再静默吞掉。

三处同步后 sha256 = `54064c7733ccd8aa5cd174724dc9cd5671b98acc326ebaa2cc5f3a0b28856657`：

- `_ops/public/console/so-console`
- `_push/console/so-console`
- 远端 `/root/so/console/so-console`（备份 `so-console.bak.20261127120414`）

## 3. 缺陷 2：watchdog 架构错配 → 每 2 分钟把健康服务重启一次

缺陷 1 修好后 `install` 7/7 PASS，但服务随即进入重启循环（`amd64/src/wd_diag_20261128.out.txt`）：

```json
{"event": "probe_failed", "fails": 3, "curl_exit": 7,
 "err": "curl: (7) Failed to connect to 127.0.0.1 port 11009 after 0 ms: Could not connect to server",
 "service": {"MainPID": "442206", "NRestarts": "0", "ActiveState": "active"}, "soco_uptime_s": 97.5}
{"event": "restart", "reason": "vless_probe_failed", "restarts": 1}
{"event": "after_restart", "ok": false, "curl_exit": 7, "restarts": 1}
```

- 11:16–12:13 UTC 之间共重启 6 轮，每次都在 `uptime ≈ 122 s` 时触发；
  健康判据（端口在听、`so-console probe` 3/3 PASS）全程都是好的 —— 是**探针自身**起不来。
- 根因：`install` 把 `packaging/soco-watchdog.py`（**VLESS+REALITY 专用**）装到了 AMD 的
  **SS2022** 节点上：它从面板拉 `tls_settings` 组 vless outbound，对 `server_type=ss` 无意义；
  而 AMD 原来的 SS2022 版依赖 `/usr/local/soco/watchdog-model.py`，该文件已随 11/27 的清空丢失。
- 表现就是：`sing-box` 客户端进程起不来 → 11009 没有监听 → `curl (7)` → 3 次失败 → `systemctl restart soco`。

**修复**：`packaging/soco-watchdog.py` 改为**协议自适应单文件**（sha256 `f544137a32430b53…`）：

- 读 `server_type`：`ss` → `shadowsocks` outbound（`cipher` + `server_key:base64(uuid)[:32]`）；
  `vless` → `tls_settings` / REALITY outbound；
- 配置路径候选 `/etc/so**/so**.conf` → `/etc/soco/soco.conf`（不再写死旧路径）；
- 去掉外部 `watchdog-model.py` 依赖；面板异常 / 面板无用户 = `unknown`，不重启；
- 日志 `/var/log/soco-watchdog.log` 超 5 MB 自动轮转；健康时**不刷日志**（只在首轮 `probe_ok` / 失败 / 恢复时记一条）。

旧 VLESS 版留档：`packaging/soco-watchdog-vless-legacy.py`。
落点：`amd64/deploy/soco-watchdog.py`、远端 `/usr/local/soco/soco-watchdog.py`
（备份 `soco-watchdog.py.bak.20261127121417`）、远端 `/root/so/packaging/soco-watchdog.py`。

**部署后日志**（`amd64/src/deploy_wd_20261128.out.txt`）：

```json
{"event": "watchdog_start", "conf": "/etc/so**/so**.conf", "probe_every": 30,
 "fails_to_restart": 3, "preempt_seconds": 0.0, "sbox_present": true}
{"event": "probe_ok", "type": "ss", "server_port": 49989, "uuid": "fa12cb52…"}
```

100 s 观察窗口（`amd64/src/obs1_20261128.out.txt`）：**0 次 restart**，`soco` pid 443188、`NRestarts=0`、
`etime 03:47`，watchdog 只在首轮记了一条 `probe_ok` 之后保持静默。

## 4. 修复后的完整验收（`amd64/src/install_full_20261128.out.txt`、`verify1_20261128.out.txt`）

```text
[1/7] 环境预检                   PASS
[2/7] 目录与二进制               PASS soco 82M
[3/7] 写入配置（主控信息 + 证书） PASS 原版模板结构 41 键
[4/7] 授权 sink + hosts + nft    PASS hosts +0（sink 38443 与 nft dnat 在下一步启动并验证）
[5/7] systemd 单元               PASS 5 个单元 / daemon-reload / sink 38443
[6/7] 启动与状态                 PASS pid=442206 restarts=0 port=49989 就绪 16s
[7/7] 真实握手验证               PASS TOTAL ok=3/3
```

| 检查项 | 结果 |
|---|---|
| `so-console doctor` | **16 项全 ✔**（「结论：全部通过」）；仅剩 `log_level=error` 的「本地人数不可读」信息提示 |
| `so-console conf check` | 41 / 41 键，原版模板 41 个键全具备 |
| 服务 | `soco` active `:49989`；`soco-licence-sink` active `38443`；`soco-sink-redirect` active；`soco-watchdog` active |
| 用户数（面板 UniProxy） | 298（该时点面板实际值；本地人数需 `log_level=info` 才可读） |
| 二进制指纹 | `soco` c463791ac4bf9ba8…、`libsoco.so` 2f60b5f881c9ae46…

收口快照（2026-11-27T12:42Z，`amd64/src/final2_20261128.out.txt`）：`soco` **同一 PID 443188** 连续运行
28 min 58 s、`NRestarts=0`、`probe 3/3` 通过；`/usr/local/soco/soco-watchdog.py` sha256
`f544137a…` 与工程内 `packaging/soco-watchdog.py` **逐字节一致**；
`/root/so/console/so-console` sha256 `54064c77…` 与 `_push/console/so-console` 一致。

## 5. 600 s 闸门跨越（跨周期验证，`amd64/src/gate600_20261128.out.txt`）

等到 `soco` 运行时长越过 600 s 授权检查点后再打真实握手：

```text
2026-11-27T12:24:21Z
soco_uptime=647s  pid=443188 restarts=0
✔ TOTAL ok=3/3      退出码 0      耗时 8s
key_err=0
auth_fail=0
LISTEN 0 4096 *:49989 users:(("soco",pid=443188,fd=12))
LISTEN 0 64 0.0.0.0:38443 users:(("python3",pid=442138,fd=3))
```

要点：**同一 PID**（443188）跨过 600 s 后仍在服务、`NRestarts=0`、3 次真实握手全通过、
12 分钟内 0 条 `so** key` / 0 条 `auth failed`；watchdog 日志在 12:14:21 的 `probe_ok` 之后保持静默
（没有 `probe_failed` / `restart`）。即：新部署的 hosts + sink(38443) + nft dnat 旁路有效，
也没有被错版的 watchdog 掐断。

## 6. 发布链路（已闭合）

1. ~~**`_push/` 需要重新推送**~~ **（2026-11-27 已推送）**：`b839629..2480d40` → 远端 `main` = `2480d40`
   （`git ls-remote origin main` 与本地 HEAD 一致；`raw.githubusercontent.com/hk66443/soco/main/`
   上 `console/so-console` sha256 `54064c77…`、`packaging/soco-watchdog.py` sha256 `f544137a…`，
   codeload tarball 165 文件实测**不含** `sink_ok, sink_note = sink_up` 崩溃行）。
   推送前把本地提交变基到远端最新（远端当时已有 10 个同名重复提交 `963445d..b839629`，不能 fast-forward），
   并顺手删掉被误提交的 `amd64/evidence/runtime/final-soak-1__result.partial.json`（`.gitignore` 本就排除它）。
   线上 `/root/so` 已同步成仓库 HEAD：`console` / `packaging/soco-watchdog.py` / `amd64/deploy/soco-watchdog.py`
   / `HANDOFF.md` / `README.md` / `install.sh` 全部 SAME，只剩一个 `so-console.bak.20261127120414` 备份。
2. **24 h 长稳**仍未做（HANDOFF 待办 1）。
3. ARM 节点（`ARM_IP`）**本轮未动**，其 watchdog 仍是旧 VLESS 版；下次在 ARM 上跑 install
   会自动换成统一版，届时按「ARM 真机复测」流程复测（VLESS/REALITY 探针路径同一份代码）。
4. **新发现：已装机器的老客户不会自动拿到本次修复**。`install.sh` 第 1 步是
   `if [ -x "${DEST}/console/so-console" ] → 已存在，跳过下载`，所以只有新机器/重装才会拉到新版本；
   存量机器要更新得 `rm -rf /root/so` 或手工覆盖：
   ```bash
   curl -fsSL https://codeload.github.com/hk66443/soco/tar.gz/refs/heads/main | tar xz -C /tmp \
     && cp -a /tmp/soco-main/. /root/so/ && rm -rf /tmp/soco-main
   ```