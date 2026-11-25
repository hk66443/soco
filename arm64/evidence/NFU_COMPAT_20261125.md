# nfu / so\*\* 生态兼容 + 路由守卫 + watchdog（2026-11-25）

## 1. 需求

1. `bash <(curl -Ls https://config.nfdns.xyz/nfu_sh/install.sh)` 这套 nfu 工具要能直接给 soco 用（流媒体交给 nfu 负责）；
2. `nfu so**` 会覆盖 `/etc/so**/routes.toml` 并执行 `so** restart` → soco 必须兼容，且**不能被覆盖掉已有的分流修正**；
3. ARM 节点补 watchdog（停摆态自愈）。

## 2. nfu 到底做了什么（读 nfu.sh 得知）

`so**Confing()` 四步：

```bash
wget -O /etc/so**/routes.toml https://config.nfdns.xyz/nfu_sh/config/so**/routes.toml
sed -i "s/{UUID}/$UserUUID/g"      /etc/so**/routes.toml
sed -i "s/{Out}/$OutArea/g"        /etc/so**/routes.toml
sed -i "s/{OutPort}/$OutPort/g"    /etc/so**/routes.toml
sudo so** restart
```

- 只碰 `/etc/so**/routes.toml`（这与 soco 的目录完全一致，天然兼容）；
- 最后调用 **`so** restart`** —— 系统里必须存在 `so**` 命令，否则这一步报 `so**: command not found`。

## 3. 兼容层

### 3.1 `so**` 命令（/usr/bin/so\*\*）

```bash
#!/bin/bash
# nfu / so** 生态脚本调用 so** restart|stop|start|log|config 时，实际作用到 soco
exec /usr/bin/soco "$@"
```

- `so** restart` → `soco restart` → 重启 `soco.service` 与全部 `soco@*` 实例；
- `so** stop/start/log/config/status/list` 同样可用（`soco status` 已补）。

### 3.2 路由守卫（P1）

`nfu so**` 用模板覆盖 routes.toml，会丢掉「Netflix/OpenAI → 台湾出口」那条补丁。
新增：

| 文件 | 作用 |
|---|---|
| `/usr/local/soco/routes-guard.py` | 检测 `# soco-route-tw` 标记；缺失则在 `enable=true` 后插入补丁（password 自动沿用文件里第一个 ss 出站的密码 = nfu 替换后的 UUID）；幂等、串行、带重试 |
| `/etc/systemd/system/soco-routes-guard.path` | `PathModified=/etc/so**/routes.toml`，文件被改就触发 |
| `/etc/systemd/system/soco-routes-guard.service` | oneshot 执行守卫 |

关键细节（实测踩出来的）：

1. nfu 的写入是「wget 覆盖 → 3 次 sed」，期间文件会短暂出现 `{UUID}` 占位符或半截 TOML，守卫必须：
   - 看到 `{UUID}/{Out}/{OutPort}` → 等待重试（最多 4 轮），绝不能在半截文件上插；
   - mtime 连续 2 秒不变才动手；
2. soco 的 routes watch 只对 **内容写入（IN_MODIFY）** 稳定触发；rename 替换 / `utime` 不触发。
   守卫写完补丁后追加一个空行触发重载，实测立即生效；
3. 插入位置必须在 `enable=true` 之后（匹配按顺序，放最前才优先）。

### 3.3 效果实测

```
# 模拟 nfu so** 完整流程（wget + 3 次 sed）
before: marker=1 routes=11
after : marker=1 routes=11          # 补丁被自动补回
guard log: routes file still changing, retry 0
            patched: inserted TW route after enable=true (password len=36)
soco log : success, routes num: 11, enable: true   ← 插入后重新加载成功
so** restart → active，routes num 11
客户端实测：netflix 302 / chatgpt 200 / cloudflare 200
```

