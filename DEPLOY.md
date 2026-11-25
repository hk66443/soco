# DEPLOY · 新机器部署（amd64 / arm64 通用）

> 面向**一台全新机器**：从零装到能用，含验证、多实例、回滚。
> 全流程只有三条命令是你需要记的：`install` → `probe` → `doctor`，其余都在 `so-console` 里。
> 占位符：`<SERVER_IP>` 你的公网 IP、`<PANEL_URL>` 机场面板地址、`<NODE_ID>` / `<WEBAPI_KEY>` / `<so**_KEY>` 面板给的三件套。

---

## 0. 你要准备的

| 项 | 要求 |
|---|---|
| 机器 | Debian 11/12/13（Ubuntu 22.04+ 亦可），systemd，root |
| 架构 | `x86_64` 或 `aarch64`（`uname -m` 确认，接下来按架构走） |
| 内存 | amd64 ≥1 GB；arm64 ≥2 GB（单实例压测时独占） |
| 端口 | 面板会下发业务端口，安全组放行 TCP（SS2022 还要放 UDP） |
| 面板 | 已在该机器创建一个节点：拿到 `<NODE_ID>`、`<WEBAPI_KEY>`、`<so**_KEY>` |
| 二进制 | 按 §2 拿到 `soco` + `libsoco.so`（仓库不含，80–90 MB/个） |
| 网络 | 机器能出网（拉面板接口、探活）；被墙也能跑，但首次验证建议直连 |

---

## 1. 支持矩阵

| | amd64 | arm64 |
|---|---|---|
| `uname -m` | `x86_64` | `aarch64` |
| 二进制 | 53 区域补丁版 `soco` | **variantE**（`variantC` + 8 处 `mov #3→xzr`） |
| 适配层 | `libsoco.so`（x86_64） | `libsoco.so`（aarch64） |
| 协议 | Shadowsocks 2022 | VLESS + REALITY |
| 补丁生成器 | `amd64/manifest/patch-manifest-amd64.json` | `_ops/build_variantA/B/C/E.py` |
| 源码 | `amd64/src/adapter-amd64.c` | `arm64/src/adapter-arm64.c` |

`so-console` 会自己判断架构并写进 `/etc/so/console.conf`，你不用手工选。

---

## 2. 二进制从哪来（三选一）

**A. 从已有机器备份取回**（最省事，版本已经是验证过的）

```bash
# 在旧机器上
tar czf so-bin.tgz -C /usr/local soco/
# 新机器
tar xzf so-bin.tgz -C /usr/local/
ls -l /usr/local/soco/{soco,libsoco.so}
```

**B. 从原版 + 本仓库补丁重建**

```bash
# amd64：按补丁清单打 53 区域，并编译适配层
gcc -shared -fPIC -O2 -o libsoco.so amd64/src/adapter-amd64.c -ldl
# arm64：按变体链逐级生成（脚本自带入口断言，失败会中止）
python3 _ops/build_variantA.py
python3 _ops/build_variantB.py
python3 _ops/build_variantC.py
python3 _ops/build_variantE.py     # 产物：soco-arm64.variantE
```

**C. 只换业务端口/面板，沿用同一份二进制** —— 直接把旧机器的 `/usr/local/soco` 整个目录带走。

> 无论哪条路，装完用 `so-console verify` 对一下指纹；指纹不符说明你拿到的不是验证过的版本。

### 2.1 探测客户端（`probe` 用，建议装）

`probe` / `doctor` 的真实握手需要一个 sing-box 客户端，仓库不含（约 80 MB）。放到固定位置即可：

```bash
# amd64
curl -L -o /tmp/sb.tgz https://github.com/SagerNet/sing-box/releases/latest/download/sing-box-linux-amd64.tar.gz 2>/dev/null || \
  echo "手动下载 sing-box（linux-amd64）后解包"
# arm64 用 sing-box-linux-arm64.tar.gz

tar xzf /tmp/sb.tgz -C /tmp
install -m 755 /tmp/sing-box-*/sing-box /usr/local/soco/sing-box-probe

/usr/local/soco/sing-box-probe version      # 能打印版本即可用
```

