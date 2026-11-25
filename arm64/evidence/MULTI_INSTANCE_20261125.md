# soco 多实例 + so\*\* 目录兼容（2026-11-25）

> 用户需求：**不用 docker 跑多实例**；程序和 so\*\* 的配置方式保持一致（-c / 多配置文件）；
> 项目仍叫 soco，但**流媒体等配置继续用原 so\*\* 目录 /etc/so**/**，这样 nfu so** 这类第三方脚本能直接用。

## 1. 结论

1. soco 就是 so\*\* 2.18.1 的后端，-c 的默认值本来就是 /etc/so**/so**.conf：
   ```
   /usr/local/soco/soco -h
     -c string   Set config file (default "/etc/so**/so**.conf")
   ```
   → **不需要任何改造就已经和 so\*\* 同目录、同文件名**。之前只是部署时用 -c /etc/soco/soco.conf 把路径引偏了。
2. 多实例用 systemd 模板 soco@.service（-c /etc/so**/%i.conf）或 screen/nohup 手工跑，均可用；
   每个实例独立 log_file_dir / ip_user_cache_save_dir / access_log_dir。
3. 同机多实例**不会互相污染**；之前「在线人数 497 掉到 6」的真因是实验实例与生产实例共用同一个 webapi 域名（/etc/hosts 被指到 mock），不是进程间共享状态。

## 2. 落地改动

| 机器 | 改动 | 结果 |
|---|---|---|
| ARM ARM_IP | soco.service 去掉 -c（用默认 /etc/so**/so**.conf）、soco@.service → /etc/so**/%i.conf、装 /usr/bin/soco、sink 规则去重 | 497 用户、49999、NRestarts=0 |
| AMD AMD_IP | 同上（--no-restart 安装 + 一次计划内重启）；soco-licence-sink 从 0.0.0.0:443 换到 38443 + nft 127.0.0.1:443 → 38443 | 497 用户、49989、真实 SS2022 握手 PASS=true、**443 已空出** |
| 两台 | 清理 AMD 孤儿 mesh 实例（/run/soco-mesh/mesh-2.conf，50302）、ARM nft 重复 dnat | 端口/规则干净 |

新增文件（工程 packaging/，服务器 /root/soco-pkg/）：

```
soco.service            主实例单元（无 -c，默认 /etc/so**/so**.conf）
soco@.service           多实例模板（-c /etc/so**/%i.conf）
install-soco.sh         安装/更新（保留 /etc/so** 与所有实例；--no-restart 可只改单元）
soco-multi.sh           /usr/bin/soco 管理脚本（list/new/remove/rename/start/stop/restart/log/config/update/uninstall）
MULTI_INSTANCE.md       使用文档（本文档的运行版）
```

## 3. 多实例实测（ARM，生产实例同时在跑）

| 项 | 数据 |
|---|---|
| 实例 A（mock 面板 19001，3 用户） | current user num: 3，*:30001，日志 /tmp/mi/A/so**-vless-2026-11-25.log |
| 实例 B（mock 面板 19002，5 用户） | current user num: 5，*:30002，日志 /tmp/mi/B/... |
| 生产实例（真实面板 node <ARM_NODE_ID>） | current user num: 497，*:49999，NRestarts=0，**全程未受影响** |
| 面板请求 | A/B 只打各自 mock（19001/19002），无交叉 |
| soco new lab1（systemd 实例） | 自动生成 /etc/so**/lab1.conf + /etc/so**/instances/lab1/，soco@lab1 active，*:30001，3 用户 |
| 实例数据面（真实 REALITY） | sing-box 客户端经 SSH 隧道连 30001 → cdn-cgi/trace 回 ip=ARM_IP，ifconfig.co 200 |
| soco remove lab1 | 配置删除、服务停止、30001 释放，生产 497 不变 |

## 4. 使用方式（一台机多机场）

```bash
soco new jp1 node_id=645 webapi_url=https://panel2.example.com webapi_key=KEY so**_key=so**Key
soco list
soco log jp1 -f
soco config jp1 check_interval=30
soco restart jp1
soco remove jp1
```

隔离规则（soco new 自动完成，手工复制配置时必须自己改）：

```ini
log_file_dir=/etc/so**/instances/<name>/
ip_user_cache_save_dir=/etc/so**/instances/<name>/
access_log_dir=/etc/so**/instances/<name>/access_log
```

不用 systemd 时：

```bash
LD_PRELOAD=/usr/local/soco/libsoco.so \
nohup /usr/local/soco/soco -c /etc/so**/jp1.conf \
  >>/etc/so**/instances/jp1/stdout.log 2>&1 &
```

> LD_PRELOAD 必须带；不带则适配层不生效（88 上限等回退原生行为）。

## 5. 流媒体（nfu / 第三方）

- 配置仍在 /etc/so**/：routes.toml、blockList、whiteList、dns.yml、geoip.dat、geosite.dat；
- nfu so** 写好之后重启实例，日志应出现：
  load routes config file </etc/so**/routes.toml> success, routes num: 10, enable: true
- 若某实例要单独一套 routes：在该实例 conf 加 routes_url=...，其余实例继续共享 /etc/so**/routes.toml。

## 6. 600 s 闸门（licence sink）现状

| 机器 | sink 监听 | 重定向 | 443 |
|---|---|---|---|
| ARM | 0.0.0.0:38443 | nft 127.0.0.1:443 → 38443（单条，已去重） | 空闲 |
| AMD | 0.0.0.0:38443 | 同上（新增 soco-sink-redirect.service） | **空闲** |

/etc/hosts 里 4 条 licence 域名继续指 127.0.0.1（必需，删了 10 分钟后会断流）。

## 7. 回滚

```bash
# 主实例回到旧布局（ARM/AMD 都有备份）
install -m644 /root/soco-pkg/soco.service.bak /etc/systemd/system/soco.service
systemctl daemon-reload && systemctl restart soco
# AMD sink 回到 443
install -m644 /root/soco-pkg/soco-licence-sink.service.bak.<ts> /etc/systemd/system/soco-licence-sink.service
systemctl stop soco-sink-redirect; systemctl daemon-reload; systemctl restart soco-licence-sink
```

## 8. 已知限制

1. 同一台机的多个实例共享 /etc/so**/routes.toml 与 geoip/geosite（只读，安全）；要不同分流用 routes_url。
2. 实例的服务端口由各自面板下发，不能撞；新建后 ss -lntp | grep soco 自查。
3. 同一台机多实例会叠加内存（soco ~90 MB/实例），ARM 只有 1 GB，建议 ≤ 3 个实例。
4. 不要用 pkill -f 清实例（会把执行命令的 shell 本身匹配掉，历史踩过）；用 soco stop <name> 或按 /proc/*/exe 判断。