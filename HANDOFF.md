# HANDOFF — 接手包（换电脑 / 换 AI 必读）

> 目标：让你在**没有任何上下文**的情况下，30 分钟内能：看懂现状 → 连上机器 → 验证服务 → 继续干活。
> 配套阅读：[README.md](README.md)（总览）、[BYPASS.md](BYPASS.md)（根因与实验）、[amd64/deploy/RUNBOOK.md](amd64/deploy/RUNBOOK.md)（运维手册）。

---

## 1. 环境

### 1.1 本机（Windows）

| 项 | 值 |
|---|---|
| 工程根 | `C:\Users\adminuser\Downloads\soco`（本包） |
| 原工作目录 | `C:\Users\adminuser\Downloads\so**\_deploy`（历史实验目录，可不带走） |
| Python | `C:\Users\adminuser\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe` |
| 必备库 | `capstone`(5.x)、`pyelftools`、`paramiko`（已装在该 Python 里） |
| Shell | pwsh（PowerShell 7）。注意 heredoc 用 `@'...'@`、写文件用 UTF-8 |

### 1.2 目标机

| 项 | 值 |
|---|---|
| 主机 | `AMD_IP`（Debian GNU/Linux 13, x86_64） |
| 私网地址 | `AMD_LAN_IP` |
| 出口 IP | `AMD_IP`（面板/客户端看到的就是它） |
| 内存/CPU | 962 MB / 2 vCPU（**注意：内存紧张，同时最多 2–3 个测试实例**） |
| 已装工具 | `strace 6.13`、`gcc`、`python3.13`、`/tmp/sing-box`（探测客户端）、`/usr/local/soco/sing-box-probe`（全量探针客户端） |
| 497 全量 | **497/497 通过**（2026-11-25 12:12–12:32 UTC，串行 1178 s，服务端 497 authenticated / 497 relayed / 0 auth failed，`NRestarts=0`）→ [amd64/evidence/AMD_497_FULL_20261125.md](amd64/evidence/AMD_497_FULL_20261125.md) |

### 1.2b 第二台：ARM（aarch64，流媒体节点）

| 项 | 值 |
|---|---|
| 主机 | `ARM_IP`（私网 `ARM_LAN_IP`），Debian 11 aarch64，云厂商 |
| root 密码 | `<REDACTED>` |
| 服务 | `soco.service`（VLESS + REALITY，`*:49999`，面板 node **644**）；`so**.service` **已 disabled** |
| 二进制 | `/usr/local/soco/soco` **`549ef746…`（variantE，2026-11-24 已切换；497 用户 497/497 全量通过）** + `libsoco.so` `f5fc39df…`（`LD_PRELOAD`）；回滚点 `/root/soco-verified-tests/soco.pre-variantC.202611241151`（旧 crack 版 `37332960…`） |
| 600 s 闸门 | **已用 licence sink 修掉**：`soco-licence-sink`（0.0.0.0:**38443**，快速失败）+ `soco-sink-redirect`（nft 把本机 127.0.0.1:443 dnat 到 38443）+ `/etc/hosts` 4 条 licence 域名 → 127.0.0.1。**443 已空出来**，可以给网站用 |
| 配置 | `/etc/so**/so**.conf`（node_id=<ARM_NODE_ID> / type=xboard / api=webapi；默认 `-c` 目标） |
| 分流 | `/etc/so**/routes.toml` **11 条**（原 10 条 + 2026-11-25 新增 Netflix/OpenAI → 台湾出口）；其余跨国流媒体仍走 `node-us.nfdns.xyz:38383` |
| 流媒体现状 | **Netflix 302 / ChatGPT 200 / api.openai 421（通）**，走 `node-tw.nfdns.xyz:20558`；Disney+/HBO 仍走美国节点（000，见 STREAM_NF_MATRIX_20261125.md） |
| 关键坑 | ① routes 是带 `{Out}/{OutPort}/{UUID}` 占位符的模板，写坏会让 routes 退回 0 且**静默**；② 面板 uuid `<REDACTED-PANEL-UUID>…` ≠ NF 密码 `<REDACTED-NF-PASSWORD>…` |
| 操作 | 换地区：`/usr/local/bin/switch_stream_area.sh us|hk|tw|jp|kr|sg|uk` |
| 复盘 | 见 [arm64/evidence/ARM_STREAM_ROUTES_FIX_20261123.md](arm64/evidence/ARM_STREAM_ROUTES_FIX_20261123.md) |

