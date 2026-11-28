# soco 节点工程 · amd64 / arm64（含控制台）

在一台**普通 Debian 机器**上把节点部署起来并做日常运维的工程包：

```
节点程序（二进制补丁 + 适配层 libsoco.so）
  + systemd 单元（主服务 / 多实例模板 / watchdog / 授权 sink / nft 转发）
  + 单文件控制台  console/so-console   ← 一键部署 + 交互菜单 + 全套运维命令
  + 部署与运维脚本、补丁清单、证据
```

两个架构**共用同一条一键命令**，装的时候在向导里选协议即可：

| | amd64（x86_64） | arm64（aarch64） |
|---|---|---|
| 协议（向导里选） | `1` = Shadowsocks 2022 | `2` = VLESS + REALITY |
| 二进制 | 53 区域补丁版 | variantE（变体链生成） |
| 适配层 | `LD_PRELOAD=libsoco.so`（必需） | 同名 aarch64 版 |
| 分流 `routes.toml` | 通常不用 | 常用（控制台只读查看） |
| 内存 | ≥1 GB | ≥2 GB |

> 细节：[DEPLOY.md](DEPLOY.md)（完整流程 / 回滚 / 故障表）　[CONFIG.md](CONFIG.md)（**配置文件在哪 / 字段谁写 / 证书怎么弄**）　[CONSOLE.md](CONSOLE.md)（命令行手册）　[SECURITY.md](SECURITY.md)（占位符）

**机场/主控信息写在 `/etc/so**/so**.conf`**（真实路径用 `so-console paths` 看）：`node_id`、`webapi_url`、`webapi_key`、`so**_key`、协议、间隔、日志、证书都在这个文件里；多机场是 `/etc/so**/<实例名>.conf`。详见 [CONFIG.md](CONFIG.md)。

---

## 0. 前置条件

| 项 | 要求 |
|---|---|
| 系统 | Debian 11/12/13（Ubuntu 22.04+ 亦可），systemd，root |
| 架构 | `x86_64` 或 `aarch64`（`uname -m` 确认，向导里选协议） |
| 内存 | amd64 ≥1 GB；arm64 ≥2 GB |
| 端口 | 业务端口由面板下发；SS2022 要放行 **TCP+UDP** |
| 面板 | 已在该机器建好节点，拿到**节点 ID** |
| 二进制 | `soco` + `libsoco.so`（仓库不含，见 [DEPLOY.md](DEPLOY.md) §2） |
| 探测客户端 | `sing-box` → `/usr/local/soco/sing-box-probe`（`probe`/`doctor` 用，见 [DEPLOY.md](DEPLOY.md) §2.1） |
| 网络 | 机器能出网（拉面板接口 + 定时探活） |

---

## 1. 一键部署（amd64 / arm64 通用）

### 1.1 一条命令：下载项目 → 直接进交互控制台

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/hk66443/soco/main/install.sh)
```

它只做三件事，然后把你丢进控制台：

```
== 拉取 hk66443/soco@main → /root/so
== 项目就绪：/root/so
== 进入控制台（菜单里选 1 install 开始安装）
```

等价写法（管道）与带参数（跳过菜单、直接装）：

```bash
# 管道
curl -fsSL https://raw.githubusercontent.com/hk66443/soco/main/install.sh | bash

# 下载完直接按参数安装（不进菜单）
curl -fsSL https://raw.githubusercontent.com/hk66443/soco/main/install.sh | bash -s -- install --node-id 12 --type ss --url https://panel.example.com