> 覆盖过程中 soco 会打出几条 `load routes config file ... failed` —— 那是 fsnotify 读到 nfu 的半截文件，属预期；soco 保留旧配置继续服务，守卫补完后恢复 `success, routes num: 11`。

## 4. watchdog（P2，ARM / VLESS+REALITY）

| 文件 | 作用 |
|---|---|
| `/usr/local/soco/soco-watchdog.py` | 每 30 s 用 sing-box 起 socks → VLESS/REALITY 打本机 49999 → 请求本地 marker(18089)，必须回 `M` |
| `/usr/local/soco/sing-box-probe` | sing-box 1.14.4 linux/arm64（75 MB） |
| `/etc/systemd/system/soco-watchdog.service` | `PROBE_EVERY=30 / FAILS_TO_RESTART=3 / PREEMPT_SECONDS=0`，`Restart=always` |
| `/var/log/soco-watchdog.log` | JSON 行：`watchdog_start` / `probe_ok` / `probe_failed` / `restart` / `recovered` |

要点：
- 配置路径 `/etc/so**/so**.conf`（兼容旧 `/etc/soco/soco.conf`）；
- REALITY 参数（server_name / public_key / short_id）**每次实时从面板拉**，不用手写；
- 面板拉不到用户/配置 → 记 `probe_error` 跳过，不误杀；
- 进程启动 30 s 内不判；`PREEMPT_SECONDS=0`（variantE 已无 600 s 闸门，不需要预重启）。

### 4.1 停摆演练（真实触发重启）

用 nft 只对 **loopback 探测路径** 丢包，模拟「端口在听但不转发」，真实公网客户端不受影响：

```nft
table ip soco_wd_test {
  chain wdout {
    type filter hook output priority 0; policy accept;
    ip daddr 127.0.0.1 tcp dport 49999 drop
  }
}
```

结果见文末「实测记录」。

## 5. 回滚

```bash
systemctl disable --now soco-routes-guard.path soco-watchdog.service
rm -f /etc/systemd/system/soco-routes-guard.{path,service} /etc/systemd/system/soco-watchdog.service
rm -f /usr/bin/so** /usr/local/soco/routes-guard.py /usr/local/soco/soco-watchdog.py
systemctl daemon-reload
```

## 6. 实测记录

### 6.1 路由守卫（nfu 覆盖后自动补回）

```
# 完全复刻 nfu so**：wget 覆盖 + 3 次 sed
before: marker=1 routes=11
after : marker=1 routes=11
guard : routes file still changing, retry 0
        patched: inserted TW route after enable=true (password len=36)
soco  : load routes config file </etc/so**/routes.toml> success, routes num: 11, enable: true
so** restart → active；客户端：netflix 302 / chatgpt 200 / cloudflare 200
```

### 6.2 watchdog（停摆演练，真实触发一次重启）

```
08:11:24 probe_ok  (server_port 49999, uuid fa12cb52…)
08:25:26 probe_failed fails=1  curl: (97) Can't complete SOCKS5 connection
08:26:02 probe_failed fails=2
08:26:38 probe_failed fails=3
08:26:38 restart reason=vless_probe_failed
08:27:07 after_restart ok=true  (新 MainPID 2457293)
之后：current user num 497、VLESS listen (:49999)、systemctl active、NRestarts=0
```

说明：
- 演练只对 **loopback 探测路径**（127.0.0.1:49999）丢包，公网客户端不受影响；
- watchdog 重启 soco 后立即复核 `after_restart ok=true`；
- 规则 118 秒后自动删除，服务随之恢复，不会造成重启循环。

### 6.3 当前单元清单（ARM）

```
soco.service             active  （默认 /etc/so**/so**.conf）
soco-licence-sink.service active （0.0.0.0:38443）
soco-sink-redirect.service active（nft 127.0.0.1:443→38443）
soco-routes-guard.path    active  （监听 routes.toml）
soco-watchdog.service     active  （真实 VLESS/REALITY 探活）
```