### 1.2c 部署流程与配置一致性复测（2026-11-26）

| 项 | AMD | ARM |
|---|---|---|
| `so**.conf` 改前 | 10 行（缺 31 个原版键） | 41 行（原版模板，`log_level=debug`） |
| `so**.conf` 改后 | **63 行 / 41 键，与原版模板逐行一致** | 同，`log_level=error` |
| `so-console install` | **7/7 PASS**（端口就绪 10 s） | **7/7 PASS** |
| 用户 / 握手 | 498 = 面板 498；probe **3/3** | 498 = 面板 498；probe **3/3** |
| 分流 routes | 0 条（本机本就空模板） | **11 条仍加载** |

结论：**两台部署流程均正常，配置文件与原版发行包模板完全一致**（字段、顺序、注释分节、63 行）。
`so-console conf check` 可随时审计差异（缺键退出码 1）。本轮修掉的 5 个缺陷见
[amd64/evidence/DEPLOY_CONF_PARITY_20261126.md](amd64/evidence/DEPLOY_CONF_PARITY_20261126.md)，
其中最关键两条：

1. 构建流水线的行级脱敏把 `so-console` 打成 `SyntaxError`（公开包一直是坏的，一键命令从未真跑通）；
2. `write_conf` 整份覆盖会清掉客户在原版上开的 `dy_limit_*` / `redis_ip_limit_*` / `proxy_protocol`
   —— 已改「原版模板 + 合并写入」，重装不丢配置。

### 1.3 SSH（唯一入口）

工程里用的是带白名单的封装，不要直接 `ssh`：

```powershell
$py="C:\Users\adminuser\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe"
$env:so**_SSH_HOST='AMD_IP'
$env:so**_SSH_PASSWORD='<REDACTED>'
# 执行远端脚本（脚本先落地到允许目录，再把 stdout+stderr 收回来）
& $py amd64\src\scoped_ssh.py exec-file <本地脚本> <本地输出json，必须不存在> --timeout 300
# 上传 / 下载
& $py amd64\src\scoped_ssh.py put <本地文件，必须在 _deploy\implementation_amd64_verified\ 下> /root/soco-verified-tests/<名字>
& $py amd64\src\scoped_ssh.py get /root/soco-verified-tests/<名字> <本地新文件>
```

**封装的三条硬规则（踩过坑）**：
1. `exec-file` 是把脚本内容当 `bash -c` 跑，**不能用 `$1/$2` 传参**，参数要写死在脚本里；
2. 输出文件**必须不存在**（同名会 `FileExistsError`），重跑请换名字；
3. 远端可写路径限定在 `/root/soco-verified-tests` 下，本地待传文件限定在 `_deploy\implementation_amd64_verified\` 下。

---

## 2. 敏感信息（本机文件，注意流转）

| 项 | 值 |
|---|---|
| root 密码 | `<REDACTED>` |
| 面板 | `https://<REDACTED>`（Cloudflare 后面） |
| node_id | `341`；`type=xboard`、`server_type=ss`、`api=webapi` |
| 面板 key | 在目标机 `/etc/so**/so**.conf` 的 `so**_key` / `webapi_key` |
| 节点 SS2022 | `2022-blake3-aes-256-gcm`，端口 `49989`，server_key 由面板下发（`/api/v1/server/UniProxy/config`） |
| 面板账号 | 未知（本轮全部操作不需要登录面板） |

> 换机器后建议：改 root 密码 / 换 SSH key，并把 `soco_key` 从面板侧重置一次。

---

## 3. 目标机上的实际布局

