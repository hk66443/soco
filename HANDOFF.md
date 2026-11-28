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
| 11-27 清空后重装 | **修复 2 个缺陷后 7/7 PASS**：`soco` active `:49989`、sink `38443`、watchdog 统一版（0 假重启）、`doctor` 16/16 ✔、`probe 3/3` → [amd64/evidence/DEPLOY_REGRESSION_FIX_20261127.md](amd64/evidence/DEPLOY_REGRESSION_FIX_20261127.md) |
| 11-28 审计第 2 轮 | **再修 8 个缺陷后 `doctor` 17/17 ✔**：`bash -n` 7 个 shell 全 OK、授权 sink 改线程化（打 443 证书校验 **0.02 s** 失败）、routes 守卫**补装**并 active、`probe 3/3`、`users` 297=297、**soco PID `506373` 未变**（`NRestarts=0`）→ [amd64/evidence/CLEAN_INSTALL_CONSOLE_HARDENING_20261127.md](amd64/evidence/CLEAN_INSTALL_CONSOLE_HARDENING_20261127.md) 第 81/82 条 |

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
| 11-27 同步升级 | console `0d312ad9…` → **`cfe40087…`**（一键命令覆盖更新，0 s）；`soco-watchdog.py` 换成统一版 `f544137a…`（`probe_ok type=vless server_port=49999`）；`doctor` 16/16 ✔、`conf check` 41/41、`probe 3/3`、`gate` 全 ✔、PID 2543124 全程未变 |
| 11-28 审计第 2 轮 | console `cfe40087…` → **`17fc0f22…`**（含 17 项 doctor）；`bash -n` 7 个 shell OK、sink 线程化（443 证书校验 **0.01 s** 失败）、routes 守卫**补装**并 active（`routes file missing, skip` —— routes.toml 仍是待办 17/79）、`probe 3/3`、`users` 297=297、**PID `2587316` 全程未变**（`NRestarts=0`） |
| 复盘 | 见 [arm64/evidence/ARM_STREAM_ROUTES_FIX_20261123.md](arm64/evidence/ARM_STREAM_ROUTES_FIX_20261123.md) |

### 1.2c 部署流程与配置一致性复测（2026-11-26）

| 项 | AMD | ARM |
|---|---|---|
| `so**.conf` 改前 | 10 行（缺 31 个原版键） | 41 行（原版模板，`log_level=debug`） |
| `so**.conf` 改后 | **63 行 / 41 键，与原版模板逐行一致** | 同，`log_level=info`（2026-11-28 起，AMD 也是） |
| `so-console install` | **7/7 PASS**（端口就绪 10 s） | **7/7 PASS** |
| 用户 / 握手 | 498 = 面板 498；probe **3/3** | 498 = 面板 498；probe **3/3** |
| 分流 routes | 0 条（本机本就空模板） | **0 条（2026-11-28 清空重装后整个文件丢失，见 §7.2 第 17 条更正）** |

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
├── soco-watchdog.py        watchdog（统一版：按 server_type 自适应 SS2022 / VLESS+REALITY；PROBE_EVERY/FAILS_TO_RESTART/PREEMPT_SECONDS 由 unit 注入）
├── soco-mesh.py            mesh 中继（已停用，AMD 上遗留孤儿实例 2026-11-25 已清）
└── licence/{sink.py,sink_38443.py,cert.pem,key.pem,sink-redirect.nft}   本地授权端点（sink，38443）

