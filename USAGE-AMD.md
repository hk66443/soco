# USAGE · AMD 节点（x86_64 · Shadowsocks 2022 · `:49989`）

> 适用机器：`141.148.139.236`（私网 `10.0.96.156`），Debian GNU/Linux 13 x86_64，2 vCPU / 962 MB。
> 面板：xboard `node_id=341`，`server_type=ss`，`api=webapi`。协议：**SS2022 `2022-blake3-aes-256-gcm`**。
> 所有命令以 root 执行。**判健康只看真实 SS2022 握手**，不看端口。

---

## 1. 这台机器现在是什么

```
              ┌──────────────────────────────────────────────┐
  客户端 ────►│ soco  (PID: systemd, LD_PRELOAD=libsoco.so)   │
  :49989      │   SS2022  · 用户表来自面板 /UniProxy/user      │
              │   ├─ 向面板 pull 用户 / push 流量 (webapi)     │
              │   └─ 每 600 s 一次 licence 校验 ─────────────┐ │
              └──────────────────────────────────────────────┘ │
                                                               ▼
                          /etc/hosts: 4 条 licence 域名 → 127.0.0.1
                          nft dnat: 127.0.0.1:443 → 127.0.0.1:38443
                          soco-licence-sink (python, TLS 握手即拒) → 快速失败，闸门不关
```

| 项 | 值 |
|---|---|
| 主程序 | `/usr/local/soco/soco`，sha256 `c463791ac4bf9ba82f28b8e87b148976f13397e1407ddab04d366579e4c80fed`，版本 `2.18.1` |
| 适配层 | `/usr/local/soco/libsoco.so`，sha256 `2f60b5f881c9ae462a9de843eaea4471bd4a386a467c4e4c82042355c7998ab7`（源码 [`amd64/src/adapter-amd64.c`](../amd64/src/adapter-amd64.c)） |
| 配置 | `/etc/soga/soga.conf`（**默认 `-c` 目标**）；旧路径 `/etc/soco/soco.conf` 只作备份 |
| 监听 | `*:49989`（TCP+UDP） |
| 用户上限 | 已解除（二进制 53 区域补丁 + 适配层抓全量用户表）；实测 **497/497** |
| 600 s 闸门 | 环境旁路（hosts + sink + nft），已跨越 19.6 min 全量跑批无回归 |

---

## 2. 服务与单元

```bash
systemctl list-units --type=service --all | grep -E 'soco|soga'
```

| 单元 | 作用 | 期望 |
|---|---|---|
| `soco.service` | 主实例（不带 `-c`，默认读 `/etc/soga/soga.conf`） | active，`NRestarts=0` |
| `soco@.service` | 多实例模板（`-c /etc/soga/%i.conf`） | enabled（不常驻） |
| `soco-watchdog.service` | 真实握手探活，连续 3 次失败才重启 | active |
| `soco-licence-sink.service` | `0.0.0.0:38443` 的 licence sink（TLS 立即失败） | active |
| `soco-sink-redirect.service` | nft：`127.0.0.1:443 → 38443`（**把 443 让给业务用**） | active |
| `soco-routes-guard.path/.service` | `routes.toml` 被 nfu 覆盖后自动补回 NF/OpenAI → TW | active |
| `soco-mesh.service` | 备选架构（中继+轮换），**当前 stopped** | stopped |

`/etc/systemd/system/soco.service` 的关键三行：

```ini
Environment=LD_PRELOAD=/usr/local/soco/libsoco.so
ExecStart=/usr/local/soco/soco            # 2026-11-25 起不带 -c
Restart=always
```

> **适配层为什么必须有**：88 用户上限在二进制层被改掉之后，用户表的"注入"仍要由 `libsoco.so` 接管，
> 否则只会 `add user` 到 88。检查它有没有加载：
> `grep libsoco /proc/$(systemctl show soco -p MainPID --value)/maps`

---

## 3. 配置 `/etc/soga/soga.conf`（节选）

```ini
type=xboard
server_type=ss
node_id=341
api=webapi
webapi_url=https://<你的面板域名>
webapi_key=<面板给的 webapi_key>
soga_key=<面板给的 soga_key>
check_interval=60
submit_interval=60
log_level=info
```

- 多实例的私有目录：`/etc/soga/instances/<name>/{log_file_dir,ip_user_cache_save_dir,access_log_dir}`；
- 分流/黑白名单/geo 文件同在 `/etc/soga/`（`routes.toml`、`blockList`、`whiteList`、`dns.yml`、`geoip.dat`、`geosite.dat`）；
- 改完必须 `systemctl restart soco`。