> 你的发行版若自带 `sing-box` 包，也可以直接软链：
> `ln -s "$(command -v sing-box)" /usr/local/soco/sing-box-probe`。
> 没装这个客户端不影响节点本身运行，只是 `probe` / `doctor` 的握手项会显示 FAIL。

---

## 3. 上传什么（只传项目，不要传别的）

```bash
scp -r ./soco root@<SERVER_IP>:/root/so
```

**要传**：仓库本身（`console/ amd64/ arm64/ packaging/ _ops/` + 根目录 md）。
**不要传**：`/etc/so**` 里的旧配置（含别人的 key）、`/root/*backup*`、任何私钥、旧日志。

---

## 4. 面板侧准备（顺序很重要）

1. 面板 → 服务器 → 新建节点（区域随便，名字有意义即可）；
2. 协议选 `Shadowsocks 2022`（amd64）或 `VLESS + REALITY`（arm64）；
3. 记下 **节点 ID**（`<NODE_ID>`）——这是客户需要在安装向导里填的三项之一；
4. 业务端口、REALITY 的 `public_key / short_id / server_name`、SS2022 的 `server_key / cipher` **都由面板下发**，
   节点侧不写死；
5. 把用户/套餐挂到这个节点上（用户数在面板上调，节点侧每 60 s 拉一次）。

**`webapi_key` = 面板与节点之间的通信密钥**，必须以面板里的为准（填错/随机 → 拉不到用户）；
`webapi_url` 是面板地址。两者都由客户提供。

**`so**_key` = 授权密钥**：本工程已解除授权检查，控制台随机生成即可，不需要客户关心。

TLS 协议（`vmess` / `trojan` / `anytls` / `hysteria`，以及要自带证书的 `vless`）还要选证书方式：
`panel`（面板下发）/ `self`（本机自签）/ `file`（已有证书）/ `http`（ACME HTTP-01）/ `dns`（ACME DNS-01）。
逐项说明与命令写法见 **[CONFIG.md](CONFIG.md) §3**。

> 配置文件由控制台写（`0600`，路径 `/etc/so**/so**.conf`）—— **机场/主控信息都在这个文件里**，内容固定：
>
> ```ini
> type=xboard            # 固定
> api=webapi             # 固定
> check_interval=60      # 固定
> submit_interval=60     # 固定
> log_level=error        # 固定：只记错误日志
> server_type=<ss|vless> # 安装时选
> node_id=<节点ID>        # 安装时填
> webapi_url=<面板地址>    # 安装时填
> webapi_key=<面板给的串 / 留空则随机>    # 客户填（或随机）
> so\*\*_key=<同一串>                       # 与 webapi_key 相同
> ```
>
> 要看真实路径：`so-console paths`。**不要手写这份配置**，用 `so-console install` 覆盖即可（幂等）。

---

## 5. 安装（向导问四项：节点 ID / 协议 / 面板地址 / 节点密钥）

```bash
/root/so/console/so-console install          # 向导：节点 ID → 协议 → 面板地址 → 节点密钥
```

```
  节点 ID [ ]: 12
  协议  1) Shadowsocks 2022   2) VLESS + REALITY
  选择 [1]: 1
  面板地址 [https://]: https://panel.example.com
  节点密钥 = 面板节点详情里的 webapi_key（与 so**_key 同一串）
  节点密钥（回车 = 本机随机生成） [ ]: <粘贴面板里那串>
```

**客户填四项**（节点 ID / 协议 / 面板地址 / 节点密钥），其余由控制台固定并自动完成：

| 固定项 | 值 |
|---|---|
| `type` / `api` | `xboard` / `webapi` |
| `check_interval` / `submit_interval` | `60` / `60` |
| **日志** | `log_level=error` —— **只记错误**，不刷流量流水 |
| 节点密钥 | **客户填**：面板节点详情里的 `webapi_key`（与 `so**_key` 同一串）；留空则本机随机生成（装完回填面板） |
| 闸门 | hosts 4 条 + 本地 sink(`38443`) + nft `127.0.0.1:443→38443` |
| 单元 | `soco.service` / `soco@.service` / sink / nft / watchdog 共 5 个 |

`install` 的 7 步（幂等，重复执行 = 修复）：

