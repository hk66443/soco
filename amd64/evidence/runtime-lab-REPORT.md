# 「10 分钟停摆」归因实验报告（隔离实例 + mock 面板）

- 目标机：141.148.139.236（Debian 13 / 6.12.107+deb13-cloud-amd64）
- 时间：2026-11-21 16:08Z – 16:59Z
- 候选二进制：`/root/soco-verified-tests/candidates/verified53-20261121-minimal-v1/soco`
  sha256 `c463791ac4bf9ba82f28b8e87b148976f13397e1407ddab04d366579e4c80fed`
  （与线上 `/usr/local/soco/soco` **同一 sha256**）
- 适配器：`/root/soco-verified-tests/adapter-clean-build-20261121-v1/libsoco-amd64.so`
  sha256 `2f60b5f881c9ae462a9de843eaea4471bd4a386a467c4e4c82042355c7998ab7`
- 面板快照：`/root/soco-verified-tests/lab-fixtures/{config.json,user.json}`（97 用户）
- 探针脚本：`/root/soco-verified-tests/probe_sched_v3.py`（新增：按时调度 / 用户轮换 / 长连接保持 / 停摆后换用户+恢复检查）
- 全程未改 `/etc/hosts`、`/etc/resolv.conf`、未动 `/usr/local/soco/*`、未 restart/stop `soco.service`、未改 unit、未 apt。

## 结论（一句话）

**停摆不是探测打出来的。** 它是**实例进程启动后按墙钟时间**到达阈值（实测 601–604 s，即约 10 分钟）后发生的、**实例级、不自行恢复**的故障；
探测次数、探测间隔、是否换用户、是否并发都**不是**触发条件，也不是拖延条件。

## 实验矩阵（全部单实例隔离，端口 19500+，mock 面板）

| # | run-id | 场景 | 探测次数 | 最后一次成功 | 第一次失败 | curl | 结论 |
|---|---|---|---|---|---|---|---|
| 1 | `rt-zeroprobe650-19530` | **零探测**：起实例后 650s 内一条连接都不建，650/660/670/680s 各探 1 次 | 4（全失败） | 无（此前 0 条连接） | **t=663.2s** | 52 | 停摆 → **与探测无关** |
| 2 | `rt-rotate40-20s-19531` | 20s 一次，**每次换新 uuid**（共 31 个不同用户） | 34（30 成功） | t=593.3s | **t=613.3s** | 52 | 轮换用户无效；失败那次是**从没用过的第 31 个用户** |
| 3 | `rt-sameuser90s-19522` | 同用户 **90s 一次** | 11（7 成功，全程仅 8 条连接） | t=551.2s | **t=641.2s** | 52 | 8 条连接照样停摆 → 排除次数/频率 |
| 4a | `rt-sameuser3s-19541` | 同用户 **3s 一次**，跑 420s | **137 全成功 / 0 失败** | t=419.2s（结束） | 无 | — | 137 条连接无害 → 次数假说死亡 |
| 4b | `rt-sameuser3s700-19570` | 同用户 3s 一次，跑满 700s（把停摆时刻卡到 ±3s） | 200（197 成功） | **t=601.0s** | **t=604.0s** | 52 | **停摆窗口 (601, 604] s** |
| 5 | `rt-sameuser20s-post-19542` | 基线复现 20s 一次 + **停摆后换用户 & 恢复检查** | 33（30 成功） | t=596.3s | **t=616.3s** | 52 | 停摆后换 user2/user3 **同样 52**；+104s 再探仍失败 |
| 6 | `rt-conc5clean-19560` | **5 条长连接全程保持**，每 20s 探第 6 条 | 33（30 成功） | t=599.2s | **t=619.2s** | 52 | 5 并发+探测 600s 内全通，**没有「第 6 条立刻被拒」**；长连接一直活到实验结束（t=698s）才随实例关闭而断 |

