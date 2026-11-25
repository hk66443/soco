# soco / soga v2.18.1 · amd64 + arm64 双架构定制工程

> 一套可复现的工程包：把 `soga v2.18.1`（闭源 · garble 混淆 · Go）的 **88 用户上限** 和 **600 秒授权闸门**
> 在两台生产节点上解掉，并留下源码、补丁生成器、systemd 单元、验证夹具与全部实测证据。
>
> - 只想操作机器 → **[USAGE-AMD.md](USAGE-AMD.md)** / **[USAGE-ARM.md](USAGE-ARM.md)**
> - 换机器 / 换人接手 → **[HANDOFF.md](HANDOFF.md)**
> - 想知道"到底怎么绕过去的" → **[BYPASS.md](BYPASS.md)**
> - 仓库里哪些值被脱敏、怎么填自己的 → **[SECURITY.md](SECURITY.md)**

---

## 0. 两台机器一眼对照

| 项 | **AMD 节点**（`amd64/`） | **ARM 节点**（`arm64/`） |
|---|---|---|
| 架构 / 系统 | x86_64 · Debian 13 | aarch64 · Debian 11（Oracle） |
| 面板 / 节点 | xboard · `node_id=341` · `type=webapi` | xboard · `node_id=644` · `type=webapi` |
| 协议 / 端口 | **Shadowsocks 2022**（`2022-blake3-aes-256-gcm`）· `*:49989` | **VLESS + REALITY**（`xtls-rprx-vision`）· `*:49999` |
| 主程序 | `/usr/local/soco/soco`（crack 版 53 处区域补丁） | `/usr/local/soco/soco`（**variantE**，纯二进制） |
| 适配层 | `LD_PRELOAD=/usr/local/soco/libsoco.so`（抓全量用户表） | 同名 `libsoco.so`（另编 aarch64 版） |
| 88 用户上限 | **二进制改 53 区域 + 适配器**，已解除 | **10 处控制闭包补丁**（variantC/E），已解除 |
| 600 秒闸门 | **环境旁路**：hosts 4 条 + 本机 sink + nft dnat | **环境旁路 + variantE 补回 8 处 `mov #3→xzr`** |
| 用户数实测 | **497/497 逐个真实握手通过**（1178 s 串行） | **497/497 逐个真实握手通过**（388 s 串行） |
| 流媒体分流 | 无（SS2022 单协议） | `routes.toml` **11 条**（NF/ChatGPT → TW，其余走 US） |
| 多实例 | `soco@.service` + `/usr/bin/soco`（`/etc/soga/*.conf`） | 同左（2026-11-25 统一） |
| 运维手册 | [USAGE-AMD.md](USAGE-AMD.md) | [USAGE-ARM.md](USAGE-ARM.md) |

> 两台**互不依赖**，各自独立部署；不要跨机器照搬（协议栈不同、补丁位置不同、端口不同）。

---

## 1. 60 秒上手

### 1.1 AMD（SS2022 · 49989）

```bash
# ① 服务三件套是否在跑（sink 折到 38443，443 已让出）
systemctl is-active soco soco-licence-sink soco-sink-redirect
# ② 用户数（应等于面板条数）
journalctl -u soco -n 200 -o cat | grep 'current user num' | tail -1
# ③ 真实握手抽检（唯一可信判据，不是看端口）
python3 /root/soco-pkg/probe_many.py 12 1,50,88,89,91,100,150,200,300,400,490,497
# ④ 全量（497 个用户逐个独立握手，串行约 20 min）
python3 -u /root/soco-pkg/probe_many.py 497 > /root/soco-verified-tests/probe497-$(date +%Y%m%d-%H%M%S).log 2>&1
```

### 1.2 ARM（VLESS + REALITY · 49999）

```bash
# ① 服务与二进制指纹（期望 variantE 549ef746…）
systemctl is-active soco; sha256sum /usr/local/soco/soco
# ② 用户数 + REALITY 参数（只读，用面板接口核对）
journalctl -u soco -n 200 -o cat | grep 'current user num' | tail -1
# ③ 分流条数（写坏会静默退回 0 条）
journalctl -u soco -n 300 -o cat | grep 'load routes config' | tail -1
# ④ 真实握手抽检 / 全量
python3 /root/soco-pkg/probe_many.py 12 1,50,88,89,91,100,150,200,300,400,490,497
python3 -u /root/soco-pkg/probe_many.py 497 > /root/soco-verified-tests/probe497-$(date +%Y%m%d-%H%M%S).log 2>&1
```

> `probe_many.py` 在本仓库 [`_ops/probe_many.py`](_ops/probe_many.py)：从面板拉参数 → **每个用户单独起一个 sing-box 客户端**
> → 走 `cdn-cgi/trace` 断言真实转发。**串行**，任何时刻最多 1 个客户端，不压生产。

---

## 2. 两条铁律（不看这两条一定误判）

1. **看端口在听 = 会被骗。** 停摆态下 `LISTEN` 一直在，`nc -z` 能连上，但 accept 后**立即 close 且不读任何字节**；
   已建立的长连接也不受影响。唯一可信判据是**真实协议握手 + 断言返回内容**（`probe_v2.py` / `probe_many.py`）。