```
/usr/local/soco/
├── soco                    主程序（amd64: c463791a…；ARM: variantE 549ef746…）
├── libsoco.so              适配器（amd64 2f60b5f8…；ARM 单独编译版）
├── soco-watchdog.py        watchdog（PROBE_EVERY/FAILS_TO_RESTART/PREEMPT_SECONDS 由 unit 注入；amd 有）
├── soco-mesh.py            mesh 中继（已停用，AMD 上遗留孤儿实例 2026-11-25 已清）
└── licence/{sink.py,sink_38443.py,cert.pem,key.pem,sink-redirect.nft}   本地授权端点（sink，38443）

/etc/systemd/system/
├── soco.service            主实例（2026-11-25 起不带 -c，默认读 /etc/so**/so**.conf）
├── soco@.service           多实例模板（-c /etc/so**/%i.conf，实例名 = 配置文件名）
├── soco-watchdog.service   PREEMPT_SECONDS=0 / FAILS_TO_RESTART=3 / PROBE_EVERY=30（amd）
├── soco-licence-sink.service  0.0.0.0:38443 sink（Restart=always）
├── soco-sink-redirect.service nft: 127.0.0.1:443 dnat → 38443（443 已让出，可跑网站/证书）
├── soco-routes-guard.path/.service  routes.toml 守卫（nfu 覆盖后自动补回 Netflix/OpenAI → TW）
├── soco-watchdog.service   真实 VLESS/REALITY 握手探活，连续 3 次失败重启（ARM；amd 为 SS2022 版）
└── soco-mesh.service       备选架构（当前 stopped）

/etc/so**/                  配置与流媒体目录（与 so** 完全一致，nfu 直接可用）
├── so**.conf               主实例配置（默认 -c 目标）
├── <name>.conf             其它实例配置
├── instances/<name>/       实例私有 log_file_dir / ip_user_cache_save_dir / access_log_dir
├── routes.toml            流媒体分流（10 条 NF 解锁规则）
└── {blockList,whiteList,dns.yml,geoip.dat,geosite.dat}

/usr/bin/soco               多实例管理脚本（list/new/remove/start/stop/restart/log/config/update）
/etc/soco/soco.conf         旧路径，仅备份保留（内容与 /etc/so**/so**.conf 相同）

/root/soco-verified-tests/  所有实验数据（candidates/、lab-fixtures/、lab-*/、probes/、_export/）
```

> 多实例/目录统一的操作手册与实测：见 [arm64/evidence/MULTI_INSTANCE_20261125.md](arm64/evidence/MULTI_INSTANCE_20261125.md)、[packaging/MULTI_INSTANCE.md](packaging/MULTI_INSTANCE.md)。

---

## 4. 常用命令（复制即用）

```bash
# 状态
systemctl is-active soco.service soco-watchdog.service soco-licence-sink.service soco-mesh.service
systemctl show soco.service --property=MainPID,ActiveState,NRestarts,ExecMainStartTimestamp
ss -lntup 'sport' = ':49989'
sha256sum /usr/local/soco/soco /usr/local/soco/libsoco.so
journalctl -b _PID=$(systemctl show soco.service --property=MainPID --value) -o cat | grep -aE 'current user num|so** key|Shadowsocks listen'

# 真实握手验证（唯一可信的健康判据）
cd /root/soco-verified-tests && python3 probe_v2.py            # 打生产 49989
# 输出 PASS=true 才算健康；curl 52/56 且日志无 start handle client = 已进入停摆态

# 切到备选 mesh（停摆无法恢复时）
systemctl stop soco.service soco-watchdog.service && systemctl start soco-mesh.service
# 切回单进程
systemctl stop soco-mesh.service && systemctl start soco-licence-sink.service soco.service soco-watchdog.service

# 多实例（2026-11-25 起：配置目录统一为 /etc/so**，soco 默认就读 /etc/so**/so**.conf）
soco list                                   # 实例 / 状态 / 重启次数 / 日志目录
soco new jp1 node_id=645 webapi_url=https://panel2.example.com webapi_key=KEY so**_key=so**Key
soco log jp1 -f                             # 读 /etc/so**/instances/jp1/ 下的日志
soco config jp1 check_interval=30           # 改实例配置并重启
soco restart jp1 / soco stop jp1 / soco remove jp1
# 手工前台（不带 systemd）：LD_PRELOAD=/usr/local/soco/libsoco.so /usr/local/soco/soco -c /etc/so**/jp1.conf

# 恢复二进制到已验证版本（若被换坏）
bash /root/soco-verified-tests/deploy_test_build.sh   # 需按 amd64/deploy/restore_c463.sh 改路径
```