/etc/systemd/system/
├── soco.service            主实例（2026-11-25 起不带 -c，默认读 /etc/so**/so**.conf）
├── soco@.service           多实例模板（-c /etc/so**/%i.conf，实例名 = 配置文件名）
├── soco-watchdog.service   PREEMPT_SECONDS=0 / FAILS_TO_RESTART=3 / PROBE_EVERY=30（amd）
├── soco-licence-sink.service  0.0.0.0:38443 sink（Restart=always）
├── soco-sink-redirect.service nft: 127.0.0.1:443 dnat → 38443（443 已让出，可跑网站/证书）
├── soco-routes-guard.path/.service  routes.toml 守卫（nfu 覆盖后自动补回 Netflix/OpenAI → TW）
├── soco-watchdog.service   真实握手探活（协议自适应），连续 3 次失败重启（2026-11-27 起两台同用统一版）
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
| `ask()` / `confirm()` 里 `raise SystemExit(130)` | 管道、CI、`curl … \| bash` 下整个控制台被**静默杀掉**，没有任何提示 | 抛 `Cancelled`：交互菜单回菜单、非交互打印「已取消」并退出 130 |
| 多机场实例用主实例端口判断"起来了没" | 面板不可达时实例照样报 PASS —— 实际没有端口，僵尸进程白占 ~62 MB | 实例必须从面板拉 `server_port`；拉不到 → `[5/7]` FAIL + 自动删半截 conf（2026-11-27 修） |
| `so-console` 里改「步骤顺序」只改一半 | `deploy()` 第 4 步读了第 5 步才赋值的 `sink_up` → 每次 install 必崩 `UnboundLocalError`，单元永远不落地（**2026-11-27 现网事故**） | 改步骤顺序后跑一次真 install；别把校验放在被校验对象启动之前（见 [amd64/evidence/DEPLOY_REGRESSION_FIX_20261127.md](amd64/evidence/DEPLOY_REGRESSION_FIX_20261127.md)） |
| 把 `packaging/soco-watchdog.py` 当成"通用 watchdog" | 它原是 VLESS/REALITY 专用版，装到 AMD 的 SS2022 节点上探针永远失败 → 每 2 分钟重启一次 soco | 用统一版（按 `server_type` 自适应，sha256 `f544137a…`）；旧版留档 `packaging/soco-watchdog-vless-legacy.py` |

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
- **一键部署回归修复（2026-11-27 UTC）**：全量清空后用公开仓库一键命令重装时，
  ① `so-console` `deploy()` 前向引用 `sink_up` → install 必崩在 `[4/7]`、单元永不落地；
  ② `packaging/soco-watchdog.py` 是 VLESS 专用版却被装到 AMD 的 SS2022 节点 → 探针永远失败、
  每 ~2 分钟重启一次 soco。两处已修（console sha256 `54064c77…`、watchdog 统一版 `f544137a…`），
  修后 `install` 7/7 PASS、`probe 3/3`、`doctor` 16 项全 ✔、watchdog 100 s 观察 0 重启
  （[amd64/evidence/DEPLOY_REGRESSION_FIX_20261127.md](amd64/evidence/DEPLOY_REGRESSION_FIX_20261127.md)）
- **控制台加固 + 清空重装实测（2026-11-27 晚）**：AMD 全清（单元/目录/端口/nft/hosts 全 0）→
  公开一键命令 **11 s** 拉起（165 文件 + release 二进制 c463791a/2f60b5f8）→ 控制台 `install` 7/7、
  `doctor` 16/16、`probe 3/3`、跨 600 s 闸门（uptime **1577 s**、同 PID、key_err=0）；
  同时修掉控制台 **7 个真问题**（EOF 静默杀进程、`conf check` NameError、`logs 20` 语义、
  `rollback` 非 tty 挂住、实例僵尸误判 PASS、`inst remove` 非 tty、`service` 乱写/菜单 `?`/大写退出）
  （[amd64/evidence/CLEAN_INSTALL_CONSOLE_HARDENING_20261127.md](amd64/evidence/CLEAN_INSTALL_CONSOLE_HARDENING_20261127.md)）
- **第十轮控制台入口（2026-11-28）**：`uninstall [--purge] [--yes]` + sink-redirect 单元
  `priority dstnat → 100`，console `c5693a8b…` 已推送（`0334789`）；两台一键命令 1 s 拉齐、
  `doctor` 全通过 / `probe 3/3` / `gate` ✔，非交互 `uninstall` 两台均 rc=2 且什么都没动。

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
4. ~~**sink 健壮性**~~ **（2026-11-28 完成，`9fa1ccf`）**：`soco.service` 与 `soco@.service` 都加了
   `After=` + `Wants=soco-licence-sink.service`（sink 先起、soco 后起），避免 sink 没起来时撞 600 s 检查；
   **没有**给 sink 加 `PartOf=soco.service` —— 那会在主实例停止/重启时把 sink 一起带走，
   正在跑 `soco@<实例>` 的节点就断授权。console 模板同步改（三份副本 `8fefcc68…`），单测 +5 项（26/26）；
   两台现网单元已按同一形状补齐（备份 `soco**.bak.202611280*`、`systemd-analyze verify` rc=0、
   `daemon-reload` 后 `systemctl show soco -p Wants` 已含 sink），**未重启任何服务**：
   PID 未变、`probe 2/2`、`doctor` 全部通过。
