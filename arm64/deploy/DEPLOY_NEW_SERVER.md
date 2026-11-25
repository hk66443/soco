# 在新 arm64 服务器上部署 soco

> 目标：一台全新的 aarch64 机器，跑起 **soga v2.18.1 + 43 字节破解 + 面板适配层**，对外提供 VLESS + REALITY 节点。
> 配套一键脚本：[`deploy_arm64_soco.sh`](deploy_arm64_soco.sh)（已在本轮线上机做过 `bash -n` + dry-run + 反例拦截验证）。

---

## 0. 先搞清楚要传什么

| 角色 | 工程包里的路径 | 装到 | SHA256 | 大小 |
|---|---|---|---|---|
| 主程序（破解版） | `arm64/bin/soga-arm64.crack-soga10` | `/usr/local/soco/soco` | `3733296060ddb4047495ea0eb67e0449eee07e8ce375a7e969b28d36773f1d3a` | 91,634,064 |
| 面板适配层 | `arm64/bin/libsoco-arm64.so` | `/usr/local/soco/libsoco.so` | `f5fc39df4f988cb4a8eb4c683f914a07d5836b1807720aab7b010736cf83293a` | 19,336 |

### 绝对不要用的那一份

| 文件 | SHA256 | 为什么不能用 |
|---|---|---|
| `arm64/bin/soco-arm64-legacy-delivery` | `1b280c88…39e171` | **98 区域 / 174 字节**重补丁版。实测：REALITY 通过、用户认证通过，但**从不 dial**，一条流量都不通（日志只有 `access address` + `handle vless end`，没有 `tcp direct relay`） |

脚本会硬校验两个 hash，传错直接拒绝落地。

### 原版 soga 要不要装？

**运行不需要。** `soga-arm64.crack-soga10` 就是**完整的可执行程序**（与原版同尺寸 91,634,064 B，只差 43 字节），不是补丁文件，不需要「先装原版再打补丁」。

| | 需要装 | 说明 |
|---|---|---|
| 运行 soco | ❌ | 只装上面那两个文件 |
| 保留原版做回滚/取证 | ✅ 建议存档，**不装、不启服务** | 放 `/root/backup/soga-arm64.original`（`3c42ba62…`）或留官方 `official-2.18.1-arm64.tar.gz` |
| `soga.service` | ❌ | 只需要 `soco.service` 一个 unit；两个都启会抢同一个端口 |
| `/etc/soga/` 下的 `blockList`、`whiteList`、`dns.yml`、`routes.toml` | ✅ **必须有** | 主程序启动时会读，缺失会告警/启动失败。脚本已按官方包原样补建（都是注释占位，各 12–56 字节） |
| `/etc/soga/geoip.dat`、`geosite.dat` | 可选 | 只有 `routes.toml` 里用到 geoip/geosite 规则时才需要 |

⚠️ 别把原版覆盖到 `/usr/local/soco/soco`：那样会丢掉破解属性（用户上限退回 88）。

### 为什么必须用「这两个文件配对」

适配层 `libsoco.so` 里有硬编码：

```c
#define NATIVE_BODY 0x33292e4UL   /* 原生 pull_users 入口 */
```

它会在初始化时校验该入口的字节，不匹配就打印 `native pull_users entry mismatch` 并放弃 hook（→ 用户数退回 soga 原生上限 88）。所以**适配层与主程序必须是同一份构建**，不能拿别的 soga 版本配。

> ⚠️ **适配层只解除「加载上限」，没解除「转发闸门」**（2026-11-23 实测）：
> 面板用户数 **> 88** 时，用户能被加载（`add user` 100 次），但数据面整体关闭 ——
> 认证通过、不加 dial、客户端 000；88 以内（含 88）完全正常。
> 所以**单实例不要挂超过 88 个用户**。要更多用户请用多实例分片（每实例一个 `node_id` + 独立端口），
> 细节见 [../evidence/ARM_88_USER_LIMIT_FINDINGS_20261123.md](../evidence/ARM_88_USER_LIMIT_FINDINGS_20261123.md)。

---

## 1. 前置条件

### 服务器

- 架构 **aarch64**（`uname -m` 确认）；x86_64 走 `amd64/` 那套，机制完全不同（见文末）
- 系统：Debian 11/12/13 或 Ubuntu arm64 均可（主程序是 Go 静态 + libc；适配层只依赖 `libcurl.so.4` / `libjson-c.so.5`）
- root 权限、能出网（要访问面板 API）
- 依赖（脚本会自动查 `ldd` 并补装）：
  ```bash
  apt-get install -y libcurl4 libjson-c5 ca-certificates
  ```

### 面板（必须先做，否则机器上没有端口和 REALITY 密钥）

