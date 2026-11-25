# CONSOLE · so-console 命令参考

单文件、无第三方依赖（只要 python3 ≥ 3.6），amd64 / arm64 同一份代码。
两种用法等价：**交互菜单**（不带参数）和**直接敲命令**（适合脚本 / 定时任务）。

```bash
/root/so/console/so-console              # 进控制台
/root/so/console/so-console status       # 一条命令
```

建议做个软链：ln -s /root/so/console/so-console /usr/local/bin/so-console
（下面示例都按 so-console 写。）

---

## 1. 命令总表

| 命令 | 作用 | 常用示例 |
|---|---|---|
| status | 一屏总览：服务/端口/人数/闸门计数/routes/实例/指纹 | so-console status |
| install [目录] | 安装或**修复**（幂等）：目录、二进制摆放、证书、hosts、nft、systemd、参数落盘 + 自动闸门自检 | so-console install /root/so |
| service <start\|stop\|restart\|status> | 主服务与 sink 一起动 | so-console service restart |
| users | 本地日志里的 current user num vs 面板 /UniProxy/user 条数 | so-console users |
| probe <N\|all> [idx列表] | 真实握手（串行，每个用户一个独立客户端） | so-console probe 3、so-console probe all、so-console probe 12 1,50,88,89 |
| gate | 600 秒闸门自检：hosts / sink / 38443 / nft / 10 分钟 key 错误 / uptime | so-console gate |
| routes list | 条数、首个 Outs 出口、loaded 状态 | so-console routes list |
| routes switch <us\|hk\|tw\|jp\|kr\|sg\|uk> | 切第一个 Outs 总出口（自动备份） | so-console routes switch tw |
| routes validate | TOML 合法性（防"静默 0 条"） | so-console routes validate |
| inst list | 实例 + 状态 + 重启次数 | so-console inst list |
| inst new <名> [k=v ...] | 从主配置复制一份 <名>.conf 并覆盖指定字段 | so-console inst new jp1 node_id=12 webapi_url=... |
| inst start\|stop\|restart\|log\|remove <名> | 实例生命周期 | so-console inst log jp1 |
| logs <unit> [行数] | journalctl -o cat 快照 | so-console logs soco 120 |
| backup | 打包 /usr/local/soco + 配置目录 | so-console backup |
| rollback [包] | 列出备份并恢复（先停服务，恢复后自动起） | so-console rollback |
| verify | 二进制 sha256、unit 关键行、适配层是否加载 | so-console verify |
| doctor | 13 项自检，逐项 PASS/FAIL + 修复提示 | so-console doctor |
| paths | 打印真实路径（配置/二进制/实例/console.conf） | so-console paths |
| help | 用法 | so-console help |

退出码：0 通过；1 检查失败/操作未达成；2 参数错误；3 缺二进制；124 子命令超时。

---

## 2. 交互控制台长什么样

```
 so-console · amd64 · 2026-01-01 12:00:00
==========================================================
  1) status    状态总览（服务/端口/人数/闸门/routes）
  2) install   安装或修复
  ...
so> 1
=== 2026-01-01 12:00:03 ===
arch        : amd64
service     : active     pid=12345    restarts=0
uptime/rss  : 03:12:44 78284 0.3
port        : 49989 (yes)
users(svc)  : 497
soco-licence-sink    active
soco-sink-redirect   active
soco-watchdog        active
gate(5m)    : key_err=0 auth_fail=0 relay=143
routes      : </etc/so**/routes.toml> success, routes num: 11, enable: true
instances   : so**
bin hash    : c463791ac4bf9ba8
```

在 so> 提示符下**也可以直接敲命令**（不用记编号）：

```
so> probe 3
so> routes switch tw
so> logs soco 40
so> doctor
```

---

## 3. 典型操作流

### 3.1 新机上线

```bash
so-console install /root/so     # 装完自动跑 gate 自检
so-console status               # 服务/端口/人数
so-console probe 3              # 3/3 才算通
so-console doctor               # 期望 ALL PASS
```

### 3.2 面板加了用户，客户端说连不上

```bash
so-console users                # 本地 vs 面板条数
so-console gate                 # 闸门是否被打开
so-console probe 3              # 真实握手
so-console logs soco 120        # 有无 access address 却没 tcp relay
```

### 3.3 换个流媒体出口地区

```bash
so-console routes validate
so-console routes switch jp
so-console routes list          # 看 loaded 那一行是否重新加载
```

### 3.4 挂第二个机场

```bash
so-console inst new jp1 node_id=112 webapi_url=https://panel2.example.com webapi_key=KEY so**_key=KEY
so-console inst start jp1
so-console inst log jp1
```

### 3.5 升级/换二进制

```bash
so-console backup
install -m 755 /path/to/new/soco /usr/local/soco/soco
so-console service restart
so-console verify               # 指纹变了说明生效
so-console probe 3
# 不对就： so-console rollback
```

---

## 4. 配置文件 /etc/so/console.conf

install 会写一次；之后想换路径/端口/服务名，改这里即可（每行 key=value）：

```ini
pkg=/root/so
bin_dir=/usr/local/soco
conf=/etc/so**/so**.conf
inst_dir=/etc/so**
service=soco
port=
arch=amd64
```

| 键 | 含义 |
|---|---|
| pkg | 项目目录（probe_many.py、watchdog 脚本从这里拷） |
| bin_dir | 二进制与 sink 证书所在目录 |
| conf | 主节点配置（sink 只拦授权域名，不动这里） |
| inst_dir | 多实例配置目录（<名>.conf） |
| service | 主 systemd 单元名（不带 .service） |
| port / arch | 留空则自动探测 |

环境变量 SO_CONSOLE_CONF 可指向另一份配置，方便在一台机上演练两套方案。

---

## 5. 它依赖哪些东西

| 依赖 | 用途 |
|---|---|
| systemctl / journalctl | 服务状态、日志、重启 |
| ss | 端口是否真的在听 |
| nft | 127.0.0.1:443 → 38443 的 dnat |
| openssl | 生成 sink 自签证书 |
| curl | 打面板 /UniProxy/user |
| python3 + probe_many.py | 真实握手（install 会从项目里拷到 bin_dir） |

缺哪个，install / doctor 的输出里会直接指出来。