5. **ARM 真机复测**：已完成（2026-11-23）。`ARM_IP` 上 soco 连续运行 ~2 h、`NRestarts=0`、
   真实 VLESS/REALITY 链路与 10 条 NF 解锁分流均正常，**未见 600 s 数据面闸门**；
   另修掉 `routes.toml` 加载失败的静默故障（详见 [arm64/evidence/ARM_STREAM_ROUTES_FIX_20261123.md](arm64/evidence/ARM_STREAM_ROUTES_FIX_20261123.md)）。
6. **出正式 release**：`packaging/` 里是旧包装（install/verify/manifest/checker），若要发布需要把本轮 amd64 产物与 sink/hosts 方案纳入 manifest。
7. **多实例并发压测**：`soco@.service` 已补 `SOCO_INSTANCE=%i` + `WorkingDirectory`，但本轮只做单实例复测。
8. ~~**公开仓库 `_push/` 必须重新推送（阻塞项）**~~ **（2026-11-27 已完成，现 HEAD `e76e75d`）**：
   - `9d18377`：控制台交互加固（EOF 不再静默杀进程、`conf check` NameError、`logs 20` 语义、
     实例僵尸误判 PASS、`inst remove --yes`、`conf get`、菜单 `?`/大写退出）
   - `e76e75d`：第二轮（`install.sh` 改为**每次拉最新并覆盖**、部署互斥锁、备份默认保留 3 份、
     `rollback --file` + 解包路径白名单、`/etc/hosts` 不可写判 FAIL、`inst remove` 清私有目录、`.gitignore` 加密钥规则）
   - 远端 `main` = `e76e75d`；`raw.githubusercontent.com/hk66443/soco/main/console/so-console`
     = `5ded1556…`（82,731 B）、`packaging/soco-watchdog.py` = `f544137a…`
   - **存量机器现在能自动更新了**：重跑一键命令会打印「覆盖更新程序文件」，实测把 console 降级成旧版后
     重跑 **1 s** 就回到 GitHub 版本，`/etc` 下配置不动（要保留本地改动用 `SO_SKIP_PULL=1`）
9. **第三、四轮边界修复已推送（`4022e1a`，2026-11-27 深夜）**：`console/so-console` = `87cb2051…`
   （92,931 B）、`_ops/probe_many.py` = `16f21b03…`，`raw.githubusercontent.com/hk66443/soco/main/` 已核验一致。
   共 22 项：坏 routes 的 traceback、`logs` 不存在 unit、`probe` 非法/越界索引、`conf keys` 缺配置、
   TLS 协议缺 `--cert-mode`、`verify` 返回码、`gate` 主服务检查、`service restart` 等端口就绪、
   菜单 backup 参数、**`so**_key` 幂等**、**实例端口冲突不再借主实例 listener 判 PASS**、
   **`[6/7]` 失败返回非 0**、`version` 命令、`probe_many` 并发端口隔离 + `SO_PROBE_CONF` + 跑完清理、
   `human_size` 去 du、`status` 内存可读化。
   AMD 已装 v15；ARM 未装（跑一次一键命令即更新到同一版）。
   详见 [amd64/evidence/CLEAN_INSTALL_CONSOLE_HARDENING_20261127.md](amd64/evidence/CLEAN_INSTALL_CONSOLE_HARDENING_20261127.md) §10。
10. **一键更新现在会同步运行期脚本（`92dd57d`）**：`install.sh` 拉完项目后把
    `probe_many.py` / `soco-watchdog.py` / `routes-guard.py` / `licence/sink.py` 同步进 `bin_dir`
    （旧文件备份为 `.bak.<ts>`，内容相同则跳过），watchdog 需 `systemctl restart soco-watchdog` 生效；
    `probe_script()` 也改成按 mtime 取最新那份。实测两台重跑一键命令后
    `probe_many.py` 都从 `dff13b34…` 变成 `16f21b03…`，console 均为 `27b6d0da…`。