在面板里为该机器建节点，参数：

| 项 | 值 |
|---|---|
| 节点类型 | `vless` |
| 传输 | `tcp` |
| TLS | `reality`（面板会自动生成密钥对） |
| flow | **`xtls-rprx-vision`**（服务端强制，客户端留空会被拒：`can not use new vless conn err: can not use empty flow`） |
| server_name | 例如 `www.apple.com` |
| 端口 | 面板分配（如 49999） |

建完拿到三样东西：**`node_id`**、节点的 **`webapi_key`**、**`soga_key`**。

---

## 2. 传文件

### Windows（工程包在本机）

```powershell
$d = "C:\Users\adminuser\Downloads\soco\nodetest"
& "$d\bin\pscp.exe" -batch -pw '<root密码>' `
  'C:\Users\adminuser\Downloads\soco\arm64\bin\soga-arm64.crack-soga10' `
  'root@<新服务器IP>:/root/soco/'
& "$d\bin\pscp.exe" -batch -pw '<root密码>' `
  'C:\Users\adminuser\Downloads\soco\arm64\bin\libsoco-arm64.so' `
  'root@<新服务器IP>:/root/soco/'
& "$d\bin\pscp.exe" -batch -pw '<root密码>' `
  'C:\Users\adminuser\Downloads\soco\arm64\deploy\deploy_arm64_soco.sh' `
  'root@<新服务器IP>:/root/soco/'
```

### Linux / macOS

```bash
mkdir -p /root/soco
scp arm64/bin/soga-arm64.crack-soga10 arm64/bin/libsoco-arm64.so \
    arm64/deploy/deploy_arm64_soco.sh root@<新IP>:/root/soco/
```

### 从现有那台 ARM 机器直接拿（最省流量，同城/内网更快）

```bash
# 在新机器上执行
scp root@130.61.141.143:/usr/local/soco/soco       /root/soco/soco
scp root@130.61.141.143:/usr/local/soco/libsoco.so /root/soco/libsoco.so
```

> 注意：从线上机拷 `soco` 时它是 0700，普通用户读不到，必须 root。

---

## 3. 部署（一条命令）

在新机器上：

```bash
cd /root/soco
mv soga-arm64.crack-soga10 soco 2>/dev/null      # 脚本也认原名，改名只是更清楚
mv libsoco-arm64.so libsoco.so 2>/dev/null
chmod +x deploy_arm64_soco.sh

NODE_ID=<面板节点ID> \
WEBAPI_KEY=<webapi_key> \
SOGA_KEY=<soga_key> \
PANEL_URL=https://<REDACTED> \
./deploy_arm64_soco.sh
```

先只预检不落地（推荐第一次这么干）：

```bash
NODE_ID=... WEBAPI_KEY=... SOGA_KEY=... ART_DIR=/root/soco ./deploy_arm64_soco.sh -n
```

脚本做的 7 步：

1. 预检：root、`aarch64`、参数齐备、两个文件 hash 正确
2. 依赖：`ldd` 检查适配层动态库，缺则 `apt-get install`
3. 装文件：`/usr/local/soco/soco`、`libsoco.so`（均 0700）
4. 写 `/etc/soco/soco.conf`（0600，旧文件自动备份）
5. 写 `soco.service`（含 `Environment=LD_PRELOAD=/usr/local/soco/libsoco.so`）+ `daemon-reload` + 开机自启
6. 启动并检查进程 / `LD_PRELOAD` 是否真的进了 `/proc/PID/maps`
7. 验证：调面板 `config` 接口打印端口与 REALITY 参数、检查用户是否加载、检查适配层是否 `entry mismatch`、检查端口监听

---

## 4. 验证（三关，缺一不可）

```bash
# 第一关：进程在跑、适配层已加载
systemctl is-active soco
PID=$(systemctl show soco -p MainPID --value)
readlink /proc/$PID/exe                      # 应为 /usr/local/soco/soco
grep -c libsoco /proc/$PID/maps              # 必须 > 0
journalctl -u soco -n 30 | grep '\[soco\]'   # 应看到 [soco] users=N out=... bytes

# 第二关：用户已加载
L=/etc/soga/soga-vless-$(date +%Y-%m-%d).log
grep 'add user:' $L | tail -3
grep -c 'current user num' $L               # 应持续增长

# 第三关（唯一可信）：真实握手 + 真实转发
```

第三关做法：客户端连上去，同时看服务器日志。

```bash
# 客户端侧（本机）
curl https://www.cloudflare.com/cdn-cgi/trace     # 出口 IP 应等于新机器公网 IP

# 服务器侧（必须出现 dial + relay，缺一就是没转发）
grep 'tcp direct dial' $L | tail -3
grep -c 'tcp relay' $L
```