# 项目已经在机器上了：直接进控制台
/root/so/console/so-console
```

### 1.2 交互控制台

进去以后就是菜单：选 `1 install`，向导问四项（**节点 ID / 协议 / 面板地址 / 面板通信密钥 `webapi_key`**），
TLS 协议再多问一项证书方式；其余（`type`、`api`、间隔、日志、`so**_key`、闸门、单元）全部固定或自动。
`webapi_key` 必须粘面板里那串（**不能随机**，随机了节点拉不到用户）；`so**_key` 由控制台随机生成（本工程不校验授权）。
菜单里也能直接敲任意命令，例如 `so> probe 3`、`so> inst new jp1 …`。

```
╭─────────────────────────────────────────────────────────────
│ so-console 2.0   amd64          2026-01-01 12:00:00
╰─────────────────────────────────────────────────────────────
  ── 部署 ─────────────────────────────
   1 install   部署 / 修复本机节点（向导：只填 ID、协议、面板）
   2 inst      多机场：部署 / 查看 / 启停 / 删除实例
  ── 运维 ─────────────────────────────
   3 status    状态总览（服务 / 端口 / 人数 / 闸门 / 分流）
   4 service   启动 / 停止 / 重启
   5 logs      日志（默认主服务，只记错误）
   6 users     本地 vs 面板用户数
  ── 验证 ─────────────────────────────
   7 probe     真实握手（3 / N / all）
   8 gate      600 秒闸门自检
   9 doctor    全量自检
  10 verify    指纹 / 适配层 / 单元
  ── 数据 ─────────────────────────────
  11 routes    流媒体分流（只读查看）
  12 backup    备份（二进制 + 配置）
  13 rollback  从备份回滚
  14 paths     真实路径
  15 conf      配置一致性（对比原版模板）
    0 quit     退出

  so> 
```

安装（菜单 `1`）会依次做完 7 步，幂等，重复执行 = 修复：

```
[1/7] 环境预检           root / systemctl / ss / nft / curl / openssl / 二进制
[2/7] 目录与二进制        /usr/local/soco + licence/，权限 0755 / 0600
[3/7] 写入配置（原版模板）  结构 = 原版 41 键 / 63 行；合并式写入，客户已有值保留
[4/7] 授权 sink          自签证书 + hosts 4 条 + sink 38443
[5/7] systemd 单元        5 个 + daemon-reload + enable
[6/7] 启动与状态          active / pid / restarts / 业务端口就绪（实测 10–19 s）
[7/7] 真实握手验证        3 个用户真实转发（--no-probe 可跳过；失败会自动等 15 s 复测）
```

> **配置文件与原版一致**：`/etc/so**/so**.conf` 就是原版发行包那份 41 键模板，
> 控制台只填必要项，可选键（`dy_limit_*` / `redis_ip_limit_*` / `proxy_protocol` …）保留原版默认
> 且重装不覆盖。随时可审计：`so-console conf check`（见 [CONFIG.md](CONFIG.md) §2.1）。

### 1.3 一行式（脚本 / 批量，不进菜单）

```bash
# 最常用：四项都在参数里（webapi_key 必须是面板那串）
so-console install --node-id 12 --type ss --url https://panel.example.com --webapi-key <面板的 webapi_key>

# 第二个机场（另一台面板）
so-console install --node-id 13 --type vless --url https://p2.example.com --webapi-key <p2 的 webapi_key>

# TLS 协议要证书：panel / self / file / http / dns 五选一（见 CONFIG.md §3）
so-console install --node-id 14 --type trojan --url https://panel.example.com --webapi-key <key> \
  --cert-mode self --cert-domain node.example.com

# 只预演，不改系统（打印 7 步计划）
so-console install --node-id 12 --type ss --url https://panel.example.com --webapi-key <key> --dry-run

# 先装起来，跳过真实握手验证（网络/面板还没通的时候）
so-console install --node-id 12 --type ss --url https://panel.example.com --webapi-key <key> --no-probe

