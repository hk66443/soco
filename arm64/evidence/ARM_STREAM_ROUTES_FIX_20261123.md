# ARM 机器（130.61.141.143）流媒体分流故障复盘 — 2026-11-23

> 结论先行：**soco 一直是好的；坏的是 `routes.toml` 的加载**。文件在 07:29 被写坏过一次，
> soco 的 fs watcher 只在变更瞬间尝试加载、失败后**不会自动重试**，于是内存里的 routes 退回 0 条，
> Netflix / ChatGPT / Disney 全部走直连（德国 Oracle IP），表现就是"流媒体不行"。
> 已修复并实测生效：routes num: 10，netflix/chatgpt 走 `node-us.nfdns.xyz:38383`（104.238.222.105）。

## 1. 现场事实（2026-11-23 13:05 UTC 实测）

| 项 | 值 |
|---|---|
| 机器 | `130.61.141.143` / 私网 `10.0.37.39` / Debian 11 aarch64 / Oracle |
| soco | **active**，PID 2405082，`NRestarts=0`，启动 06:10:15 EST，常驻约 1h55m，RSS 41 MB |
| 监听 | `*:49999` TCP，VLESS + REALITY（sni `www.apple.com`，pbk `<REDACTED-REALITY-PBK>…`，sid `<REDACTED>`） |
| 面板 | node_id **644**，`type=xboard` / `server_type=vless` / `api=webapi`，`config` 与 `user` 接口均 HTTP 200 |
| 面板用户 | id 1635，uuid **<REDACTED-PANEL-UUID>** |
| 二进制 | `/usr/local/soco/soco` = `37332960…73f1d3a`（crack-soga10）；`libsoco.so` = `f5fc39df…f83293a`；`LD_PRELOAD` 已在 `/proc/<pid>/environ` 与 `maps` 中确认 |
| 未安装/未启用 | `soco-watchdog`、`soco-licence-sink`、`soco-mesh`（ARM 侧实测无 600 s 闸门，不需要） |

## 2. 三个问题的根因

### 2.1 「soga 程序启动不起来」 — 不是 soco 的锅，是 soga 自己被守卫杀掉

```
Process: 2407911 ExecStart=/usr/local/soga/soga (code=exited, status=0/SUCCESS)
Process: 2407912 ExecStartPost=/usr/local/bin/soga-license-guard.sh (code=exited, status=1/FAILURE)
soga[2407911]: 2026/11/23 07:30:02 INFO  soga key 错误
soga-license-guard.sh[2407912]: soga 授权失败，拒绝启动 (PID 2407911)
```

- `/usr/local/soga/soga` 是**官方原版** `3c42ba62…01d641`（与 `/root/rollback/soga-official.3c42ba62.bak` 同 hash），
  不是 crack 版 → 本来就带 88 用户上限与授权逻辑。
- `/etc/systemd/system/soga.service.d/license-guard.conf` 里有
  `ExecStartPost=/usr/local/bin/soga-license-guard.sh` + `Restart=no`；该脚本把**启动 +6 s 的
  `soga key 错误`**（官方版正常现象）当作授权失败，直接杀进程并 `exit 1` → 服务 `failed`。
- 即使守卫不拦，soga 也抢不到 `49999`（soco 正持有），并且会退回官方版的 88 用户上限与授权闸门。

**处置：`systemctl disable --now soga` 已执行**（enabled=disabled / active=inactive）。
这台机器只跑 `soco.service`，单位置、单进程。

### 2.2 「流媒体不行」 — routes.toml 加载失败，分流退回直连

时间线（`/etc/soga/soga-vless-2026-11-23.log`）：

```
05:43:12  load routes config ... success, routes num: 10     ← 当时是好的
07:29:22  load routes config ... success, routes num: 0      ← 被还原成 56 字节空配置
07:29:23  ERROR ... failed: toml: line 317 ... unexpected EOF; expected '"'
07:29:23  ERROR ... failed: toml: line 395 (routes.Outs.port) ... got '}' instead
07:45:34  tcp direct dial → www.netflix.com:443 (207.45.73.1)   ← 直连，未解锁
08:03:18  load routes config ... success, routes num: 10     ← 本轮修复后
08:04:08  tcp proxy dial → node-us.nfdns.xyz:38383 (www.netflix.com:443)
08:04:08  start tcp relay ... remote(104.238.222.105:38383)
```