> 时间基准：`t` 从脚本启动计；候选进程实际启动约 t≈2s，监听就绪约 t≈11–16s。故停摆 = **进程启动后约 599–602 s**，或**端口就绪后约 588–592 s**。
> 全部 run 的 `cycles@fail` 为 10–12（pull_interval=60s），与 600s 墙钟一致；结合“pull=10 跑 34 周期（340s）不犯”，**刷新周期数不是触发量**。

### 作废（端口/客户端冲突，不作为结论依据）

- `rt-conc5-19540`、`rt-conc5long-19543`：两个 run 的 sing-box socks 端口与别的 run 重叠，`client.log` 明确
  `FATAL start inbound/socks[in0]: listen tcp 127.0.0.1:19840|19843: bind: address already in use`，
  实际 curl 走的是**别人实例**的 socks 入口，其“失败时刻”（124.0s / 557.5s）是另一个实例的停摆时刻，已废弃。
  干净的并发复测即上表第 6 项。

## 停摆签名（本次实测）

1. 新连接：TCP 能连上（监听 socket 仍在，kernel 正常 SYN/ACK），随后无任何数据即被关闭 → `curl 52 (Empty reply from server)`，少数 `curl 56 (Connection reset by peer)`。
2. **已建立的长连接不受影响**（第 6 项：5 条 hold 连接跨过 600s 仍在，直到实例被关闭时才断）。
3. 服务端连接级日志**完全静默**：`/etc/soga/soga-ss-2026-11-21.log` 里正常期每条探测都有
   `start handle client … / user 1 access address … / start tcp relay: session id N … end tcp relay`；
   停摆后（19570 端口最后一次 relay 是 16:50:00，下一次探测 16:50:03）**连 `start handle client` 都不再出现** → 不是鉴权/用户/面板层拒绝，而是 **accept/分发路径整体停摆**。
   （注：隔离实例的连接日志写在 `init log file: /etc/soga/soga-ss-2026-11-21.log`，不在 stdout/server.log，这也是“服务端无日志”的部分原因。）
4. 实例级：停摆后换另外两个 uuid 同样 52。
5. 不可自愈：停摆后 +90s、+104s 复探仍 52（仅重启进程可复位，本次未做重启验证以免碰线上）。

## 对“线上安全探测策略”的结论与建议

**依据**：探测次数/间隔/用户/并发都不是变量（137 条 3s 间隔全通、零探测 650s 后第一条即失败、31 个不同用户全过、5 并发保持 600s 无事），唯一变量是**进程存活时间**。

1. **不必为了“避免打停摆”而限频/轮换用户**——省下的力气应放在“识别停摆”。
2. **健康判据要带进程年龄**：`curl` 探测结果必须与 `systemctl show soco.service -p ExecMainStartTimestamp`（或 `/proc/<pid>/stat` 启动时间）一起记录。
   期望曲线：uptime < 590s → PASS；uptime > 600s → FAIL(52/56)。偏离曲线才是真故障。
3. **单次探测就够**：1 条连接、`--max-time 10`、唯一 run-id、目标用本机 marker（避免外部依赖）。频率建议 ≤1 次/秒，1 次/10–20s 更干净（与停摆无关，只影响日志噪声）。
4. **并发上限**：实测 **5 保持 + 1 新连**（6 并发）600s 内完全正常，没有立刻拒绝的现象；若要更保守，长连接 ≤5、新连接串行即可。
5. **不要把长连接当健康信号**：停摆后老连接仍活、新连接全死。健康检查必须是**新建连接**。
6. **失败要区分类型**：`52/56` 且服务端无 `start handle client` = 停摆态；`curl 7` = 监听不在/进程没了（另一类故障）。
7. **线上运维含义（重要）**：候选与线上二进制 sha256 相同，故线上实例**很可能每条新连接只在启动后约 600s 内可用**。2026-11-21 16:56:46Z 我对线上 49989 做了一次握手探测：当时 `ExecMainStartTimestamp=16:55:28Z`（uptime 76.6s），`PASS=true`，与“600s 内可用”一致。演示/验收前务必在 10 分钟内重启，或先修掉该 600s 定时器。

