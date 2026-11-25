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
3. 记下三件套：`<NODE_ID>`、`<WEBAPI_KEY>`、`<so**_KEY>`；
4. 业务端口、REALITY 的 `public_key / short_id / server_name`、SS2022 的 `server_key / cipher` **都由面板下发**，
   节点侧不写死——你只要把 webapi 三件套填进配置文件即可；
5. 把用户/套餐挂到这个节点上（用户数在面板上调，节点侧每 60 s 拉一次）。

节点配置文件（真实路径用 `so-console paths` 看，通常是 `/etc/so**/so**.conf`）：

```ini
type=xboard
server_type=ss            # arm64 写 vless
node_id=<NODE_ID>
api=webapi
webapi_url=<PANEL_URL>
webapi_key=<WEBAPI_KEY>
so**_key=<so**_KEY>
check_interval=60
submit_interval=60
log_level=info
```

```bash
install -d -m 700 /etc/so**
install -m 600 so**.conf /etc/so**/so**.conf    # 文件名按你机器的实际路径来
```

---

## 5. 一条命令安装

```bash
/root/so/console/so-console install /root/so
```

`install` 做这 7 件事（全部幂等，可反复跑）：

1. 建目录：`/usr/local/soco`、`licence/`、配置目录；
2. 校验并在必要时摆放 `soco` / `libsoco.so`（`0755` / `0600`）；
3. 从项目里拷 `probe_many.py`、`soco-watchdog.py`、`routes-guard.py`、`licence/sink.py`；
4. 生成 licence 自签证书（sink 只需要"被拒绝"，不需要可信）；
5. 写 `/etc/hosts` 的 4 条授权域名 → `127.0.0.1`（幂等，缺才补）；
6. 写 5 个 systemd 单元并 `daemon-reload` + `enable --now`（主服务、sink、nft 转发、watchdog、多实例模板 `soco@.service`）；
7. 落 `/etc/so/console.conf`，然后自动跑一次闸门自检。

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
/root/so/console/so-console probe all          # 等价 probe 497；约 7–20 min 视机型
journalctl -u soco --since '-30min' -o cat | grep -c 'tcp relay'      # 服务端确实在转发
journalctl -u soco --since '-30min' -o cat | grep -c 'auth failed'    # 期望 0
```

三关的口径：

| 关 | 判据 | 失败说明 |
|---|---|---|
| ① 进程与适配层 | `so-console verify` 里 `adapter loaded = yes` | `LD_PRELOAD` 没进 unit，或 `.so` 权限/属主不对 → 用户数会卡在 88 |
| ② 用户表 | `so-console users` 本地 ≈ 面板条数 | 面板 key 错，或自适应层没生效 |
| ③ 真实握手 + 转发 | `probe 3` 全过且日志有 `tcp relay` | 只有 `access address` 没有 `tcp relay` = 闸门开了 → `so-console gate` |

---

## 7. amd64 专属注意

- **适配层是硬要求**：`soco.service` 里必须有 `Environment=LD_PRELOAD=/usr/local/soco/libsoco.so`，
  否则只会 `add user` 到 88。`so-console install` 已写好，别手改掉。
- 内存 ≥1 GB：单实例 ≈80 MB，但压测（sing-box 客户端）会额外吃 30–60 MB/个，**串行**跑，不要并发。
- SS2022 业务端口 **TCP+UDP 都要放行**；`probe_many.py` 会把面板下发的 `server_key:cipher` 拼成客户端密码。

## 8. arm64 专属注意

- 必须是 **variantE**（`sha256` 以 `549ef746…` 开头那一版）。用旧 crack 版或 `variantB` 会在 `>88` 用户时认证过、但不转发。
- `routes.toml`（`/etc/so**/routes.toml`，真实路径看 `so-console paths`）：

```bash
/root/so/console/so-console routes list          # 条数 + 首个 Outs 出口 + loaded 状态
/root/so/console/so-console routes switch tw     # 把第一个 Outs 块切到 tw（自动备份 .bak.<时间>）
/root/so/console/so-console routes validate      # TOML 合法性（写坏会静默 0 条）
```

- 分流模板在 `_ops/routes_tw_patch.toml`（含占位符，需要填你自己的出站 `server/port/password` 与用户 `uuid`）。
- 出站能力矩阵（哪家串流该走哪个地区）见 `arm64/evidence/STREAM_NF_MATRIX_20261125.md`。

---

## 9. 多实例（一台机多个机场）

```bash
/root/so/console/so-console inst list
/root/so/console/so-console inst new jp1 node_id=<NODE_ID> webapi_url=<PANEL_URL> webapi_key=<KEY> so**_key=<KEY>
/root/so/console/so-console inst start jp1
/root/so/console/so-console inst log jp1
/root/so/console/so-console inst remove jp1
```

| 约束 | 原因 |
|---|---|
| 每个实例一套 `<inst>.conf`，日志/缓存独立目录 | 共用会互串 |
| **不要**让两个实例同时打满人数 | 适配层状态会互相顶掉（历史事故：在线从数百掉到个位数） |
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
| 用户数卡 88 | `so-console verify` 的 `adapter loaded` | 确认 unit 里 `LD_PRELOAD`、`.so` 为 `0600 root` |
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