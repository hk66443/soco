# USAGE · ARM 节点（aarch64 · VLESS + REALITY · `:49999`）

> 适用机器：`130.61.141.143`（私网 `10.0.37.39`），Debian GNU/Linux 11 (bullseye) aarch64，Oracle，2 vCPU / 11.9 GB。
> 面板：xboard `node_id=644`，`server_type=vless`。协议：**VLESS + REALITY**（`xtls-rprx-vision`，`flow=vision`）。
> 所有命令以 root 执行。**判健康只看真实 VLESS 握手 + 真实转发**，不看端口。

---

## 1. 这台机器现在是什么

| 项 | 值 |
|---|---|
| 主程序 | `/usr/local/soco/soco` = **variantE**，sha256 `549ef7461a21a19b13f4489323126c1ec219bccf71d4c513b08b505b02821c55`，版本 `2.18.1`，91.6 MB |
| 适配层 | `/usr/local/soco/libsoco.so`，sha256 `f5fc39df4f988cb4a8eb4c683f914a07d5836b1807720aab7b010736cf83293a`（aarch64，`LD_PRELOAD`） |
| 配置 | `/etc/soga/soga.conf`（`type=xboard`、`server_type=vless`、`node_id=644`、`check_interval/submit_interval=60`） |
| 监听 | `*:49999`（VLESS + REALITY） |
| 分流 | `/etc/soga/routes.toml`，**11 条**规则，`enable: true` |
| 用户上限 | 已解除（variantC/E 的 10 处控制闭包补丁）；实测 **497/497** |
| 600 s 闸门 | 环境旁路（hosts + sink 38443 + nft）+ variantE 补回 8 处 `mov #3 → xzr` |
| 内存 | 11.9 GB，soco RSS ≈ 94 MB |

```
客户端 ──(VLESS+REALITY :49999)──► soco(variantE, LD_PRELOAD=libsoco.so)
                                    ├─ 面板 pull 用户 / push 流量（node 644）
                                    ├─ routes.toml：NF/ChatGPT → TW 出站，其余 → US 出站
                                    └─ 每 600 s licence 校验 → sink 快速失败 → 闸门不关
```

---

## 2. 为什么 ARM 走"纯二进制"，而 AMD 走"环境旁路 + 适配层"

| | AMD（x86_64） | ARM（aarch64） |
|---|---|---|
| 88 上限 | 二进制改 53 区域 **+ 适配层抓全量用户表** | variantC/E 的 **10 处补丁**（8 个控制闭包入口改 `ret` + 2 个 nil-error leaf 返回零值） |
| 关键开闸点 | 编译期已知（53 区域） | 运行时定位：xboard 本地 nil-error leaf `E2L2TNbFODvd.O8ecjRSd0zK`（= amd64 `#52`） |
| 600 s 闸门 | 只靠环境（hosts+sink） | 环境 **+** 补回 8 处 `movz x0,#3 → mov x0,xzr`（老 crack 版有、重建版丢了就会退回去） |

**变体谱系**（每一个都必须能在真机跑过才算数）：

| 变体 | 改动 | 88 上限 | 数据面 | 说明 |
|---|---|---|---|---|
| `soga-arm64.original` | 官方原版 | ❌（>88 只 add 到 88） | ✅ | 对照基线 |
| `soga-arm64.crack-soga10` | 43 字节 / 11 处纯 crack | ❌ | ✅ | 老交付：任意 key 一直跑，但不解 88 |
| `soco-arm64.variantB` | 加载层（用户表注入） | 加载 ✅ / 转发 ❌ | ❌ | `>88` 时认证过但不 dial |
| **`soco-arm64.variantC`** | variantB + **10 处**（8 闭包 `ret` + 2 nil leaf） | ✅ | ✅ | 100/200 用户全通 |
| **`soco-arm64.variantE`**（现网） | variantC + 8 处 `mov #3→xzr` | ✅ | ✅ | 497/497；日志不再出现 `soga key 错误` |
| `soco-arm64.variantD/F` | 实验分支 | — | — | 仅留档，勿上线 |