# 直接用实例名部署（等价于 inst new jp1 …）
so-console install --node-id 12 --type ss --url https://panel.example.com --webapi-key <key> --name jp1
```

`so-console` = `/root/so/console/so-console`，可做软链：

```bash
ln -sf /root/so/console/so-console /usr/local/bin/so-console
```

### 1.4 谁填什么

| 项 | 值 | 谁负责 |
|---|---|---|
| 节点 ID | 面板里那个节点 id | **客户填** |
| 协议 | `ss` / `vless` / `vmess` / `trojan` / `anytls` / `hysteria` | **客户选** |
| 面板地址 | `https://panel.example.com`（写进 `webapi_url`） | **客户填** |
| **面板通信密钥** | 面板节点详情里的 `webapi_key` | **客户填**：必须与面板一致，**不能随机**（不一致就拉不到用户） |
| 授权密钥 `so**_key` | 随机串 | **自动**：本工程不校验授权，随便写 |
| 证书（TLS 协议才有） | `panel` / `self` / `file` / `http` / `dns` | 客户选一种，见 [CONFIG.md](CONFIG.md) §3 |
| `type` / `api` | `xboard` / `webapi` | **固定** |
| `check_interval` / `submit_interval` | `60` / `60` | **固定** |
| `log_level` | `error` —— **只记错误日志** | **固定** |
| 授权 sink | hosts 4 条 + `38443` + nft `127.0.0.1:443 → 38443` | **自动** |
| systemd 单元 | 主服务 / `soco@.service` / sink / nft / watchdog | **自动** |
| 业务端口 | 面板下发，控制台自动探测 | **自动** |

> `webapi_key` 是**面板与节点之间的通信密钥**：填错/随机都会导致节点拉不到用户，必须以面板里的为准。
> `so**_key` 是**授权密钥**：本工程已解除授权检查，随机串即可。
> 重跑 `install` 会沿用已有配置里的 `webapi_key`，不会把它换掉。
> 文档里出现的 `so**` 是屏蔽后的程序名，配置文件与授权字段分别是 `so**.conf` / `so**_key`（真实路径看 `so-console paths`）。

---

## 2. 一台机器多个机场（多实例）

```bash
so-console inst                                  # 列表：实例 / 节点ID / 协议 / 状态 / 重启
so-console inst new                              # 向导：实例名 → 节点ID → 协议 → 面板
so-console inst new jp1 --node-id 21 --type vless --url https://p2.example.com
so-console inst start   jp1
so-console inst stop    jp1
so-console inst restart jp1
so-console inst log     jp1
so-console inst remove  jp1
```

每个实例 = 独立 `soco@<名>.service` + `<名>.conf`（`0600`）+ 独立日志；端口由各自面板下发。

| 约束 | 说明 |
|---|---|
| 实例数 ×（80–95 MB）+ 余量 | 1 GB 机器最多 2 个 |
| 不要两个实例同时压满人数 | 适配层状态会互相顶掉，人数会异常掉到个位数 |
| 端口别撞主实例 | 撞了起不来，日志 `bind: address already in use` |

---

## 3. 全部命令总表

| 命令 | 作用 |
|---|---|
| `install [--node-id N] [--type ss\|vless] [--url U] [--webapi-key K] [--name N] [--dry-run] [--no-probe]` | 一键部署 / 修复（幂等） |
| `inst` / `inst new [名] [--node-id N --type T --url U]` / `inst start\|stop\|restart\|log\|remove <名>` | 多机场 |
| `status` | 一屏总览：服务/端口/人数/闸门计数/分流/实例/指纹 |
| `service start\|stop\|restart\|status` | 主服务控制（连带 sink 与 nft 转发） |
| `logs [unit] [行数]` | 日志（默认主服务最后 100 行） |
| `users` | 本地 vs 面板用户数对照 |
| `probe 3` / `probe all` / `probe N 1,50,89` | 真实握手（串行） |
| `gate` | 600 秒闸门自检（hosts / sink / nft / key 错误） |
| `doctor` | 全量自检（17 项，含「配置与原版模板一致」「routes 守卫 active」，逐项 PASS/FAIL + 修复提示） |
| `verify` | 二进制指纹、unit 关键行、适配层是否加载 |
| `routes` / `routes show` / `routes validate` | 流媒体分流**只读**查看与 TOML 校验 |
| `conf check` / `conf show` / `conf keys` | 配置与原版模板比对（缺键则退出码 1）/ 打印 / 键名 |
| `backup` / `rollback [file]` | 备份（二进制+配置）/ 从备份恢复 |
| `paths` | 真实路径（配置 / 二进制 / 实例 / 端口 / 架构） |
| `help` | 用法 |

---

## 4. 目录

