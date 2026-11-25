# soco 多实例与 soga 兼容配置（不用 docker）

> 目标：**程序叫 soco，配置与流媒体目录沿用 soga**（`/etc/soga/`），这样 nfu / soga 生态的脚本（`nfu soga`、`routes.toml`、`blockList`、`dns.yml`、`geoip.dat`）可以直接改、直接生效；同时支持 soga 那套「一实例一配置」的多实例方式。

## 1. 为什么不用额外适配

soco 就是 soga 2.18.1 的后端（加 soco 适配层），它的默认配置路径本来就是：

```
-c 的默认值 = /etc/soga/soga.conf
```

`/usr/local/soco/soco -h` 里能看到：

```
  -c string
        Set config file (default "/etc/soga/soga.conf")
```

所以 `soco` 不加参数运行时，行为和 `soga` 完全一样，读的是同一份 `/etc/soga/soga.conf`、同一份 `/etc/soga/routes.toml`。

## 2. 文件布局

| 路径 | 作用 |
|---|---|
| `/usr/local/soco/soco` | 主程序（= soga 2.18.1 + 补丁） |
| `/usr/local/soco/libsoco.so` | `LD_PRELOAD` 适配层（解除 88 人上限等） |
| `/etc/soga/soga.conf` | **主实例配置**（`soco.service` 不带 `-c`，用默认值） |
| `/etc/soga/<name>.conf` | 其它实例配置（`soco@<name>.service` 用 `-c` 指向它） |
| `/etc/soga/instances/<name>/` | 实例私有目录：`log_file_dir` / `ip_user_cache_save_dir` / `access_log_dir` |
| `/etc/soga/routes.toml` | 流媒体路由（多实例共享；nfu 直接写这里） |
| `/etc/soga/{blockList,whiteList,dns.yml,geoip.dat,geosite.dat}` | 共享数据文件 |
| `/etc/systemd/system/soco.service` | 主实例单元 |
| `/etc/systemd/system/soco@.service` | 多实例模板（`-c /etc/soga/%i.conf`） |
| `/usr/bin/soco` | 管理脚本 |

旧的 `/etc/soco/soco.conf` 只作为备份保留，不再被任何单元引用（内容与 `/etc/soga/soga.conf` 相同，迁移可回滚）。

## 3. 单实例（默认）

```bash
systemctl status soco
soco list
soco log            # journalctl -u soco
soco config         # 打印 /etc/soga/soga.conf
soco config node_id=644 check_interval=60   # 改主实例配置并重启
```

改完配置：

```bash
systemctl restart soco
```

## 4. 多实例（每个实例一个机场 / 一个节点）

一条命令新建实例（自动建配置、自动隔离日志与缓存目录、注册并启动 `soco@<name>`）：

```bash
soco new jp1 node_id=645 \
  webapi_url=https://panel.example.com webapi_key=KEY \
  soga_key=<REDACTED>
```

等价于：

```
/etc/soga/jp1.conf              <- 从 soga.conf 复制 + 覆盖上面这些键 + 写入私有目录
/etc/soga/instances/jp1/        <- log_file_dir / ip_user_cache_save_dir / access_log_dir
systemctl enable --now soco@jp1
```

管理：

```bash
soco list                       # 全部实例 + 状态 + 重启次数 + 日志目录
soco start jp1 / stop jp1 / restart jp1
soco log jp1 -f                 # 读实例日志（优先读实例目录里的 soga-*.log）
soco config jp1                 # 看实例配置
soco config jp1 check_interval=30
soco rename jp1 jp2
soco remove jp1                 # 停服务 + 删配置（私有目录保留）
```

**端口**：每个实例的监听端口由各自面板下发（`UniProxy/config` 的 `server_port`），新建后自查是否冲突：

```bash
ss -lntp | grep -E 'soco'
```

**隔离要点（必须）**：不同实例的 `log_file_dir`、`ip_user_cache_save_dir`、`access_log_dir` 要不同——`soco new` 已经自动写进 `/etc/soga/instances/<name>/`。如果手动复制配置，务必一并改这三项，否则同一天会写同一个 `soga-vless-YYYY-MM-DD.log`，IP-用户缓存也会互相覆盖。

## 5. 不用 systemd 的前台/后台方式（screen / nohup）

systemd 只是推荐方式；要手工跑（比如临时调试）直接：

```bash
# 后台常驻（日志落实例目录）
LD_PRELOAD=/usr/local/soco/libsoco.so \
nohup /usr/local/soco/soco -c /etc/soga/jp1.conf \
  >>/etc/soga/instances/jp1/stdout.log 2>&1 &

# screen 方式（与原 soga 文档一致）
screen -R soco-jp1
LD_PRELOAD=/usr/local/soco/libsoco.so /usr/local/soco/soco -c /etc/soga/jp1.conf
# ctrl+a 松开再按 d 离开；ctrl+a 松开再按 Esc 可滚屏；exit 关闭
```

注意 `LD_PRELOAD` 必须带，否则适配层不生效（88 上限/用户表处理会退回原生行为）。

## 6. 流媒体（第三方 NF 解锁）

- 所有实例共读 `/etc/soga/routes.toml`；`nfu soga` 生成的流媒体配置直接落在这里，改完重启实例即可：
  ```bash
  nfu soga                # 第三方脚本写 /etc/soga/...
  systemctl restart soco  # 或 soco restart <name>
  journalctl -u soco -n 50 -o cat | grep routes
  # 期望：load routes config file </etc/soga/routes.toml> success, routes num: N, enable: true
  ```