---

## 4. 600 秒闸门（这台机器的关键机关）

**现象**（历史故障）：进程跑满 600 s 后，新连接全部 `curl 52/56`，服务端日志只有 `user N access address` → `handle ... end`，
**没有 `tcp direct dial`** —— 认证过了但不转发。老连接不受影响。

**根因**：每 600 s 向 licence 域名（`sksjd.vaxilu.com` / `*.singledance.xyz` / `*.cilema.xyz`）发一次校验；
请求"挂着不回"或真网络失败，闸门就把数据面关掉。

**现场解法（三件套，缺一不可）**

```bash
# ① licence 域名指向本机（持久化在 /etc/hosts）
grep -nE 'vaxilu|singledance|cilema' /etc/hosts
#   127.0.0.1 sksjd.vaxilu.com
#   127.0.0.1 agdfgkdfg.singledance.xyz
#   127.0.0.1 boiudihsdfk.singledance.xyz
#   127.0.0.1 sxp7hu5t.cilema.xyz

# ② 本机 sink（握手立刻失败 → 检查瞬间失败）
systemctl status soco-licence-sink --no-pager | head -5
ss -lnt | grep ':38443'
python3 /usr/local/soco/licence/sink.py --help   # 实现见 amd64/src/licence-sink.py

# ③ 443 让出：nft 把 127.0.0.1:443 dnat 到 38443（链名不要叫 out，out 是关键字）
nft list ruleset | grep -A3 redir
```

**验证闸门已被压制**（必须跨 600 s）：

```bash
# 进程已跑过 600 s 后仍然 PASS 才算过
systemctl show soco -p MainPID -p ExecMainStartTimestamp -p NRestarts --value | paste -sd' '
python3 /root/soco-pkg/probe_many.py 3 1,2,3        # 3/3 才算过
journalctl -u soco --since '-10min' -o cat | grep -c 'soga key'   # 期望 0
```

---

## 5. 日常运维（复制即用）

```bash
# 状态总览
systemctl is-active soco soco-watchdog soco-licence-sink soco-sink-redirect soco-routes-guard.path
systemctl show soco -p MainPID -p NRestarts -p ActiveState -p ExecMainStartTimestamp --value | paste -sd'|'
ps -o etime=,rss=,pcpu= -p "$(systemctl show soco -p MainPID --value)"

# 用户数 / 面板交互
journalctl -u soco -n 400 -o cat | grep 'current user num' | tail -3
journalctl -u soco --since '-10min' -o cat | grep -E 'auth failed|soga key|panic' | tail -5

# 端口与连接
ss -lntp | grep 49989
ss -tn state established '( sport = :49989 )' | wc -l

# 指纹（变更前后都必须记录）
sha256sum /usr/local/soco/soco /usr/local/soco/libsoco.so
```

### 5.1 健康判据对照表

| 现象 | 含义 / 处置 |
|---|---|
| `probe_many` 3/3 通过、`auth failed=0` | 健康 |
| `curl 52/56` + 日志无 `tcp relay` | **闸门关了** → 查 ① `soco-licence-sink` 是否 active ② `grep vaxilu /etc/hosts` ③ nft 规则 ④ 进程 uptime > 600 s |
| `curl 7` | 端口没在听 / 进程死了 → `systemctl status soco` |
| `current user num` < 面板条数 | 面板 `webapi_url/webapi_key` 错误，或适配层没加载 |
| 用户数恰为 88 | 适配层没生效 → 查 `LD_PRELOAD`、`/proc/<pid>/maps`、`.so` 权限 0600 且 root 拥有 |
| `NRestarts` 一直涨 | watchdog 判真失败在重启 → 先跑 `probe_many` 看是不是真不通 |

---

## 6. 全量验证（497 用户，串行约 20 分钟）

```bash
# 抽检 12 个关键位点（含 88/89/91 闸门边界）
python3 /root/soco-pkg/probe_many.py 12 1,50,88,89,91,100,150,200,300,400,490,497

# 全量 497（分离式启动，断 SSH 不死）
LOG=/root/soco-verified-tests/probe497-amd-$(date +%Y%m%d-%H%M%S).log
setsid bash -c "python3 -u /root/soco-pkg/probe_many.py 497 > $LOG 2>&1" < /dev/null > /dev/null 2>&1 &
tail -f "$LOG"        # 每行一个用户；末尾 TOTAL ok=497/497

# 服务端自证（把窗口对齐到跑批开始时间）
journalctl -u soco --since '<跑批开始时间>' -o cat > /tmp/win.log
grep -c 'access address' /tmp/win.log                                                   # 认证次数
grep -oE 'user [0-9]+ access address' /tmp/win.log | awk '{print $2}' | sort -u | wc -l # distinct 认证用户
grep -oE 'start tcp relay: session id: [0-9]+, user: [0-9]+' /tmp/win.log | awk '{print $NF}' | sort -u | wc -l
grep -c 'auth failed' /tmp/win.log                                                      # 期望 0
```