符号表坑：重建出来的 45,462 个入口**整体偏移 `+0x40`**（指向 `_func` 元数据而非代码）；
按"是否以 Go 栈分裂序言开头"统计，原始地址只有 2.9% 命中，`+0x40` 后 77.6% → 见
[`arm64/evidence/ARM_88_GATE_RESOLVED_20261124.md`](../arm64/evidence/ARM_88_GATE_RESOLVED_20261124.md)。

---

## 3. 重建二进制（本仓库不含 90 MB 产物）

```bash
# 前置：arm64 原版（soga-arm64.original）+ 下面这几个脚本
python3 _ops/build_variantA.py     # 基线变体
python3 _ops/build_variantB.py     # 加载层
python3 _ops/build_variantC.py     # +10 处闸门补丁（带入口断言，断言失败立即中止）
python3 _ops/build_variantE.py     # +8 处 mov #3→xzr  → 现网这一版
sha256sum arm64/bin/soco-arm64.variantE    # 期望 549ef746…
```

- 补丁清单（VA / 偏移 / 原字节 / 新字节）：[`_ops/variantB_patchlist.txt`](variantB_patchlist.txt)、[`_ops/variantC_patchlist.txt`](variantC_patchlist.txt)；
  variantE 额外那 8 处在 [`_ops/build_variantE.py`](build_variantE.py) 里内联（含原字节断言 `0xD2400060 / 0xD2400063`）。
- 适配层源码：[`arm64/src/adapter-arm64.c`](../arm64/src/adapter-arm64.c)（aarch64 编译）
- **不要**把 amd64 的补丁照搬到 ARM：两边的功能名同构但地址、序言、闭包数量都不同。

---

## 4. 部署 / 切换 / 回滚

```bash
# ── 首次部署（一键）──────────────────────────────────────────────
bash arm64/deploy/deploy_arm64_soco.sh         # 装 soco+libsoco.so+unit+licence sink+hosts
# 详见 arm64/deploy/DEPLOY_NEW_SERVER.md

# ── 已有机器的常规切换（先备份，再换，再验）────────────────────
systemctl stop soco
cp -a /usr/local/soco/soco /root/soco-verified-tests/soco.pre-$(date +%Y%m%d%H%M)
install -m 0755 arm64/bin/soco-arm64.variantE /usr/local/soco/soco
systemctl start soco
sleep 15 && systemctl is-active soco && python3 /root/soco-pkg/probe_many.py 3 1,2,3

# ── 回滚（现网回滚点）───────────────────────────────────────────
install -m 0755 /root/soco-verified-tests/soco.pre-variantC.202611241151 /usr/local/soco/soco
systemctl restart soco
```

切换后**必须**看这三行日志：`Shadowsocks/VLESS listen`、`current user num: <面板条数>`、`load routes config file … routes num: 11`。

---

## 5. 三关验证（缺一不可）

```bash
# 第一关：进程 + 适配层已加载
systemctl show soco -p MainPID -p NRestarts -p ActiveState --value | paste -sd'|'
grep libsoco /proc/$(systemctl show soco -p MainPID --value)/maps

# 第二关：用户表加载完整（应等于面板 /UniProxy/user 条数）
journalctl -u soco -n 300 -o cat | grep 'current user num' | tail -1     # 期望 497

# 第三关（唯一可信）：真实 VLESS 握手 + 真实转发
python3 /root/soco-pkg/probe_many.py 12 1,50,88,89,91,100,150,200,300,400,490,497
journalctl -u soco --since '-3min' -o cat | grep -E 'access address|tcp relay|tcp direct dial' | tail -6
```

> **只看端口会骗人**：>`>88` 的转发层闸门开着时，端口照样 LISTEN、认证照样过（`access address`），
> 但立刻 `handle vless end`、**没有 `tcp direct dial`**。缺 `tcp relay` 就是没有转发。

### 5.1 全量 497（串行约 7–20 分钟，看机型）

```bash
LOG=/root/soco-verified-tests/probe497-arm-$(date +%Y%m%d-%H%M%S).log
setsid bash -c "python3 -u /root/soco-pkg/probe_many.py 497 > $LOG 2>&1" < /dev/null > /dev/null 2>&1 &
tail -f "$LOG"
```