## 建议的下一步（机制定位，按性价比排序）

1. **去掉 LD_PRELOAD 适配器**跑同一候选（同一 `test.conf`）→ 若 600s 停摆消失，定时器在 `libsoco-amd64.so` 的钩子里；若仍在，则在 soco 本体。
2. 用 `lab_strace.py` 思路对 **595–610s** 窗口抓 accept 线程 syscall（`strace -f -p <pid> -e trace=accept4,epoll_wait,close,futex`）→ 看 accept 循环是阻塞、退出还是被信号打断。
3. 对比 `ss -ltn` 的 `Recv-Q`（停摆期连接堆积在 accept 队列 → accept 循环已停）与 goroutine/线程数（`/proc/<pid>/status` Threads、`gdb -p` 或 Go pprof 若开启）。
4. 检查 soco 相关定时器常量（600s / 10min）在二进制里的出现位置（`strings`/`objdump`）与 adapter 的 `cap bypass` 逻辑是否带超时。

## 证据绝对路径

远端（均在 `/root/soco-verified-tests/` 下，只读或不影响运行）：
- 汇总：`/root/soco-verified-tests/runtime-lab-summary.json`（9 个 run 全量探测记录）
- 逐 run：`/root/soco-verified-tests/<run-id>/result.json`、`result.partial.json`、`server.log`、`client.log`
  run-id 列表：`rt-zeroprobe650-19530`、`rt-rotate40-20s-19531`、`rt-sameuser90s-19522`、`rt-sameuser3s-19541`、`rt-sameuser3s700-19570`、`rt-sameuser20s-post-19542`、`rt-conc5clean-19560`（有效）；`rt-conc5-19540`、`rt-conc5long-19543`（端口冲突作废）
- 脚本：`/root/soco-verified-tests/probe_sched_v2.py`、`probe_sched_v3.py`
- 服务端连接级日志：`/etc/soga/soga-ss-2026-11-21.log`（19570 最后一次 relay 16:50:00；其后无 `start handle client`）
- 线上单次探测：`/root/soco-verified-tests/probes/rt-prodcheck-165645/`、`/root/soco-verified-tests/probe-health.log` 末行

本地（Windows）：
- 本报告：`C:\Users\adminuser\Downloads\soga\_deploy\implementation_amd64_verified\runtime-lab-20261121\REPORT.md`
- 汇总副本：`...\runtime-lab-20261121\evidence_summary.json`
- 逐 run 副本：`...\runtime-lab-20261121\evidence_<run-id>.json`
- 执行脚本：`...\runtime-lab-20261121\{probe_sched.py,probe_sched_v3.py,batch1b.sh,batch2b.sh,batch3.sh,collect.sh,cleanup2.sh}`
- 远端执行回执：`...\runtime-lab-20261121\{batch1_launch,batch1b_launch,batch2b,batch3,collect_01,prodcheck_01,diag_srvlog_01,diag_srvlog2_01,cleanup_02}.out.txt`

## 清理状态

- 我起的 9 个 lab 实例（含客户端与 mock/marker）已全部退出；按 `/proc/*/exe → /root/soco-verified-tests/rt-*` 精确核对，**无残留**；端口 1952x–1957x / 1962x–1977x / 199xx / 2016x–2017x 均已释放。
- 未触碰他人实例：`/root/soco-verified-tests/instr2-N97-760-v1/soco`、`/root/soco-verified-tests/lab-tick1h-v5/soco` 原样保留。
- `soco.service` 全程未被我这侧 restart/stop（期间线上 PID 变化由其它会话造成：129470 → 131729 → 136235 → 138485）。