**2026-11-25 实测**：`TOTAL ok=497/497`，1178 s，服务端 497 authenticated / 497 relayed / 0 auth failed，
`current user num: 497`（窗口内 22 次 pull 全 497），`NRestarts=0` → [证据](../amd64/evidence/AMD_497_FULL_20261125.md)。

---

## 7. 多实例（一台机跑多个机场）

```bash
soco list                                           # 实例 / 状态 / 重启次数 / 日志目录
soco new jp1 node_id=645 webapi_url=https://panel2.example.com webapi_key=KEY soga_key=KEY
soco log jp1 -f
soco config jp1 check_interval=30
soco restart jp1 / soco stop jp1 / soco remove jp1
```

**硬约束（踩过的坑）**

| 约束 | 原因 |
|---|---|
| 同时最多 2 个实例（962 MB 机器） | 4 个实例直接 OOM |
| 固定端口段：实例 `194xx/195xx/196xx/197xx/198xx`，mock=实例+1000，marker=实例+900，socks=实例+8800 | 端口乱撞会让实验数据全废 |
| **不要和生产实例同时压满人数** | 适配层状态共享，会把生产 497 顶成 mock 表（历史事故：在线掉到 6） |
| 实例配置必须在 `/etc/soga/<name>.conf`，日志走 `instances/<name>/` | `soco@.service` 的 `-c` 目标就是它 |

细节：[`packaging/MULTI_INSTANCE.md`](../packaging/MULTI_INSTANCE.md)、[`arm64/evidence/MULTI_INSTANCE_20261125.md`](../arm64/evidence/MULTI_INSTANCE_20261125.md)。

---

## 8. watchdog 与 mesh

- **watchdog**（`soco-watchdog.service`）：`PROBE_EVERY=30`、`FAILS_TO_RESTART=3`、`PREEMPT_SECONDS=0`
  —— 只在**真实握手连续 3 次失败**时重启，不按时间掐点。日志 `/var/log/soco-watchdog.log`。
- **mesh**（`soco-mesh.service`）：中继 + 轮换的备选架构，当前 stopped。
  它是兜底不是等价替代：曾出现 `active born_s_ago=627` 仍在服务（轮换延迟 → 越过 600 s → 新连接 52）。
  要用必须把轮换判据改成 `now - active.born > 540` 立刻轮换，且新后端先做真实握手。
  切法见 [`amd64/deploy/RUNBOOK.md`](../amd64/deploy/RUNBOOK.md) §4.1。

---

## 9. 回滚与彻底恢复

```bash
# ① 二进制回滚到已验证版本（脚本会校验 sha256，不符直接中止）
bash /root/soco-verified-tests/deploy_test_build.sh      # 或 amd64/deploy/restore_c463.sh

# ② 整目录备份（变更前必做）
cp -a /usr/local/soco /root/soco-backup-$(date +%Y%m%d-%H%M)

# ③ 放弃全部改造（回到官方行为：88 上限 + 600 s 闸门都会回来）
systemctl disable --now soco-watchdog soco-licence-sink soco-sink-redirect
sed -i '/vaxilu\|singledance\|cilema/d' /etc/hosts
nft delete chain ip nat redir 2>/dev/null || true
install -m 0755 /root/soco-verified-tests/soco.original /usr/local/soco/soco
systemctl restart soco
```

> **变更前 checklist**：记 `sha256sum` → 记 `MainPID/ExecMainStartTimestamp/NRestarts` → 备份目录 → 变更后跑
> `probe_many`（≥ 3 用户）→ 若涉及闸门相关改动，**必须观察 ≥ 12 分钟（跨 600 s）**才算通过。

---

## 10. 端口 / 资源清单

| 端口 | 用途 |
|---|---|
| `49989/tcp+udp` | SS2022 业务端口 |
| `38443/tcp` | licence sink（python） |
| `443` | **已让出**（nft 只劫持 `127.0.0.1:443`，对外可用） |
| `18089` 等 | watchdog 本地 marker（仅本机） |
| `194xx+` | 多实例/实验室端口段（见 §7） |

内存：962 MB，soco RSS ≈ 74 MB / CPU ≈ 0.2%；同时最多 2 个隔离实例。