11. **第五轮（磁盘/临时目录/完整性，**未推送**）**：`console` `e4d58cc8…`、`probe_many.py` `adcba664…`、
    `install.sh` `ffa95ab3…`、`licence-sink.py` `e4471443…`。关键三条：
    ① `install.sh` 临时目录从 `/tmp`（这台是 **tmpfs 482 MB**）改 `/var/tmp` + 下载前空间预检；
    ② 加了 release `SHA256SUMS` 校验（该文件 CRLF，需先 `tr -d '\r'`）；
    ③ 拉项目时 `tar --exclude='./install.sh'` —— 以前在 `/root/so` 里 `bash install.sh`
    会在执行途中覆盖自己，后半段行为错乱。
    两台（AMD/ARM）已手动对齐到上述四个 sha；`_push/` 未同步、未 commit、未 push。
    详见 §10（第 39–48 条）与 [amd64/evidence/CLEAN_INSTALL_CONSOLE_HARDENING_20261127.md](amd64/evidence/CLEAN_INSTALL_CONSOLE_HARDENING_20261127.md)。
12. **第六轮（回滚安全 / watchdog 端口，**未推送**）**：`console` `4e1e9184…`、`probe_many.py` `de7cb86a…`、
    `soco-watchdog.py` `40eff5b8…`、`install.sh` `bdaf9f2c…`。要点：
    ① `rollback` 白名单改为规范化路径（挡 `..`/绝对路径），并要求备份含 ≥1 MB 的 `soco`
    —— 以前一个 4 字节 soco 的 tar 就能覆盖主程序（本轮真踩了，靠 `SO_FORCE_BIN=1` 恢复）；
    ② watchdog 的 socks 端口改为动态挑选（遗留 sing-box 占 11009 时探针永久失效），marker 端口被占时明确 rc=1；
    ③ `probe_many` 缺配置键给人话；
    ④ `install.sh` 的 git clone 回退改成先克隆到 `/var/tmp` 再覆盖（不再先删 `$DEST`）。
    两台已同步到上述四个 sha（AMD py3.13 / ARM py3.9 都做了回滚安全实测）；`_push/` 未同步、未 commit、未 push。
    详见 §10 第 49–56 条。
13. **第七轮（子进程回收 / 探针输入校验，**未推送**）**：`console` `bb72a3fa…`、`probe_many.py` `6e074092…`、
    `soco-watchdog.py` `09217727…`。要点：
    ① watchdog 退出时收掉自己拉起的 sing-box（以前 `systemctl restart` 会留下孤儿占着 socks 端口 + 80 MB）；
    ② `probe_many` 对「面板返回 HTML/非 JSON」「vless 缺 REALITY public_key」「ss 缺 cipher/server_key/uuid」给一句人话；
    ③ `backup` 排除 `/etc/so**/instances/` 与 access_log。
    两台已同步到上述三个 sha，实测 watchdog 重启后旧 sing-box pid 消失、11009 回收、`probe` 3/3。
    `_push/` 未同步、未 commit、未 push。详见 §10 第 57–62 条；新增单测 `tools/test_probe_units.py`（9 项）。
14. **第八轮（编码事故修复 / 权限收紧，**未推送**）**：`console` `217d821d…`、`probe_many.py` `5abd2cba…`、
    `soco-watchdog.py` `898f50d5…`。要点：
    ① **事故**：上一轮用 PowerShell `Set-Content -Encoding UTF8` 改 watchdog，把中文写成双重编码
    （857 处 mojibake），两台生产跑的都是乱码版 —— 已用 write 重建并重新部署，三文件 `mojibake=0`。
    **以后改源码只用 edit/write，别用 Set-Content 覆写 UTF-8 源码。**
    ② `backup` 产物 `chmod 600`（内有 webapi_key / so\*\*_key / licence 私钥）；
    ③ `probe_many` 临时目录 700、配置 600；
    ④ socks 端口搜索范围 20 → 50。
    两台已同步并验证（ARM py3.9 也正常）。`_push/` 未同步、未 commit、未 push。详见 §10 第 63–66 条。