### 4.1 ARM 节点（node <ARM_NODE_ID> / REALITY 49999，2026-11-24 起是 variantC）

```bash
# 状态 + 二进制指纹（期望 7dd42983…）
systemctl is-active soco
systemctl show soco -p MainPID -p NRestarts -p ExecMainStartTimestamp --value | paste -sd' '
sha256sum /usr/local/soco/soco
ss -lnt | grep 49999

# 面板侧看到的人数与 REALITY 参数（只读，不写入）
CONF=/etc/so**/so**.conf
URL=$(grep -E '^webapi_url=' $CONF | cut -d= -f2-); KEY=$(grep -E '^webapi_key=' $CONF | cut -d= -f2-)
curl -s "$URL/api/v1/server/UniProxy/user?node_id=ARM_NODE_ID&node_type=vless&token=$KEY" | python3 -c 'import sys,json;print(len(json.load(sys.stdin)["users"]))'
curl -s "$URL/api/v1/server/UniProxy/config?node_id=ARM_NODE_ID&node_type=vless&token=$KEY" | python3 -c 'import sys,json;t=json.load(sys.stdin)["tls_settings"];print(t["server_name"],t["public_key"],t["short_id"])'

# 回滚到切换前的 crack 版
install -m755 /root/soco-verified-tests/soco.pre-variantC.202611241151 /usr/local/soco/soco
systemctl restart soco.service
```

端到端复测夹具（本机 Windows，工程内已有）：
`python _ops\ssh_tunnel.py arm 11960 127.0.0.1 49999` → `sing-box run -c _ops\sbx_prod.json` →
`curl.exe -x socks5h://127.0.0.1:21191 https://www.cloudflare.com/cdn-cgi/trace`（应回 `ip=ARM_IP`）。

---

## 5. 关键判据（别被假健康骗了）

1. **只看端口在听 = 会被骗**。停摆态下 LISTEN 一直在、TCP 能连上，但 accept 后立即 close。
2. **看长连接会被骗**。停摆不杀老连接，只杀新连接。
3. **可信判据只有一条**：`probe_v2.py` 用真实 SS2022 握手穿透并断言返回 body（`PASS=true`）。
4. 停摆态的签名：`curl 52`（或 56）+ 服务端日志**没有** `start handle client` + 服务端侧 TIME-WAIT。
5. `so** key 错误` 出现在 **启动 +1 s** 是正常的（ARM 版同样有）；只有 **+600 s** 那条才意味着闸门可能关闭。
   > 2026-11-24 起 ARM 跑的是 **variantC（自带 crack）**，日志里**不再出现** `so** key 错误`，
   > 也不再依赖 `/etc/hosts` + licence sink；若又看到这条，说明二进制被换回了旧版。

---

## 6. 踩过的坑（照着躲）

| 坑 | 后果 | 正确做法 |
|---|---|---|
| 用 `pgrep -f` / `pkill -f` 清理测试进程 | 模式的字符串出现在**自己**的 `bash -c` 命令行里 → 自杀 | 按 `/proc/*/exe` 路径判断，或按端口 `ss -lntpH` 取 pid |
| 端口分配随意 | mock 面板、sing-box socks、marker、实例端口互撞 → 实验数据全废 | 固定端口段：实例 194xx/195xx/196xx/197xx/198xx，mock=实例+1000，marker=实例+900，socks=实例+8800；生产 mesh 占 49989/51000+/52000+ |
| 内存当无限用 | 机器 962 MB，4 个实例就 OOM | 同时最多 2 个隔离实例，跑完立刻 kill |
| validator 起得太早 | 0.9 s 就断言监听 → 误判失败 | 就绪约 10–19 s，必须轮询等待 |
| 用 fixtures 的 mock 面板做"真实链路" | 某些 run 会报 `缺少 node_id`（mock 只实现 GET） | 要真实链路就用 mesh/真实面板；mock 只用于快速回归 |
| 认为"改 8 个核心点就能绕闸门" | 白跑 8 个 run | 那 8 处在 c463 里是死值，见 [BYPASS.md](BYPASS.md) §4 |
| 改 `/etc/hosts` 指向不可达地址 | 启动阶段直接卡住（listener 都不起） | 只能在**启动完成之后**再改，或改成本机有监听（快速失败） |
| 把 `scoped_ssh.py` 的输出路径重名 | `FileExistsError` | 每次用新文件名 |
| 在 `unshare -n` 里测 | 无外网时闸门不触发，会误判"已修复" | 判断闸门必须保留外网可达 |