- 如果某个实例要用**另一套** routes，把它的配置里加 `routes_url=<地址>`（该实例单独生效），其余实例继续用 `/etc/soga/routes.toml`。
- `routes.toml` 写坏会**静默**退回 0 条，改完一定看上面那条日志。

## 7. 安装 / 更新 / 回滚

```bash
# 安装或更新主程序（保留 /etc/soga 配置与所有实例）
install-soco.sh --bin /path/to/soco            # 本地文件
install-soco.sh --bin https://.../soco --lib /path/to/libsoco.so
soco update /path/to/soco /path/to/libsoco.so  # 装完后重启全部实例
```

安装脚本的行为：
1. `/usr/local/soco/{soco,libsoco.so}`（旧文件自动 `.bak.<时间戳>`）；
2. 写 `soco.service` / `soco@.service` / `/usr/bin/soco`；
3. `/etc/soga/soga.conf` 存在就不动；只有 `/etc/soco/soco.conf` 时复制过去；
4. 补齐 `/etc/soga/{routes.toml,blockList,whiteList,dns.yml,geoip.dat,geosite.dat}`（只补缺）；
5. 默认重启主实例，`--no-restart` 可只改单元不重启。

> `soco update` 只接受**本项目构建的 soco 二进制**（含 53 区域补丁/ARM variantE 与适配层）。直接把官方 `soga` release 换进来会丢掉破解与适配层，`soco -v` 能跑但 88 上限/600 s 闸门行为会回退。

回滚（主实例回到旧布局）：

```bash
install -m644 /root/soco-pkg/soco.service.bak /etc/systemd/system/soco.service
systemctl daemon-reload && systemctl restart soco
```

## 8. 已实测（2026-11-25，ARM 生产机 `130.61.141.143`）

同机同时跑两个实例（mock 面板，分别 3 / 5 用户，独立目录），生产实例（497 用户、真实面板）同时在跑：

| 项 | 结果 |
|---|---|
| 实例 A | `current user num: 3`，监听 `*:30001`，日志在 `/tmp/mi/A/soga-vless-2026-11-25.log` |
| 实例 B | `current user num: 5`，监听 `*:30002`，日志在 `/tmp/mi/B/...` |
| 生产实例 | `current user num: 497`，`NRestarts=0`，`*:49999` 正常，未受影响 |
| 面板请求 | A/B 各自只打自己的 mock（19001/19002），无交叉 |
| 结论 | 多实例安全，**不需要不同机器**；隔离靠「独立 webapi_url + 独立 log/cache 目录」 |

### 8.1 两台生产机的现状（2026-11-25）

| 机器 | 配置路径 | 主实例 | sink | 443 |
|---|---|---|---|---|
| ARM `130.61.141.143`（node 644，VLESS/REALITY） | `/etc/soga/soga.conf`（unit 无 `-c`） | 497 用户、49999、REALITY e2e 回 `ip=130.61.141.143` | `0.0.0.0:38443` + nft dnat | **空闲** |
| AMD `141.148.139.236`（node 341，SS2022） | `/etc/soga/soga.conf`（unit 无 `-c`） | 497 用户、49989、SS2022 探针 `PASS=true` | `0.0.0.0:38443` + nft dnat | **空闲** |

> AMD 迁移时用了 `--no-restart` 安装 + 一次计划内重启（先停 `soco-watchdog` 再重启，完成后再拉起）；
> 同时清掉了 mesh 遗留孤儿实例（`/run/soco-mesh/mesh-2.conf`，50302）与 ARM 上重复的 nft dnat 规则。

## 9. nfu / soga 生态兼容（2026-11-25）

`bash <(curl -Ls https://config.nfdns.xyz/nfu_sh/install.sh)` 这套工具直接可用，流媒体配置交给它。

| 组件 | 作用 |
|---|---|
| `/usr/bin/soga` | 兼容入口：`soga restart/stop/start/log/config/status/list` 全部转到 soco（nfu 最后一步是 `sudo soga restart`） |
| `soco-routes-guard.path` + `.service` | 监听 `/etc/soga/routes.toml`：nfu 用模板覆盖后，自动把「Netflix/OpenAI → 台湾出口」补丁插回（幂等、避开 nfu 半截写入、追加空行触发 soco 热加载） |
| `soco-watchdog.service` | ARM：每 30 s 真实 VLESS/REALITY 握手探活，连续 3 次失败重启 soco（详见 `arm64/evidence/NFU_COMPAT_20261125.md`） |

`nfu soga` 的实际动作（读 nfu.sh）：

```bash
wget -O /etc/soga/routes.toml https://config.nfdns.xyz/nfu_sh/config/soga/routes.toml
sed -i "s/{UUID}/.../g; s/{Out}/.../g; s/{OutPort}/.../g" /etc/soga/routes.toml
sudo soga restart
```

因为 soco 与 soga 共用 `/etc/soga`，前三步天然兼容；最后一步由 `/usr/bin/soga` 兜住；覆盖掉的分流补丁由守卫自动补回。

> 之前「两个实例互相污染、在线人数从 497 掉到 6」的原因是实验实例和生产实例用了**同一个 webapi 域名**（/etc/hosts 被指到 mock），不是 soco 内部共享状态。多实例只要各自面板地址不同就不会互相覆盖。