# 部署流程 & 配置一致性专项复测（amd64 + arm64）— 2026-11-26

> 结论先说：**两台都跑通，配置与原版模板完全一致**。过程中修掉 5 个真实缺陷，
> 其中 2 个会导致「客户根本装不上」和「重装丢客户配置」，1 个会把 so-console 打成语法错误。
>
> 复测口径：`/root/so/console/so-console`（v2.1）+ 本机 `_push` 树（= GitHub 公开版）；
> 两台目标机均以 **现网生产配置** 为输入，install 幂等重跑。

---

## 1. 改前 / 改后对照

| 项 | AMD `AMD_IP` | ARM `ARM_IP` |
|---|---|---|
| 架构 / OS | x86_64 / Debian 13 (trixie) | aarch64 / Debian 11 (bullseye) |
| 协议 / 端口 | `ss` (SS2022) / 49989 | `vless` (REALITY) / 49999 |
| 二进制 | `soco c463791a…` + `libsoco 2f60b5f8…` | `soco 549ef746…` + `libsoco f5fc39df…` |
| **改前 so\*\*.conf** | **222 B / 10 行**（缺 31 个原版键，`log_level=debug`） | 1112 B / 41 行（原版模板，`log_level=debug`） |
| **改后 so\*\*.conf** | **63 行 / 41 键，与原版模板逐行一致**，`log_level=error` | 63 行 / 41 键，`log_level=error` |
| install 结果 | 7/7 PASS（端口就绪 10 s） | 7/7 PASS |
| 用户数 | 本地 498 = 面板 498 | 本地 498 = 面板 498 |
| 真实握手 | probe 3/3（连续 3 轮） | probe 3/3 |
| 分流 routes | 0 条（本机原本就是空模板） | **11 条仍加载** `routes num: 11` |
| 服务 | active / NRestarts=0 | active / NRestarts=0 |

改后 AMD 的 `/etc/so**/so**.conf`（脱敏）就是原版模板填值：

```
# 基础配置
type=xboard / server_type=ss / node_id=AMD_NODE_ID / so**_key=9bo4th…
# webapi 对接信息
api=webapi / webapi_url=https://… / webapi_key=AAbbcc…
# db 对接信息（5 键空）
# 手动证书配置（2 键空）
# 自动证书配置（cert_mode 空 / cert_key_length=ec-256）
# proxy protocol（2 键 false）
# 全局限制用户 IP 数（6 键，需 Redis 8.0+）
# 动态限速（7 键）
# 其它杂项（user_conn_limit / user_speed_limit / user_tcp_limit / node_speed_limit = 0）
check_interval=60 / submit_interval=60 / forbidden_bit_torrent=true / log_level=error
```

原版模板基准取自 AMD 机上残留的 `/usr/local/so**/so**.conf`（原版发行包原文，41 键 / 63 行）。

---

## 2. 修掉的 5 个缺陷

### ① `write_conf` 写的配置与原版不同（10 键 vs 41 键）

- 现状：`so-console install` 生成的是**精简 10 行**；原版安装脚本 `install_base` 直接
  `cp so**.conf /etc/so**/`（完整 41 键模板）再 `sed` 改值。
- 后果：客户拿原版配置对比会以为「少了功能」；`so**_key`/`db_*`/`dy_limit_*`/`redis_ip_limit_*`/
  `proxy_protocol`/`forbidden_bit_torrent` 全都不在文件里，只能靠二进制内置默认值。
- 修：`so**_CONF_TEMPLATE` 用原版模板原文（41 键 / 63 行 / 注释分节全同），控制台只填值。
  单元测试 `_ops/test_conf_parity.py` 断言：键集合、键顺序、注释分节、总行数全部等于原版。

### ② install 覆盖式重写会清掉客户在原版上开的功能

- 现状：`write_conf` 整份覆盖，客户已开的 `dy_limit_enable=true`、`redis_ip_limit_*`、
  `proxy_protocol=true`、自定义键 → 重装即丢失。
- 修：改为 **合并写入**（`merge=True`）：先备份 `.bak.<时间戳>`，只更新 `CONF_MANAGED` 那几项，
  可选键沿用旧值，模板外的键追加到文件末尾并加注释。
  单测覆盖：`dy_limit_enable/speed`、`redis_ip_limit_addr`、`user_conn_limit`、`proxy_protocol`
  五个典型自定义 + 模板外 `my_custom_key` 全部保留；`log_level` 作为固定项回到 `error`；
  合并后无重复键行。

### ③ 构建流水线把控制台打成语法错误（部署包本身就是坏的）

- 现象：靶机上 `python3 /root/so/console/so-console` → `SyntaxError: line 658: so**_key = <REDACTED>`。
- 原因：`_ops/make_public_repo.py` 的「key=value 行级脱敏」正则对 `.py` 也生效，
  把代码行 `so**_key = so**_key or secrets.token_hex(16)` 替换成了 `<REDACTED>`。