服务端自证：

```bash
journalctl -u soco --since '<跑批开始时间>' -o cat > /tmp/win.log
grep -oE 'user [0-9]+ access address' /tmp/win.log | awk '{print $2}' | sort -u | wc -l   # distinct 认证
grep -oE 'start tcp relay: session id: [0-9]+, user: [0-9]+' /tmp/win.log | awk '{print $NF}' | sort -u | wc -l
grep -c 'auth failed' /tmp/win.log                                                       # 期望 0
```

**2026-11-24 实测**：`TOTAL ok=497/497`、388 s、服务端 497 authenticated / 497 relayed / 0 auth failed、
`current user num: 497`、`NRestarts=0`、`soga key 错误` 0 条。

---

## 6. 流媒体分流（`routes.toml`）

现网 11 条规则：`#Main`/默认 → US 出站；Netflix / Disney+ / HBO / Spotify / ChatGPT 等 → **TW 出站**；其余地区块照旧。

```bash
# 看条数与是否 enable（写坏会静默退回 0 条，必须看这条日志）
grep -c '^\[\[routes\]\]' /etc/soga/routes.toml
journalctl -u soco -n 400 -o cat | grep 'load routes config' | tail -1
#   → success, routes num: 11, enable: true

# 切换「#Main / 跨国」首选出口地区（只改第一个 Outs 块，同 inode 同长度 → 即时重载）
bash arm64/deploy/switch_stream_area.sh tw      # us|hk|tw|jp|kr|sg|uk
# 改动后会自动备份到 /root/rollback/routes.toml.bak.<utc>

# nfu 覆盖守卫（nfu 重写路由会把 NF/OpenAI 规则冲掉；path unit 会自动补回）
systemctl is-active soco-routes-guard.path
tail -3 /var/log/soco-routes-guard.log
```

**模板 vs 成品**：仓库里的 [`_ops/routes_tw_patch.toml`](routes_tw_patch.toml) 是**带占位符**的片段，
`password`/`UUID` 已脱敏（见 [SECURITY.md](../SECURITY.md)）。真实值在现网 `/etc/soga/routes.toml`，
也可以在面板文档接口按自己的 uuid/节点拉起一份：[`packaging/MULTI_INSTANCE.md`](../packaging/MULTI_INSTANCE.md)。

**NF 能力矩阵实测**（哪些地区对哪家串流有效，容易踩的坑都在里面）：
[`arm64/evidence/STREAM_NF_MATRIX_20261125.md`](../arm64/evidence/STREAM_NF_MATRIX_20261125.md)。
已知结论：`node-us` 对 Netflix **60 s 无响应**（节点本机直连 netflix 是 302），所以 NF 类规则必须走 TW。

---

## 7. 600 秒闸门（ARM 版）

与 AMD 同一套思路，但 ARM 上**必须**同时保证两件事：

| 件 | 做法 | 检查 |
|---|---|---|
| ① 环境旁路 | `/etc/hosts` 4 条 licence 域名 → 127.0.0.1；`soco-licence-sink` 监听 `0.0.0.0:38443`（TLS 立即失败）；`soco-sink-redirect`（nft `127.0.0.1:443 → 38443`） | `grep vaxilu /etc/hosts`、`ss -lnt \| grep 38443`、`nft list ruleset \| grep -A3 redir` |
| ② 二进制补回 8 处 | variantE = variantC + `movz x0,#3 → mov x0,xzr`（8 处，见 `_ops/build_variantE.py`） | `sha256sum /usr/local/soco/soco` = `549ef746…` |

**症状史**：variantC 时期，面板人数到 497 后跑一轮全量，**最后一个用户之后**数据面直接关；
日志只在启动 +1 s 和 +600 s 出现 `soga key 错误`。修完 sink 后 13 分钟窗口（t+0…t+780 s）全 200，
再跑出 497/497。切到 variantE 后 `soga key 错误` 彻底消失（最后一条 2026-11-24 15:13，切换之前）。

---

## 8. watchdog