坏文件的来历：`/etc/soga/routes.toml` 模板里有 **`server="{Out}"` / `port={OutPort}` / `password="{UUID}"`**
三个占位符，需要 NF 脚本用 `sed` 替换成真实值（`nfu_nfu.sh` 第 223–225 行就是这么干的）。
07:29 那次写入的是**替换到一半的文件**（TOML 里 `port={OutPort}` 非法），soco 加载失败。

**关键坑**：soco 的 fs watcher 只在文件变更时尝试一次，失败**不会重试**，也不会告警，
内存里继续保持上一次成功状态（或 0）。所以"文件后来其实是对的"也没用 —— 必须手动触发重载。

### 2.3 「uuid 给进去了」 — 面板 uuid 与流媒体账号 uuid 是两个东西

实测 A/B（本机 sing-box → `node-us.nfdns.xyz:38383`，`chacha20-ietf-poly1305`）：

| 密码 | netflix HTTP | 出口 IP |
|---|---|---|
| `<REDACTED-PANEL-UUID>…`（面板节点 644 的 uuid） | **000**（握手失败） | — |
| `<REDACTED-NF-PASSWORD>-200e-4b79-900e-bd125a77c611`（routes.toml 里用的） | **200** | 104.238.222.105 |

即：**面板 node 的 uuid 只给客户端用；NF 解锁服务的密码是另一套账号 uuid（<REDACTED-NF-PASSWORD>…）。**
往面板里"填 uuid"不会让解锁生效，也别把两者互换。

## 3. 本轮做的修复

```bash
# 1) 备份
cp -a /etc/soga/routes.toml /root/rollback/routes.toml.bak.20261123T130318Z
# 2) 第一个 [[routes.Outs]]（#Main：Netflix/ChatGPT/Disney/HBO/Spotify）出口 uk:25253 → us:38383
#    同 inode、同长度就地改写，避免替换 inode 丢 fs watcher
# 3) touch 触发重载 → 08:03:18 routes num: 10
# 4) systemctl disable --now soga；systemctl reset-failed soga
```

改动前后对比（第一个 Outs 块）：

```toml
[[routes.Outs]] #路由 跨国 出口
listen=""
type="ss"
server="node-us.nfdns.xyz"      # 原 node-uk.nfdns.xyz
port=38383                       # 原 25253
password="<REDACTED-NF-PASSWORD>-200e-4b79-900e-bd125a77c611"
cipher="chacha20-ietf-poly1305"
```

其余 9 块（HK 38888 / TW 20558 / JP 38123 / KR 23355 / SG 20955 / UK 25253 / US 38383 / 其它→US / `rules=["*"]`→direct）未动。

## 4. 验证（三关都过）

1. **进程/适配层**：`ActiveState=active`、`NRestarts=0`、`LD_PRELOAD=/usr/local/soco/libsoco.so`；
2. **分流加载**：`load routes config ... success, routes num: 10, enable: true`；
3. **真实链路**：本机 sing-box REALITY 客户端 → `130.61.141.143:49999` →
   `netflix 200` / `chatgpt 200`，服务端日志 `tcp proxy dial → node-us.nfdns.xyz:38383`、
   `tcp relay ... remote(104.238.222.105:38383)`；`49999` established 9 条。

## 5. 遗留与建议

1. **routes 写坏是静默故障**。建议任何改动前先本地 TOML 校验，或加一个 5 分钟的守卫：
   比对 `journalctl -u soco | grep 'load routes'` 最新一条是否 `num: 10`，不是就 `systemctl restart soco` 并告警。
2. **换地区用脚本**：`arm64/deploy/switch_stream_area.sh us|hk|tw|jp|kr|sg|uk`（只改第一个 Outs，自动备份 + 触发重载）。
3. **soga.service 保持 disabled**。需要官方版做对照实验时，先 `systemctl stop soco` 再临时启动，
   否则端口冲突；且 license-guard 会杀掉它（这是既有设计，不是故障）。
4. **ARM 侧仍无 600 s 闸门证据更新**：本轮 soco 自 06:10 连续运行近 2 小时、期间 391 次 direct dial +
   5 次 proxy dial 全部正常，继续佐证 arm64 不受 amd64 那条 601–604 s 数据面闸门影响。