15. **第九轮（名字冲突 / 暴露面 / 重启风暴，**未推送**）**：`console` `0e35c9ed…`、`soco-watchdog.py` `d2dc74e7…`。
    ① `inst new so**` / `install --name so**` 会覆盖 `/etc/so**/so**.conf`（主配置）→ 现在 rc=2 拒绝；
    ② licence sink 从 `0.0.0.0:38443` 改成 **`127.0.0.1:38443`**（模板 + 两台生产 unit 都已改，`ss` 已确认），
    只服务本机 nft dnat，不再对外开端口；
    ③ watchdog 连续重启 ≥5 次后停手（`restart_storm`），探活恢复即清零，避免把服务来回掐断。
    两台已同步；`_push/` 未同步、未 commit、未 push。详见 §10 第 67–69 条。
16. ~~**⚠️ 推送前不要跑一键命令**~~（已随 `12b5b17` 推送解除）：`install.sh` 的"同步运行期脚本"以
    `${DEST}`（`/root/so`）为源，未推送时跑一键命令会把 `bin_dir` 的脚本退回 GitHub 旧版。
    **现在 GitHub `main` = `12b5b17`，`/root/so` 与 `bin_dir` 两处都已是新版**：实测两台重跑一键命令
    0–1 s、打印「运行期脚本已是最新」，五个文件 sha 全一致
    （console `0e35c9ed…`、probe_many `5abd2cba…`、watchdog `d2dc74e7…`、install.sh `bdaf9f2c…`、sink `e4471443…`）。
    以后顺序照旧：**先推 `_push` → 再跑一键命令**。
17. **ARM 全清 + 一键重装实测（2026-11-28）**：ARM 上 soco/so\*\* 全部清空（单元 0 / 目录 0 / 端口 0 / nft 0 /
    hosts 0），再跑公开一键命令 **3 s** 拉起（164 文件 + release 二进制 `549ef746`/`f5fc39df`），
    控制台 `install` 7/7、`doctor` 16/16、`probe 3/3`、`gate` 全 ✔。
    过程中修掉 3 个真问题（详见 §10 第 72–74 条）：
    ① **控制台新增 `uninstall [--purge] [--yes]`（菜单 16）** —— 停服务/删单元/删目录/清 hosts/nft，
    默认保留 `/etc/so**` 配置；
    ② **ARM 的 nftables 是 v0.9.8，不认 `priority dstnat`** → 模板与两台 unit 改成 `priority 100`
    （AMD v1.1.3 两种都行）；
    ③ 清空会连 `sing-box-probe` 一起删，重装后 `[7/7]` 会 SKIP —— 按提示补装即可。
    注意：**ARM 上流媒体分流暂不部署**（用户自己弄）。
    **2026-11-28 复核更正**：清空重装后 `/etc/so**/routes.toml` **已经不在了**（目录 0 文件、`routes status` 直接报
    「没有 routes.toml」、`routes-guard.path/service` 也没有），所以现在是**一条分流都没有**，
    所有站点都走默认出口（`ARM_IP` / DE）—— 这不是"漏配几个站点"，是整份分流配置丢了。
    恢复源在本地：`_ops/routes-remote-20261123.toml`（961 行 / 26 KB，含 `enable=true` 与各 region 路由）
    + `_ops/routes_tw_patch.toml`（NF/OpenAI → `node-tw:20558`，插在 `enable=true` 之后）。
    **用户明确说先不动**，等他要的时候再恢复。