---

## 7. 现状与待办

### 7.1 已完成

- 88 用户上限（97 用户正常、SS2022 通）
- 600 s 闸门的环境级旁路（单进程 30 分钟 90/90 通过，线上已切）
- 备选架构 mesh（36 次轮换 0 拒绝）与 watchdog（只在真实失败时重启）
- **ARM 88 用户上限彻底解除**（2026-11-24）：`variantC`，100 用户 24/24、300 s soak 15/15、200 用户 9/9
  （[arm64/evidence/ARM_88_GATE_RESOLVED_20261124.md](arm64/evidence/ARM_88_GATE_RESOLVED_20261124.md)）
- **AMD 497 用户全量复核**（2026-11-25）：面板 497 条用户逐个独立 SS2022 握手 + 真实转发，
  `TOTAL ok=497/497`、0 失败、1178 s；服务端 497 distinct authenticated / 497 distinct relayed / 0 auth failed；
  19.6 min 跨 2 次 600 s 周期无回归，`NRestarts=0`
  （[amd64/evidence/AMD_497_FULL_20261125.md](amd64/evidence/AMD_497_FULL_20261125.md)）
- **多实例 + 配置目录统一 so\*\***（2026-11-25）：两台均改成默认读 `/etc/so**/so**.conf`，
  `soco@.service` 模板 + `/usr/bin/soco` 管理脚本；同机 3 实例实测隔离（生产 497 不受影响）；
  ARM/AMD 的 licence sink 都换到 `38443` + nft dnat，**两台 443 都已让出**
  （[arm64/evidence/MULTI_INSTANCE_20261125.md](arm64/evidence/MULTI_INSTANCE_20261125.md)）

### 7.2 待办（按优先级）

1. **24 小时长稳**：现在只有 30 min（隔离台）+ 45 min（线上 soak）。建议挂 `probe_mesh_v2.py --duration 86400 --every 60`。
2. ~~**部署流程 + 配置一致性复测**~~ **（2026-11-26 完成）**：AMD/ARM 均 `install 7/7 PASS`、
   `so**.conf` 与原版模板逐行一致（41 键 / 63 行）、probe 3/3、用户数 498 对齐；
   修掉 6 个缺陷（含公开包 so-console 语法错误、覆盖式写入丢客户配置、log_level=error 后本地人数不可读）；2026-11-27 又做了一轮**交互层/逻辑层**复查，再修 10 个（菜单回车重复执行、空表崩溃、rollback 越界、backup 写死 /root 等）。
   见 [amd64/evidence/DEPLOY_CONF_PARITY_20261126.md](amd64/evidence/DEPLOY_CONF_PARITY_20261126.md)。
3. ~~**纯二进制旁路**~~ **（2026-11-24 已完成，amd64 侧仍走 hosts+sink）**：
   - ARM 侧已闭合：`variantC = variantB + 10 处补丁`，100 用户数据面实测通过、200 用户也通；
     符号表修正（每个入口 +0x40）+ 调用图 + amd 53 处语义映射 + 逐点 bisect 全程见
     [arm64/evidence/ARM_88_GATE_RESOLVED_20261124.md](arm64/evidence/ARM_88_GATE_RESOLVED_20261124.md)。
   - 关键结论：开闸点是 **xboard 本地 nil-error leaf `E2L2TNbFODvd.O8ecjRSd0zK`**（对应 amd64 `#52`），
     稳定性靠 8 个 SS/VLESS 控制闭包入口改 `ret`（对应 amd64 `#44–51`）。
   - 交付二进制：`arm64/bin/soco-arm64.variantC`（sha256 `7dd42983…`）；生产**尚未**更换。