```
[1/7] 环境预检        root、systemctl、ss、nft、curl、openssl、二进制
[2/7] 目录与二进制     /usr/local/soco + licence/ + 权限 0755/0600，拷探针与 watchdog
[3/7] 写入配置         log_level=error，密钥写入
[4/7] 授权 sink        自签证书 + hosts 4 条 + sink 38443
[5/7] systemd 单元     5 个 + daemon-reload + enable
[6/7] 启动与状态       active / pid / restarts / 业务端口
[7/7] 真实握手验证     3 个用户真实转发（可 --no-probe 跳过）
```

非交互写法（脚本 / 批量，全部可用）：

```bash
# 最常用：三项写在参数里，一条命令装完
so-console install --node-id 12 --type ss --url https://panel.example.com

# 第二个机场（另一台面板）
so-console install --node-id 13 --type vless --url https://p2.example.com

# 面板已经给了一对 key（覆盖自动生成的那串）
so-console install --node-id 12 --type ss --url https://panel.example.com --webapi-key <面板给的key>

# 只预演，不改系统（打印 7 步计划）
so-console install --node-id 12 --type ss --url https://panel.example.com --dry-run

# 先装起来，跳过真实握手验证（网络/面板还没通的时候）
so-console install --node-id 12 --type ss --url https://panel.example.com --no-probe

# 直接用实例名部署（等价于 inst new jp1 …）
so-console install --node-id 12 --type ss --url https://panel.example.com --name jp1
```

想用菜单操作就不用带参数：`so-console` → 选 `1 install`（菜单见 [README.md](README.md) §1.2 / [CONSOLE.md](CONSOLE.md) §7）。

> **443 端口**：sink 监听 `38443`，`127.0.0.1:443` 用 nft dnat 指到它，所以**对外 443 是空的**，可以给网站/证书用。

---

## 6. 验证（三关，缺一不可）

```bash
/root/so/console/so-console status      # 服务 active / 端口 LISTEN / 人数 = 面板条数
/root/so/console/so-console probe 3     # 3 个用户真实握手（期望 3/3）
/root/so/console/so-console doctor      # 逐项 PASS/FAIL
```

**全量**（面板有多少用户就跑多少，串行）：

```bash
/root/so/console/so-console probe all          # 面板有多少用户就跑多少（串行，按机型 10–30 min）
journalctl -u soco --since '-30min' -o cat | grep -c 'tcp relay'      # 服务端确实在转发
journalctl -u soco --since '-30min' -o cat | grep -c 'auth failed'    # 期望 0
```

三关的口径：

| 关 | 判据 | 失败说明 |
|---|---|---|
| ① 进程与适配层 | `so-console verify` 里 `adapter loaded = yes` | `LD_PRELOAD` 没进 unit，或 `.so` 权限/属主不对 → 用户数会停在 88（适配层未加载的典型症状） |
| ② 用户表 | `so-console users` 本地 ≈ 面板条数 | 面板 key 错，或自适应层没生效 |
| ③ 真实握手 + 转发 | `probe 3` 全过且日志有 `tcp relay` | 只有 `access address` 没有 `tcp relay` = 闸门开了 → `so-console gate` |

---

## 7. amd64 专属注意

- **适配层是硬要求**：`soco.service` 里必须有 `Environment=LD_PRELOAD=/usr/local/soco/libsoco.so`，
  否则用户表只加载到 88 条。`so-console install` 已写好，别手改掉。
- 内存 ≥1 GB：单实例 ≈80 MB，但压测（sing-box 客户端）会额外吃 30–60 MB/个，**串行**跑，不要并发。
- SS2022 业务端口 **TCP+UDP 都要放行**；`probe_many.py` 会把面板下发的 `server_key:cipher` 拼成客户端密码。

## 8. arm64 专属注意

- 必须是 **variantE**（`sha256` 以 `549ef746…` 开头那一版）。用旧版或 `variantB` 会出现"认证过但不转发"的数据面问题。
- **流媒体分流交给其它程序**（nfu / 你自己的路由器 / 面板侧规则）。本控制台**只读查看**，不写 `routes.toml`：

```bash
/root/so/console/so-console routes            # 规则数 + 首个出站 + 最近一次加载结果
/root/so/console/so-console routes show       # 再列若干条规则字段
/root/so/console/so-console routes validate   # 只做 TOML 合法性检查（不动文件）
```

