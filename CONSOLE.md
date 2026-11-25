# CONSOLE · `so-console` 命令参考（v2.0）

单文件、无第三方依赖（`python3` ≥ 3.8），amd64 / arm64 同一份。
两种用法等价：**交互控制台**（不带参数）与**直接命令**（适合脚本化）。

```bash
/root/so/console/so-console                    # 进控制台
/root/so/console/so-console status             # 一条命令
ln -s /root/so/console/so-console /usr/local/bin/so-console   # 建议做软链
```

---

## 0. 设计约定（先看这三行）

| 谁填 | 填什么 |
|---|---|
| **客户** | 节点 ID、协议、面板地址（`webapi_url`）、**面板通信密钥 `webapi_key`**（必须与面板一致，不能随机） |
| **客户（TLS 协议时）** | 证书方式：`panel` / `self` / `file` / `http` / `dns`，见 [CONFIG.md](CONFIG.md) §3 |
| **控制台自动** | `so**_key`（授权密钥，随机即可；本工程不校验）、目录、证书落盘、hosts、nft 规则、systemd 单元、端口探测、握手验证 |
| **固定不可改** | `type=xboard` / `api=webapi` / `check_interval=60` / `submit_interval=60` / **`log_level=error`（只记错误日志）** |

> 配置文件是 `/etc/so**/so**.conf`（机场/主控信息都在这），真实路径用 `so-console paths` 看；
> 多机场是 `/etc/so**/<实例名>.conf`。字段逐条说明见 [CONFIG.md](CONFIG.md) §2。

---

## 1. 部署

### 1.1 向导（推荐）

```bash
so-console install
```

```
╭─ 安装向导  面板上的四项
  节点 ID [ ]: 12
  协议：
   1 · Shadowsocks 2022（无证书）
   2 · VLESS（REALITY 由面板下发 / 或自备证书）
   3 · VMess（TLS，需要证书）
   4 · Trojan（TLS，需要证书）
   5 · AnyTLS（TLS，需要证书）
   6 · Hysteria（TLS/QUIC，需要证书）
  选择 [1]: 4
  面板地址 [https://]: https://panel.example.com
  webapi_key = <REDACTED>
  面板密钥 webapi_key: 3f9c1a7d2b4e60815c7a9e2d4b6f8031

╭─ 证书（trojan 需要 TLS）
   1 · 由面板下发证书（xboard 节点里配的 cert_config / 上传内容）
   2 · 本机自签（控制台自己生成 cert/key，最快能用）
   3 · 已有证书文件（给你 cert 与 key 的路径）
   4 · ACME HTTP-01（需要域名 + 80 端口，so** 自己申请）
   5 · ACME DNS-01（需要域名 + dns_provider）
  证书方式 [2]: 2
  证书域名（SNI）: node.example.com

  固定：type              · xboard / api=webapi
  固定：间隔              · pull/push 60s
  固定：日志              · log_level=error（只记错误）
  固定：so**_key          · 随机生成（本工程不校验授权）
  固定：闸门              · hosts + 本地 sink(38443) + nft dnat

── 部署 main
  架构                  · amd64
  节点 ID               · 12
  协议                  · ss
  ...
  [1/7] 环境预检           ········ PASS
  [2/7] 目录与二进制        ········ PASS  soco 92M
  [3/7] 写入配置（固定参数）  ········ PASS  log_level=error
  [4/7] 授权 sink + hosts + nft  PASS  hosts +4, sink 38443
  [5/7] systemd 单元       ········ PASS  5 个单元 / daemon-reload
  [6/7] 启动与状态          ········ PASS  pid=12345 restarts=0 port=49989
  [7/7] 真实握手验证        ········ PASS  TOTAL ok=3/3
```

### 1.2 一行命令（自动化 / 批量）

```bash
so-console install --node-id 12 --type ss --url https://panel.example.com
so-console install --node-id 13 --type vless --url https://p2.example.com --webapi-key 已有的key
so-console install --node-id 12 --type ss --url https://panel.example.com --dry-run   # 只打印将做什么
so-console install --node-id 12 --type ss --url https://panel.example.com --no-probe  # 跳过握手验证
```

`install` 幂等：**重复执行 = 修复**（配置重写、证书补齐、hosts 缺哪条补哪条、单元重装、服务重启）。

---

## 2. 多机场（一台机多个实例）

```bash
so-console inst                                   # 列表：实例 / 节点ID / 协议 / 状态 / 重启
so-console inst new                               # 向导（实例名 → 节点ID → 协议 → 面板）
so-console inst new jp1 --node-id 21 --type vless --url https://p2.example.com
so-console inst start jp1                         # 也可 stop / restart
so-console inst log jp1
so-console inst remove jp1                        # 停服 + 删配置（会二次确认）
```

每个实例 = 独立的 `soco@<名>.service` + 独立配置 `<名>.conf`：

| 项 | 值 |
|---|---|
| 配置文件 | `<inst_dir>/<名>.conf`（`0600`） |
| 单元 | `soco@<名>.service`（`-c <inst_dir>/<名>.conf`） |
| 日志 | `journalctl -u soco@<名>` |
| 端口 | **面板下发**，别和主实例撞；`inst` 列表里能看到状态与重启次数 |