2. **600 秒是"检查结果"驱动的。** 同一条 `soga key` 检查，三种结局三种后果：

| 600 s 时授权检查的结局 | 数据面 |
|---|---|
| 正常联网、拿到失败响应 | **~603 s 关闸**（认证过、不转发） |
| 域名黑洞（连接挂住 → 超时） | **拖到 ~641 s**（600 + 约 40 s 超时） |
| 域名指向本机、**快速失败** | **闸门不关**（两台现网就是这条） |

所以两台的做法都是：**让校验"快速失败"**（hosts 劫持 + 本机 sink），而不是改二进制里那个判断。

---

## 3. 目录

```
soco/
├── README.md                 ← 本文件（总览 + 两架构快速开始）
├── USAGE-AMD.md              ← AMD 节点完整运维（SS2022 · 49989 · 环境旁路 · 多实例）
├── USAGE-ARM.md              ← ARM 节点完整运维（VLESS+REALITY · 49999 · variantE · 分流）
├── SECURITY.md               ← 仓库脱敏清单 + 怎么填自己的值
├── HANDOFF.md                ← 接手包：环境 / 服务 / 命令 / 踩过的坑 / 待办
├── BYPASS.md                 ← 绕过过程全记录（含全部实验数据与排除结论）
├── MANIFEST.sha256           ← 关键产物哈希清单
├── amd64/
│   ├── src/                  ← 适配器 C 源码、sink、mesh、探测与实验室脚本
│   ├── deploy/               ← RUNBOOK.md、systemd 单元、切换/回滚脚本
│   ├── manifest/             ← 53 处补丁清单、静态校验、构建溯源
│   └── evidence/             ← 二分实验、ARM→amd64 映射、运行时证据、497 全量日志
├── arm64/
│   ├── analysis/             ← 43 字节 crack 逐处分析
│   ├── deploy/               ← 一键部署、分流切换、mock 面板、运维脚本
│   ├── manifest/             ← SHA256SUMS、溯源
│   └── evidence/             ← 88 上限解除全过程、497 全量、分流修复、多实例
├── packaging/                ← 通用交付：install-soco.sh、soco-multi.sh、watchdog、routes-guard、MULTI_INSTANCE.md
└── _ops/                     ← 本次实战用的脚本（probe_many、build_variant*、隧道、全量跑批）
```

**二进制不进仓库**（80–90 MB/个）。要拿到它们只有两条路：

1. 从原版 + 本仓库的补丁脚本重建（[`_ops/build_variantE.py`](_ops/build_variantE.py)、[`amd64/manifest/patch-manifest-amd64.json`](amd64/manifest/patch-manifest-amd64.json)、[`amd64/src/adapter-amd64.c`](amd64/src/adapter-amd64.c)）；
2. 从线上机器的备份取回：`/usr/local/soco/{soco,libsoco.so}`，回滚点在 `/root/soco-verified-tests/`。

---

## 4. 现在的生产状态（2026-11-25）

| | AMD `141.148.139.236` | ARM `130.61.141.143` |
|---|---|---|
| 服务 | `soco.service` active，`NRestarts=0` | `soco.service` active，`NRestarts=0` |
| 用户 | `current user num: 497` | `current user num: 497` |
| 全量实测 | **497/497**（12:12–12:32 UTC，1178 s） | **497/497**（388 s，13 分钟窗口零失败） |
| 服务端自证 | 497 authenticated / 497 relayed / 0 auth failed | 497 authenticated / 497 relayed / 0 auth failed |
| 授权 sink | `0.0.0.0:38443` + nft `127.0.0.1:443 → 38443` | 同左（**两台 443 都已让出**） |
| 资源 | 2 vCPU / 962 MB，soco RSS ≈ 74 MB | 2 vCPU / 11.9 GB，soco RSS ≈ 94 MB |

证据：[`amd64/evidence/AMD_497_FULL_20261125.md`](amd64/evidence/AMD_497_FULL_20261125.md)、
[`arm64/evidence/ARM_88_GATE_RESOLVED_20261124.md`](arm64/evidence/ARM_88_GATE_RESOLVED_20261124.md)。

---

## 5. 已知边界（详细在各 USAGE 手册）

1. **600 s 闸门没有从二进制里彻底移除** —— 靠 `/etc/hosts` 4 行 + 本机 sink 维持；删掉就退回"600 s 后新连接全断"。
2. **一台机不要同时跑两个 soco 实例压人数** —— 适配层状态会互相顶掉（曾把生产 497 顶成 mock 表的 6）。多实例要独立目录 + 独立日志，且不同时打满。
3. **`routes.toml` 是带 `{Out}/{OutPort}/{UUID}` 占位符的模板** —— 写坏会**静默**退回 0 条，必须看 `load routes config` 日志。
4. **面板在线人数 = 实时连接数**，客户下线就掉，不是断流；**人数上限 = 面板 `/UniProxy/user` 下发的条数**，代理换 IP 不影响它。
5. **ARM 与 AMD 的补丁不可互换**：amd64 的 53 处里有 9 段在 amd64 上实测无效（见 [BYPASS.md](BYPASS.md) §4），ARM 的关键开闸点是一个 xboard 本地 nil-error leaf。