- 影响面：**GitHub 上的 so-console 一直是坏的**，所以「一键命令 → 进控制台」这条路径从来没真跑通过
  （两台机器上 `/root/so` 此前根本不存在）。
- 修：
  - 行级脱敏只对 `.md/.conf/.toml/.yml/.txt/.log/.json/.ini` 启用（`KEYVAL_EXTS`），代码文件只做
    字面量 + UUID 替换；
  - 构建末尾新增**客户面文件语法校验**（`console/ install.sh packaging/ _ops/probe_many.py`）：
    出现 `<REDACTED>` 或 `compile()` 失败直接 `return 2`，构建失败。
  - 顺带把含我方主机/口令的内部脚本从公开包移出（`run_remote.py`、`ssh_tunnel.py`、
    `make_public_repo.py`）。

### ④ `svc_props` 取值错位 → 安装报「启动失败 FAIL 0」

- 现象：`[6/7] 启动与状态 ········ FAIL 0`，而服务其实 `active`。
- 原因：`systemctl show -p A -p B --value` 的输出顺序**不保证**与 `-p` 顺序一致，
  `st, rs = svc_props(...)` 有时拿到 `('0', 'active')`。
- 修：改用 `name=value` 形式解析后按名取值。

### ⑤ 就绪判定恒真 + 握手无重试 → 刚重启就 prob​e，报 1/3 假失败

- 现象：install 判「启动成功」后立刻 probe，得到 `ok=1/3`、`curl: (97) cannot complete SOCKS5`；
  30 秒后再测即 3/3。
- 原因：等待条件写成 `svc_state=='active' and out(['ss','-lnt'])`（`ss` 有输出即真，从不检查业务端口）。
- 修：改为等**业务端口真的 LISTEN**（实测就绪 10 s，上限 60 s）；握手失败自动等 15 s 复测一轮，
  并在输出里标注「第 2 轮」。

### 附带：systemd 单元补齐两处与原版对齐

- `soco.service` / `soco@.service` 补 `WorkingDirectory=<配置目录>`：
  `routes.toml` / `geoip.dat` / `blockList` 都是工作目录相对路径，写错会让分流**静默**退化为 0 条
  （原版单元同样把 WorkingDirectory 指向配置目录）。ARM 复测 routes 仍 11 条，确认生效。
- `soco@.service` 补 `Environment=SOCO_INSTANCE=%i`（多实例隔离用）。

---

## 3. 复现 / 复核命令

```bash
# 1) 配置一致性（缺键则退出码 1）
so-console conf check
so-console conf keys

# 2) 端到端 install（幂等，会重启）
so-console install --node-id <N> --type <ss|vless> --url <面板> --webapi-key <key>

# 3) 判健康只认握手
so-console users      # 本地 == 面板
so-console probe 3    # 3/3
so-console routes status
```

本机侧：

```powershell
& $py _ops\test_conf_parity.py     # 31 项断言：模板一致性 / 合并保留 / 幂等 / 证书模式
& $py _ops\make_public_repo.py     # 构建公开包 + 客户面语法校验
& $py _ops\push_tree.py amd|arm    # 推送公开树到靶机 /root/so
& $py _ops\run_remote.py amd|arm _ops\test_install_e2e.sh 400
```

---

## 4. 现场备份（回滚点）

| 主机 | 配置备份 |
|---|---|
| AMD | `/etc/so**/so**.conf.bak.20261126074607`（改前 10 行原样）、`…bak.20261126080022`（第二次 install 前） |
| ARM | `/etc/so**/so**.conf.bak.<时间戳>`（由本次 install 自动生成，`ls -l /etc/so**/*.bak.*` 可见） |

回滚配置：`cp /etc/so**/so**.conf.bak.<ts> /etc/so**/so**.conf && systemctl restart soco`。

---

## 5. 遗留 / 下一步

1. **AMD 侧 routes.toml 是空模板（0 条）**，本机不做流媒体分流，与 ARM 的 11 条不同属预期；
   若要把 AMD 也接流媒体，按 `arm64/evidence/STREAM_NF_MATRIX_20261125.md` 的模板填。
2. `check so** failed` 仍按 sink 快速失败路径周期性出现（AMD/ARM 都有），不影响服务
   （`NRestarts=0`、握手 3/3、用户数不降）；`log_level=error` 后日志量已显著下降。
3. 24 小时长稳（`probe_mesh_v2.py --duration 86400`）仍未做，见 HANDOFF §7.2。
4. 多实例 `soco@.service` 已补 `SOCO_INSTANCE`，但未在本次复测中做双实例并发压测。