### ⚠️ 只看端口会骗人

| 现象 | 真实含义 |
|---|---|
| `ss` 里有 `:49999` LISTEN | 只说明 socket 在听，可能已经「认证完就断」 |
| 日志有 `user ... access address` | 只说明认证通过，**不代表会转发** |
| 日志有 `handle vless end` 且**没有** `tcp direct dial` | **就是没转发** → 二进制不对，换回 `37332960…` |
| 日志有 `tcp direct dial` + `start tcp relay` | ✅ 真的在转发 |

---

## 5. 下发客户端参数

面板 `config` 接口就是标准答案，别手工改：

```bash
curl -s "https://<REDACTED>/api/v1/server/UniProxy/config?node_id=<ID>&node_type=vless&token=<REDACTED>"
```

典型返回里包含 `server_port` / `flow` / `tls_settings.{public_key,private_key,short_id,server_name}`。

客户端侧要点：

- **flow 必须 `xtls-rprx-vision`**，留空会被服务端拒绝
- `fp` 填 `chrome` / `firefox` / `safari` / `ios` / `qq` 之一都可以
- 订阅若走默认 UA，URI 里可能出现 `fp=ioq`（无效）等渲染瑕疵 → 用 `User-Agent: sing-box` 或 `clash` 取结构化配置

---

## 6. 故障对照

| 症状 | 原因 | 处理 |
|---|---|---|
| `native pull_users entry mismatch` | 主程序不是配套那份 | 换回 `37332960…` |
| 有 `access address`、无 `dial` | 用了 174 字节重补丁版 | 换回 `37332960…` |
| `can not use empty flow` | 客户端没带 flow | 客户端填 `xtls-rprx-vision` |
| `current user num: 0` 或没有 `add user` | 面板该节点下没挂用户 / node_id 错 / webapi_key 错 | 面板检查；直接 curl 面板接口确认 |
| 适配层日志不出现 `[soco]` | `LD_PRELOAD` 没生效（unit 写错 / 文件没有执行权限 / 缺 libcurl4、libjson-c5） | 查 `/proc/PID/environ`、`ldd libsoco.so` |
| `soga key 错误` 每约 10 分钟一次 | **正常**，官方版也这样，不影响转发 | 忽略 |
| 端口通但握手超时 | REALITY 参数（pbk/sid/sni）与面板不一致 | 用面板 `config` 接口的值为准 |

---

## 7. 运维

```bash
systemctl status soco --no-pager
systemctl restart soco
journalctl -u soco -f
tail -f /etc/soga/soga-vless-$(date +%Y-%m-%d).log

# 只读诊断
sha256sum /usr/local/soco/soco /usr/local/soco/libsoco.so
systemctl show soco -p MainPID,ActiveState,NRestarts,ExecMainStartTimestamp
```

回滚：

```bash
# 回到官方原版（能转发、无破解属性；但 88 用户上限与授权闸门会被还原）
install -m 0700 /path/to/soga-arm64.original /usr/local/soco/soco && systemctl restart soco

# 关掉适配层（只跑裸二进制，用户数上限恢复）
sed -i '/LD_PRELOAD/d' /etc/systemd/system/soco.service && systemctl daemon-reload && systemctl restart soco
```

---

## 8. 与 amd64 的差异（别照搬）

| | arm64（本文） | amd64 |
|---|---|---|
| 补丁体量 | **43 字节**（10 段 / 11 条指令） | 53 区域（另有适配器抓全量用户） |
| 600 秒数据面闸门 | **没有**（实测 30 次探测 / 893 秒跨 600s 边界，零失败） | **有**，约 601–604 s 后 `accept` 即 `close` |
| 是否需要 hosts + 本地 443 sink | **不需要** | **需要**（`/etc/hosts` 4 行 + `soco-licence-sink`） |
| 适配层 | 需要（同构建才行，`NATIVE_BODY 0x33292e4`） | `libsoco-amd64.so`（`2f60b5f8…`） |

把 ARM 那 10 段照搬到 amd64 上**实测无效**（工程包 `BYPASS.md` §4 有 8 个 A/B 的全部数据）。

---

## 9. 安全提醒

- `soco.conf` 含 `soga_key` 与 `webapi_key`，权限保持 `0600`；`/usr/local/soco/*` 保持 `0700`
- 新机器上线后建议改 root 密码、换 SSH key、面板侧重置一次 node 的 `webapi_key`
- 别忘了开时间同步：`timedatectl set-ntp true`（若这台以后跑 SS-2022，时钟偏差 >30 s 会让握手随机失败——本轮已在另一台踩过）