内存参考：单实例 80–95 MB；1 GB 机器最多 2 个，且不要同时压测（适配层状态会互相顶掉）。

---

## 3. 日常运维

| 命令 | 说明 |
|---|---|
| `status` | 一屏总览：服务/端口/人数/闸门计数/分流状态/实例/主程序指纹 |
| `service start\|stop\|restart\|status` | 主服务；`start/restart` 会顺手把 sink 与 nft 转发拉起 |
| `logs [unit] [行数]` | 默认主服务最后 100 行；实例看 `logs soco@jp1` |
| `users` | 本地日志里的 `current user num` vs 面板 `/UniProxy/user` 条数，并给出是否一致 |
| `paths` | 真实路径（配置/二进制/实例/console.conf/端口/架构） |

> **日志只记错误**：配置里固定 `log_level=error`，`journalctl` 里正常情况下不会有流量流水；
> 只有认证失败、key 错误、启动/加载失败这类才会出现。想看会话细节临时调高即可（改完要重启）。

---

## 4. 验证（判健康只认这个）

| 命令 | 用途 | 期望 |
|---|---|---|
| `probe 3` | 3 个用户真实握手 + 真实转发 | `TOTAL ok=3/3` |
| `probe all` | 面板有多少用户跑多少（串行） | `TOTAL ok=N/N` |
| `probe 120 1,50,89` | 指定下标抽检（第几行用户就写第几） | 全 OK |
| `gate` | 600 秒闸门自检：hosts / sink / 38443 / nft / 10 分钟 key 错误 | 闸门已被压制 |
| `doctor` | 全量自检（15 项，逐项 ✔/✘ + 修复提示） | 全部通过 |
| `verify` | 二进制指纹、`du` 体积、unit 关键行、适配层是否加载 | 适配层已加载 |

`probe` 的口径：从面板取参数 → 每个用户**单独**起一个客户端 → 走 `cdn-cgi/trace` 断言真实出网。
**串行**，任何时刻最多 1 个客户端，不压生产。

需要探测客户端 `sing-box-probe`（`install` 不会帮你下载，见 [DEPLOY.md](DEPLOY.md) §2.1）；
`probe` 找不到它会直接提示，不会静默失败。

> 只看端口/`nc -z` 会骗人：闸门打开时端口照样 LISTEN、认证也过，但**不转发**。

---

## 5. 流媒体分流（只读）

分流由**其它程序**负责，本控制台只查看，不写文件：

```bash
so-console routes          # 规则数 / 首个出站 / 最近一次加载结果
so-console routes show     # 额外列出前若干条规则字段
so-console routes validate # 只做 TOML 合法性检查（不动文件）
```

输出示例：

```
╭─ 流媒体分流（只读）
  文件       · /etc/so**/routes.toml
  规则数     · 11
  首个出站   · node-xx.nfdns.xyz:20558
  加载状态   · </etc/so**/routes.toml> success, routes num: 11, enable: true
  提示       · 本控制台只读；改写由 nfu / 其它程序 + routes-guard 负责
```

`规则数 = 0` 或没有 `success` 行 → TOML 被写坏或被覆盖，用 `routes validate` 定位，恢复由你那条链路的工具负责。

---

## 6. 数据与恢复

```bash
so-console backup                  # /usr/local/soco + 配置目录 → /root/so-backup-<时间>.tar.gz
so-console rollback                # 列表选择；先停服，恢复后自动起
so-console rollback /root/so-backup-20260101-120000.tar.gz
```

---

## 7. 交互控制台

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
    0 quit     退出

  so> 
```

- 选编号进对应功能；需要参数时会提示一行（回车 = 交互/默认）；
- 也可以直接敲命令：`so> probe 3`、`so> inst log jp1`、`so> logs soco 40`；
- `Ctrl-C` 干净退出，不会留下半完成状态。

---

## 8. 配置文件 `/etc/so/console.conf`

`install` 写一次；要换路径/服务名就改这里（每行 `key=value`）：

```ini
pkg=/root/so
bin_dir=/usr/local/soco
conf=/etc/so**/so**.conf
inst_dir=/etc/so**
service=soco
port=
arch=amd64
```

| 键 | 含义 |
|---|---|
| `pkg` | 项目目录（探针 / watchdog 从这里拷） |
| `bin_dir` | 二进制与 sink 证书目录 |
| `conf` | 主节点配置 |
| `inst_dir` | 多实例配置目录 |
| `service` | 主单元名（不带 `.service`） |
| `port` / `arch` | 留空自动探测 |

`SO_CONSOLE_CONF=/path/to/other.conf` 可指向另一份配置（一台机演练两套方案）。

---

## 9. 退出码

| 码 | 含义 |
|---|---|
| 0 | 成功 / 检查通过 |
| 1 | 检查未通过或操作未达成 |
| 2 | 参数错误 / 环境预检失败（缺命令、缺二进制、非 root） |
| 130 | 用户 `Ctrl-C` 取消 |