```bash
systemctl status soco-watchdog --no-pager | head -5
tail -5 /var/log/soco-watchdog.log
```

- 探活方式是**真实 VLESS/REALITY 握手**（`watchdog-client.json` + `sing-box-probe`），不是端口探测；
- `FAILS_TO_RESTART=3`、`PROBE_EVERY=30`；触发重启会写 `{"event":"restart","reason":"vless_probe_failed"}`；
- 现网确有 1 次真实触发（2026-11-25 08:26:38 UTC，`curl 97` SOCKS 建连失败 → 重启 → 30 s 后 `ok=true`），
  这正是它该有的行为：**只在真不通时动手**。

---

## 9. 多实例（一台机多个机场，2026-11-25 统一到 `/etc/soga`）

```bash
soco list
soco new jp1 node_id=645 webapi_url=https://panel2.example.com webapi_key=KEY soga_key=KEY
soco log jp1 -f
soco restart jp1 / soco stop jp1 / soco remove jp1
```

| 约束 | 说明 |
|---|---|
| 生产实例用**默认** `/etc/soga/soga.conf`（unit 不带 `-c`） | 老 unit 带 `-c /etc/soco/soco.conf`，多实例模板 `soco@.service` 才用 `-c /etc/soga/%i.conf` |
| 每个实例独立 log/缓存/access 目录 | 否则日志串、缓存互相覆盖 |
| **同一台机不要同时压满 497 级人数** | 曾把生产 497 顶成 mock 用户表（在线掉到 6）；真因是共用 webapi 域名被 hosts 指到 mock，不是进程共享状态 |
| 二进制装 `/usr/bin/soco` | `soco@.service` 的 `ExecStart` 指向它 |

实测：`soco remove lab1` 后配置删除、服务停止、端口释放，生产 497 不受影响 →
[`arm64/evidence/MULTI_INSTANCE_20261125.md`](../arm64/evidence/MULTI_INSTANCE_20261125.md)。

---

## 10. 故障处置

| 症状 | 排查顺序 |
|---|---|
| 全量跑到第 N 个后开始 FAIL | ① 进程 uptime 是否 > 600 s ② `soga key 错误` 是否再现 ③ sink 是否 active ④ hosts 是否被覆盖 |
| 端口在听、认证过、但客户端没网 | 日志有无 `tcp direct dial` / `tcp relay`；缺就是闸门（88 层或 600 s 层） |
| `current user num` < 面板条数 | 面板 `webapi_url/webapi_key`；适配层是否加载（`/proc/<pid>/maps`） |
| 用户数恰为 88 / 88+1 即断 | 用了旧变体（original / crack-soga10 / variantB）→ 换 variantE |
| 分流全失效、日志 `routes num: 0` | `routes.toml` 被写坏或被 nfu 覆盖 → `switch_stream_area.sh` 或 guard 补回，**先 TOML 校验** |
| 进程反复重启 | 看 `/var/log/soco-watchdog.log` 的 `probe_failed` 详情（curl 97 = SOCKS 建连失败） |
| REALITY 客户端连不上 | 面板下发参数是否变了（`public_key` / `short_id` / `server_name`）；`cat /etc/soga/soga.conf` 与面板比对 |

---

## 11. ARM ⇄ AMD 差异速查（别照搬）

| 项 | ARM | AMD |
|---|---|---|
| 协议/端口 | VLESS+REALITY `:49999` | SS2022 `:49989` |
| 用户表注入 | 二进制补丁即可 | 需要 `LD_PRELOAD` 适配层 |
| 600 s 闸门 | 环境 **+** 8 处 `mov #3→xzr` | 环境（hosts+sink+nft） |
| 探针客户端 | `sing-box-probe`（VLESS/REALITY 参数从面板拉） | `sing-box-probe`（SS2022，`server_key:base64(uuid)`） |
| 分流 | `routes.toml` 11 条 | 无 |
| 多实例根 | `/etc/soga/*.conf` | `/etc/soga/*.conf`（2026-11-25 起统一） |
| 内存 | 11.9 GB / 2 vCPU | 962 MB / 2 vCPU（**多实例要非常克制**） |