- 看到 `规则数 0` 或没有 `success` 行 = TOML 被写坏或被覆盖，恢复由你那条链路的工具负责。
- 分流模板在 `_ops/routes_tw_patch.toml`（含占位符，需要填你自己的出站 `server/port/password` 与用户 `uuid`）。
- 出站能力矩阵（哪家串流该走哪个地区）见 `arm64/evidence/STREAM_NF_MATRIX_20261125.md`。

---

## 9. 多实例（一台机多个机场）

```bash
# 列表：实例 / 节点ID / 协议 / 状态 / 重启次数
/root/so/console/so-console inst

# 向导：实例名 → 节点 ID → 协议 → 面板地址
/root/so/console/so-console inst new

# 一行式
/root/so/console/so-console inst new jp1 --node-id 21 --type vless --url https://p2.example.com

# 生命周期
/root/so/console/so-console inst start   jp1
/root/so/console/so-console inst stop    jp1
/root/so/console/so-console inst restart jp1
/root/so/console/so-console inst log     jp1
/root/so/console/so-console inst remove  jp1
```

| 约束 | 原因 |
|---|---|
| 每个实例 = `soco@<名>.service` + `<名>.conf`，日志独立 | 共用会互串 |
| **不要**让两个实例同时打满人数 | 适配层状态会互相顶掉，人数会异常掉到个位数 |
| 端口由面板下发，别撞主实例 | 撞了起不来，日志有 `bind: address already in use` |
| 内存：实例数 ×（80–95 MB）+ 余量 | 1 GB 机器最多 2 个，且不同时压测 |

---

## 10. 回滚 / 卸载 / 换机

```bash
# 备份（/usr/local/soco + 配置目录）
/root/so/console/so-console backup         # -> /root/so-backup-<时间>.tar.gz

# 回滚到某个备份（会先停服务，恢复后自动起）
/root/so/console/so-console rollback
/root/so/console/so-console rollback /root/so-backup-20260101-120000.tar.gz

# 彻底卸载改造（回到"能用但受限制"的官方行为）
systemctl disable --now soco soco-watchdog soco-licence-sink soco-sink-redirect
sed -i '/vaxilu\|singledance\|cilema/d' /etc/hosts
nft delete chain ip nat redir 2>/dev/null || true
rm -f /etc/systemd/system/soco*.service /etc/systemd/system/soco@.service
systemctl daemon-reload
```

**换机**：新机器重复 §3 → §6；旧的 `/usr/local/soco` 打包带走即可（含二进制与 sink 证书），
配置里只有 webapi 三件套需要按新节点改。

---

## 11. 故障表

| 症状 | 先查 | 处置 |
|---|---|---|
| `probe` 全挂、端口在听 | `so-console gate` | 按提示补齐 hosts / sink / nft，然后 `install` 一次（幂等） |
| 用户数停在 88 | `so-console verify` 的 `adapter loaded` | 确认 unit 里 `LD_PRELOAD`、`.so` 为 `0600 root` |
| 认证过、客户端无网 | `journalctl -u soco -n 200 -o cat \| grep 'tcp relay'` | 无 relay = 闸门/上限；有 relay = 出口/面板侧问题 |
| `panel users: <fetch failed>` | 配置里的 `webapi_url / webapi_key` | 手测面板接口；sink 只拦授权域名，不影响面板 |
| `routes num: 0` | `so-console routes validate` | TOML 写坏或被别的工具覆盖 → 用 `.bak` 恢复 |
| 进程反复重启 | `/var/log/soco-watchdog.log` | `probe_failed` 连续 3 次才重启；看 curl 错误码（97 = SOCKS 建连失败） |
| 实例起不来 | `so-console inst log <name>` | 端口冲突 / 配置缺字段 / 内存不足 |

---

## 12. 变更 checklist（改动前后各跑一遍）

```bash
/root/so/console/so-console verify        # 记录指纹
/root/so/console/so-console backup        # 备份
# … 变更 …
/root/so/console/so-console probe 3       # 至少 3 个用户
/root/so/console/so-console doctor        # ALL PASS
```

涉及闸门相关的改动（hosts / sink / nft），**必须观察 ≥12 分钟（跨过 600 s）**再算通过。