18. **第十轮推送与双机同步（已推送 `0334789`，2026-11-28）**：`console/so-console` = `c5693a8b…`
    （103,951 B，`raw.githubusercontent.com/…/main/console/so-console` 已核验一致）。两点：
    ① 新增 `uninstall [--purge] [--yes]`（菜单 16）：停+禁用所有单元（含 `soco@<实例>`）、
    按 `/proc/<pid>/exe` 杀残留（不用 `pkill -f`，模式串会把自己也杀掉）、删单元/目录/日志/临时目录、
    清 hosts 4 条、删 `ip soco_sink` 与 `ip nat`；**默认保留 `/etc/so**`**，`--purge` 连配置一起删；
    非 tty 必须 `--yes`，否则 rc=2 且什么都不做；
    ② sink-redirect 单元模板 `priority dstnat` → **`priority 100`**（ARM 的 nft **v0.9.8** 不认符号优先级，
    AMD v1.1.3 两种都认）。
    实测：两台重跑一键命令 **1 s**、`/root/so/console/so-console` 都到 `c5693a8b…`，
    `version` → `so-console 2.1 (arm64, python 3.9.2)` / `(amd64, python 3.13.5)`，
    `doctor` 全部通过（当时只有 `log_level=error` 的「本地人数不可读」提示；2026-11-28 已切 `info`，见第 20 条）、`probe 3/3`
    （AMD `type=ss` / ARM `type=vless`）、`gate` 闸门已被压制、4 个单元 active、**PID 未变、NRestarts=0**。
    非交互 `uninstall` 两台都 rc=2、units 4→4、二进制仍在。licence 域名打 443 是完整 TLS 握手到本地
    sink（ARM 用 `priority 100` 也通，证明等价可用）。AMD 现网 unit 已对齐成 `priority 100`
    （内核里已有链仍显示 `dstnat`，语义等价，下次重建即 100）。
    **顺序照旧：先推 `_push` → 再跑一键命令**；不推就跑会退回旧版（第 10 条踩过，本轮又验证了一次）。
19. **公开仓库文档仍停在脱敏旧版（待单独一轮，先别直接拷）**：`_push/HANDOFF.md`（286 行）仍是
    11-25 的脱敏版（`so**→so**`、IP 换成占位），`_push/amd64/evidence/` 里
    没有 11-26 之后的证据（`_push/CONSOLE.md` 已在 `545cc30` 补上 `uninstall` 一节，脱敏风格一致）。
    本轮只推代码 + 这份 CONSOLE 文档，本地文档（根 `HANDOFF.md`、`amd64/evidence/*`）不再镜像；
    **不要**把本地版整份拷进 `_push/` —— 里面有面板 URL 与两台机器 root 口令。
20. **日志级别切 info + AMD 链对齐（2026-11-28）**：
    ① 两台 `so**.conf` `log_level=error → info`，单元 `LogLevelMax=warning → info`
    （journal 侧也会过滤，不改这一行就算 info 也读不到），各重启一次 soco
    （PID：AMD `467626→506373`、ARM `2577047→2587316`，`NRestarts=0`，端口 10–20 s 就绪）；
    `probe 3/3`、`doctor` 全通过，`users` **本地 297 = 面板 297（实时）**，两台一致。
    控制台配套改动（`9b8ade1`，console `a0465a52…`）：`install/inst new --log-level error|info`、
    `write_conf` 保留客户已选级别（重装不会把 info 压回 error）、单元模板 `LogLevelMax={log_max}`、
    `doctor`/`conf check` 接受 info，单测 26 → **33 项**。
    ② AMD 内核里那条 nat 链删掉重建：`priority dstnat → 100`（与单元、ARM 一致）；重建后 licence 域名走 443
    仍是完整 TLS 握手到 sink，`probe 2/2`、soco PID 未变。
    ③ 顺带核实：ARM 的 `routes.toml` 已丢（见第 17 条更正），用户说先不动，本轮未改。
    日志量：一台 60 s 一条 `current user num` 加连接级 INFO，实测 1 分钟约 1–3 KB/台，磁盘可忽略。