4. **sink 健壮性**：给 `soco.service` 加 `Wants=soco-licence-sink.service`、`sink` 加 `PartOf=soco.service`，避免 sink 挂掉时撞上 600 s 检查。
5. **ARM 真机复测**：已完成（2026-11-23）。`ARM_IP` 上 soco 连续运行 ~2 h、`NRestarts=0`、
   真实 VLESS/REALITY 链路与 10 条 NF 解锁分流均正常，**未见 600 s 数据面闸门**；
   另修掉 `routes.toml` 加载失败的静默故障（详见 [arm64/evidence/ARM_STREAM_ROUTES_FIX_20261123.md](arm64/evidence/ARM_STREAM_ROUTES_FIX_20261123.md)）。
6. **出正式 release**：`packaging/` 里是旧包装（install/verify/manifest/checker），若要发布需要把本轮 amd64 产物与 sink/hosts 方案纳入 manifest。
7. **多实例并发压测**：`soco@.service` 已补 `SOCO_INSTANCE=%i` + `WorkingDirectory`，但本轮只做单实例复测。

---

## 8. 证据索引（都在本包内）

| 想证明什么 | 看哪里 |
|---|---|
| 停摆签名、时间窗、与探测无关 | `amd64/evidence/runtime-lab-REPORT.md`、`amd64/evidence/runtime/lab-*.json` |
| 三种检查结局的对照（关键） | `amd64/evidence/runtime/lab-hosts-hang-1__result.json`（641 s）、`lab-fakelic-long__result.json`（>1792 s 无失败） |
| 8 点/分支/常量全无效 | `amd64/evidence/bisect-RESULTS.md`、`amd64/evidence/bisect-*.result.json` |
| ARM→amd64 映射（含被排除理由） | `amd64/evidence/armmap-REPORT_arm_to_amd64_twin.md` |
| mesh 零拒绝 | `amd64/evidence/runtime/mesh-prod-probe-1__result.json`、`amd64/evidence/runtime/soco-mesh.log.tail` |
| 线上部署指纹 | `amd64/evidence/runtime/deployed-hashes.txt`、`services-state.txt`、`ss-49989.txt`、`hosts.licence-entries` |
| 旧交付验收（97/89/6000 档协议） | `amd64/evidence/verification/**` |
| watchdog 设计 | `amd64/evidence/STALL_AND_WATCHDOG.md` |
| ARM 88 上限解除（符号表 +0x40、10 处补丁、逐点实测） | `arm64/evidence/ARM_88_GATE_RESOLVED_20261124.md` |
| 修正后的 ARM 函数表 / 调用图 | `_ops/arm64.funcs.fixed.json`、`_ops/arm64.callgraph.json` |
| AMD 497 用户全量（串行 1178 s、497/497、服务端 497 authenticated） | `amd64/evidence/AMD_497_FULL_20261125.md`、`amd64/evidence/runtime/probe497-amd-20261125-121238.log` |
| 多实例隔离与 so\*\* 目录统一（含实测数据） | `arm64/evidence/MULTI_INSTANCE_20261125.md`、`packaging/MULTI_INSTANCE.md` |
| 流媒体分流：NF 各节点能力矩阵与 TW 修复 | `arm64/evidence/STREAM_NF_MATRIX_20261125.md`、`_ops/routes_tw_patch.toml` |
| 部署流程 + 配置与原版模板一致性（两台 7/7 PASS、41 键、probe 3/3） | `amd64/evidence/DEPLOY_CONF_PARITY_20261126.md`、`_ops/test_conf_parity.py` |
| 交互层/逻辑层 10 个缺陷与回归（菜单只执行一次、退出码、backup/rollback） | 同上 §5、`_ops/test_console_ux.py`、`_ops/test_console_e2e3.sh` |
| nfu / so\*\* 生态兼容 + 路由守卫 + watchdog（含停摆演练） | `arm64/evidence/NFU_COMPAT_20261125.md`、`packaging/routes-guard.py`、`packaging/soco-watchdog.py` |
| 安装/更新与多实例管理脚本 | `packaging/install-soco.sh`、`packaging/soco-multi.sh`、`packaging/soco@.service` |