```
soco/
├── README.md          ← 本文件（前置条件 + 一键命令 + 控制台 + 命令总表）
├── install.sh         ← 一键引导脚本（拉项目 → 进控制台）
├── DEPLOY.md          ← 完整部署手册（二进制来源、逐步骤、回滚、故障表）
├── CONFIG.md          ← **配置文件在哪 / 每个字段谁写 / 证书（cert_mode）怎么弄**
├── CONSOLE.md         ← 控制台命令参考（输出样例、退出码）
├── SECURITY.md        ← 占位符清单：哪些值要换成你自己的
├── console/so-console ← 单文件控制台（python3，无第三方依赖）
├── amd64/             ← src（适配层源码 / sink / 探针）、deploy、manifest、evidence
├── arm64/             ← src、deploy、analysis、manifest、evidence
├── packaging/         ← 通用交付：install-soco.sh、soco-multi.sh、watchdog、routes-guard
└── _ops/              ← 实战脚本：probe_many.py、build_variant*.py、隧道、跑批
```

**二进制不入库**（每个 80–90 MB）：用 `_ops/build_variant*.py` / `amd64/manifest` 从原版重建，
或从已有部署的 `/usr/local/soco/` 备份取回 → [DEPLOY.md](DEPLOY.md) §2。

---

## 5. 注意

1. **判健康只认真实握手**：`ss -lnt`、`nc -z` 都不可信（闸门态下端口照样 LISTEN，但不转发）。
2. 日志固定 `log_level=error`（只记错误）；要看会话细节临时调高，改完重启。
3. 分流由其它程序负责，`routes` 只读；`routes.toml` 写坏会**静默**退回 0 条。
4. 授权 sink 占 `38443`，`127.0.0.1:443` 用 nft dnat 指过去，**对外 443 是空的**，可给网站用。
5. 变更前先 `so-console verify && so-console backup`，变更后跑 `probe 3` + `doctor`。

---

## 附. 手动部署（不用一键命令时）

### 附 1. 上传项目 + 三步上线

```bash
# ① 上传项目（只传项目本身）
scp -r ./soco root@<你的服务器>:/root/so

# ② 一键安装：向导只问三项 —— 节点 ID / 协议 / 面板地址
/root/so/console/so-console install

# ③ 验证：3 个用户真实握手 + 全量自检
/root/so/console/so-console probe 3
/root/so/console/so-console doctor
```

### 附 2. amd64 手动

```bash
uname -m                      # 期望 x86_64

# ① 放二进制（来源见 DEPLOY.md §2）
install -d -m 755 /usr/local/soco
install -m 755 /root/so/bin/soco        /usr/local/soco/soco
install -m 600 /root/so/bin/libsoco.so  /usr/local/soco/libsoco.so

# ② 安装（向导里协议选 1 = Shadowsocks 2022）
/root/so/console/so-console install

# ③ 验证
/root/so/console/so-console status
/root/so/console/so-console verify      # 适配层已加载（否则用户数会停在 88）
/root/so/console/so-console probe 3
```

要点：`soco.service` 必须带 `Environment=LD_PRELOAD=/usr/local/soco/libsoco.so`（控制台会写好）；
业务端口 **TCP+UDP** 都要放行；压测时**串行**跑，任何时刻最多 1 个探测客户端。

### 附 3. arm64 手动

```bash
uname -m                      # 期望 aarch64

# ① 放二进制（variantE；或用 _ops/build_variant*.py 生成）
install -d -m 755 /usr/local/soco
install -m 755 /root/so/bin/soco        /usr/local/soco/soco
install -m 600 /root/so/bin/libsoco.so  /usr/local/soco/libsoco.so

# ② 安装（向导里协议选 2 = VLESS + REALITY）
/root/so/console/so-console install

# ③ 验证
/root/so/console/so-console verify
/root/so/console/so-console probe 3
/root/so/console/so-console routes      # 分流只读：规则数 / 首个出站 / 加载状态
```

要点：必须用 variantE 那一版二进制；REALITY 的 `public_key / short_id / server_name` 由面板下发，节点侧不写；
流媒体分流由其它程序负责，控制台**只读**。