21. **脚本审计第 1 轮（`4713412`，2026-11-28）**：console `4810dda2…`、`probe_many.py` `c237dccf…`、
    `soco-watchdog.py` `b81b0ac5…`。查出并修掉 8 个真缺陷：
    ① `uninstall` 原本 `nft delete table ip nat` —— docker / iptables-nft / 防火墙的 NAT 链也在
    同名的 `ip nat` 表里，等于卸载时顺手打断同机容器网络；**现在只删 `ip nat redir` 链**
    （以及遗留的 `ip soco_sink` 表），链若被别的组件重建会明确告警；
    ② `uninstall` 原地重写 `/etc/hosts`，中途被杀 = 空文件（DNS 全挂）→ 改「临时文件 + `os.replace`」，
    并且只删「去掉注释后最后一个字段是授权域名」的行（以前注释里出现过的域名也会被删）；
    ③ `uninstall` 对猜出来的单元名无脑 `systemctl stop`，刷一屏 `Unit … not loaded` → 只动真实存在的单元；
    ④ `doctor` 在 `log_level=info` 刚重启时因「还没有 INFO 行」直接判 FAIL → 改成等待提示（不是故障）；
    ⑤ `probe_many` 的 socks 端口用 `PORT_BASE + i`，两个 probe 并发时端口段重叠 → 随机 FAIL；
    改成逐个 `bind` 试（`pick_port`）；
    ⑥ `probe_many` 固定 `sleep 2.0` 等客户端 → 改成轮询端口就绪（`wait_port`，最多 6 s）；
    ⑦ `probe_many` 的清理不在 `finally`：配置非法（SystemExit）或 Ctrl-C 会留下 sing-box 进程
    和含 `server_key`/`uuid` 的临时目录 → 已把终止进程 + 删目录放进 `finally`；
    ⑧ `probe_many` vless 分支 `user['uuid']` 缺键直接 KeyError 刷 traceback → 改成一句人话；
    ⑨ watchdog 的 `restarts` 只在 storm 时清零：几小时前那 1–4 次会累积到 `STORM_LIMIT`（5），
    真正故障时反而**停止重启** → 任何一次探活成功都清零；`restart()` 也不看 systemctl 返回码、
    可能自己抛异常 → 现在记 `restart_failed` / `restart_error` 并继续跑。
    单测：console 39 项（+8：只删链 / hosts 原子写与精确匹配）、probe 13 项（+4）；pyflakes 干净。
    两台已同步（一键命令 + 只重启 watchdog）：`probe 3/3`、`doctor` 全通过、`probe_ok`、soco PID 未变。
22. **脚本审计第 2 轮（2026-11-28，装机器/守卫/授权 sink 这一面）**：routes-guard `6a499fee…`、
    licence-sink `0c0d0b17…`、一键 `install.sh` `526b36e9…`、`packaging/uninstall.sh` `4501b97d…`、
    `soco-multi.sh` `714783f7…`、`install-soco.sh` `cb6bbab8…`、console `17fc0f22…`。修掉 7 个真缺陷：
    ① **`routes-guard` 取错密码**：原来是「全文第一个 `password=`」，客户把 trojan / vmess 出站排在
    ss 前面时（真实模板里 8 个 ss 出站共用一个 UUID，但顺序不是保证的），补丁会拿到别的出站的密码 →
    注入的 ss 出站必然认证失败 → **分流静默失效**（正是第 17 条那个「静默 0 条」的形态）。
    现在按 `[[routes.Outs]]` 分块，只从 `type="ss"` 的块里取 password；`has_ss_outbound` 仍全文匹配
    （它只决定「跳过 vs 等下一轮」，宁可多等也不要漏打）；
    ② **授权 sink 会被一个卡住的连接拖死**：原来单线程 accept + 逐个握手（每个 3 s 超时），
    只要有客户端连上不发数据（扫描器 / 半开连接 / 误连），后面的连接全堵着 —— so\*\* 每 600 s 的
    授权检查正好跟着「挂住」，落进 600 s 闸门的停摆形态。改成每连接一个线程 + 64 路信号量，
    accept 后槽位满就直接 close（仍是「快速失败」）；握手失败/连接已死都不再往 journal 甩 traceback；
    ③ **一键 `install.sh` 会无声退出**：`find … | head -1` 在 `set -o pipefail` 下，head 提前关管道
    会让 find 吃 SIGPIPE（141）→ 整个脚本没提示就退出。改 `find … -print -quit`；解包/复制失败的
    分支原来会漏一个 `/var/tmp/so-src.*`（含 30 MB 项目包），现在所有临时目录由 `trap` 统一收；
    缺 `python3` 也是等到最后 `exec` 才报错，改为开工前就拦（这台机器的控制台是 python 脚本）；
    ④ **`soco-uninstall`（`packaging/uninstall.sh`）只拆了一半**：只停 `soco.service`/`soco@.service`，
    watchdog / 授权 sink / sink-redirect / routes-guard 全留着，`/etc/hosts` 4 条与 nft 链也不清 ——
    卸完之后 **DNS 仍把 4 个授权域名指向 127.0.0.1**（客户机器上别的软件跟着解析失败）、38443 还占着、
    watchdog 还在把 soco 拉回来。现在按序停（watchdog 先掐）、只删本项目单元与 `.wants` 链接、
    hosts 临时文件 + `mv` 原子写回且只删本项目域名、nft 只删 `ip nat redir` 链与遗留 `ip soco_sink` 表、
    备份清单的 `|| echo` 死分支一起修掉；
    ⑤ **`soco update` 漏临时目录**：`mktemp -d` 之后从不删，每更新一次就在 /tmp 留一份含新二进制
    （甚至 libsoco）的目录；`soco uninstall` 同样只删了 `soco.service`/`soco@.service` 两个单元、
    不清 hosts/nft/sink；`set_kv` 算好了 `esc` 却没用，值里带 `&` 或 `|` 会把配置写坏（现在用上了）；
    ⑥ **`install-soco.sh` 失败分支把 80 MB 新二进制留在 /tmp**（`--bin` 下载后 `-v` 校验失败即 exit）→
    同样改 `trap` 收；
    ⑦ **`so-console install` 不装 routes 守卫，`uninstall` 却会删**：干净装机后 nfu 一重生成
    `routes.toml`，Netflix/OpenAI 的 TW 分流就被冲掉且**不报错**（历史上踩过一次）。现在装
    `soco-routes-guard.service` + `.path` 并 `enable + start`（`.path` 只 enable 不算 active，不 start
    就没人盯文件），`doctor` 增加一行「routes 守卫 active」（**16 → 17 项**）。
    单测：新增 `tools/test_routes_guard_units.py`（31 项：分块取密码、trojan 在前、幂等、重试/跳过、
    tmp 不残留）、`tools/test_sink_units.py`（14 项：`--listen` 解析、槽位归还、握手失败/成功都关连接、
    死 socket 不漏异常）；console 39 → **45 项**（+6：守卫单元与 `.path` 监听路径）。四套共 103 项全绿，
    pyflakes 干净。
    **部署实测（两台，`cd5d6e4` + `82410df`）**：`bash -n` 7 个 shell 全 OK、`py_compile` OK；
    文件 hash 与 `_push` 逐字节一致（console `17fc0f22…`、`install.sh` `70c91ae7…`、
    routes-guard `6a499fee…`、sink `0c0d0b17…`、uninstall `4501b97d…`、multi `714783f7…`、
    install-soco `cb6bbab8…`，`bin_dir` 里的 `routes-guard.py` / `licence/sink.py` 同步刷新）；
    只重启 `soco-licence-sink`（38443 LISTEN ok，打 443 证书校验 **0.01–0.02 s** 失败 = 快速失败），
    **soco PID 未变**（AMD `506373` / ARM `2587316`，`NRestarts=0`）；
    `doctor` **17/17 ✔**、`probe 3/3`、五单元全 active、`users` 本地 297 = 面板 297。
    顺带发现并补上第 8 个：**两台机器上 `soco-routes-guard.path/.service` 其实都不存在**
    （HANDOFF §3 写的"已在"是重装前的状态），`doctor` 新加的那一行立刻把它照出来；已按
    `packaging/` 里的单元补装并 `enable --now`，手工跑一次守卫 = `routes file missing, skip`
    （两台 `routes.toml` 仍是第 17/79 条那个待办，用户说先不动）——守卫已武装，等文件回来就生效。
    另修 `install.sh` 的自覆盖判定（`82410df`）：原来一律 `--exclude=./install.sh`，用
    `bash <(curl …)` 装机时 `/root/so/install.sh` **永远是第一次那份**（实测 pull 完还是
    `bdaf9f2c…`），现在只有「正在执行的就是 `$DEST/install.sh`」时才排除，否则照样覆盖
    → 实测 pull 完 `70c91ae7…` 与远端一致。

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