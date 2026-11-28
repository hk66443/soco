# 交互控制台加固 + 清空重装全流程实测（2026-11-27 UTC）

> 现场：`AMD_IP`（amd64）。起点是「把机器上的 soco/so\*\* 全部删干净，再用公开仓库的一键命令重装，
> 验证正常与否」。同时做了一轮交互控制台的冒烟与加固（非交互 30+ 命令 / 交互菜单 15 项 / 边界输入）。
> 本轮所有改动已推到 `hk66443/soco`（`9d18377`）。

---

## 1. 清空：清到什么程度

清理脚本 `amd64/src/clear_all_20261128.sh`（只按可执行路径杀进程，不用 `pkill -f`）：

- 停 + disable 所有相关单元，删除 `/etc/systemd/system/soco*` / `so***`
- 删除 `/usr/local/soco`、`/usr/local/so**`、`/etc/so**`、`/etc/soco`、`/etc/so`、`/root/so`、`/root/so-backup-*`
- 删除 `/var/log/soco-watchdog.log*`、`/usr/bin/soco*`、`/usr/bin/so***`、`/tmp/probe-multi`
- `nft delete table ip nat`（我们建的 dnat 表）
- `/etc/hosts` 里 4 条 licence 域名整行删除

清理后核对（`amd64/src/clear_all_20261128.out.txt`，**全为 0**）：

```text
units(soco|so**):          0
dirs(/usr/local|etc|root): 0
listening ports:           0
processes:                 0
hosts licence lines:       0
nft tables:                0
keep evidence dir:         kept (/root/soco-verified-tests)
```

> `/root/soco-verified-tests` 是历史实验/证据目录（含本次的配置备份），不含运行依赖，故意保留。

## 2. 一键命令（全新机器，什么都不预置）

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/hk66443/soco/main/install.sh)
```

结果（`amd64/src/oneclick_run_20261128.out.txt`）：**11 秒**跑完，一次成功：

| 项 | 结果 |
|---|---|
| 项目落地 | `/root/so`，**165 个文件** |
| console | 73,058 B，sha256 `54064c77…`（修复版，无 `sink_up` 崩溃行） |
| watchdog | `f544137a…`（协议自适应统一版） |
| 二进制 | 从 release `v2.18.1` 下载：`soco` c463791a…（85,851,856 B）、`libsoco.so` 2f60b5f8… |
| 进入控制台 | 菜单正常显示（15 项 + quit） |

> 清空后 `sing-box-probe` 也没了 —— 它是探针客户端、不是服务依赖。重装后单独补：
> `curl -fL https://github.com/SagerNet/sing-box/releases/download/v1.14.5/sing-box-1.14.5-linux-amd64.tar.gz`
> 解出 `sing-box` → `/usr/local/soco/sing-box-probe`（缺它时 `install` 的 `[7/7]` 会 skip，不会假装通过）。

## 3. 控制台部署（用备份里的面板参数，key 不进命令行输出）

```bash
so-console install --node-id <N> --type ss --url <PANEL_URL> --webapi-key <KEY>
```

`amd64/src/deploy_after_oneclick_20261128.out.txt`：

```text
[1/7] 环境预检                   PASS
[2/7] 目录与二进制               PASS soco 82M
[3/7] 写入配置（主控信息 + 证书） PASS 原版模板结构 41 键
[4/7] 授权 sink + hosts + nft    PASS hosts +4
[5/7] systemd 单元               PASS 5 个单元 / daemon-reload / sink 38443
[6/7] 启动与状态                 PASS pid=456842 restarts=0 port=49989 就绪 12s
[7/7] 真实握手验证               PASS TOTAL ok=3/3
doctor 16/16 ✔    conf check 41/41 ✔    probe 3/3
```

跨 600 s 闸门（`amd64/src/gate_after_clean_20261128.out.txt`）：**uptime 1577 s**（跨 2 个检查点）、
同一 PID 456842、`NRestarts=0`、`gate` 5 项全 ✔、`key_err=0 / auth_fail=0`、`probe 3/3`。

## 4. 控制台本轮修掉的 7 个真问题

| # | 问题 | 以前的表现 | 现在 |
|---|---|---|---|
| 1 | `ask()/confirm()` 遇 EOF/Ctrl+C 直接 `raise SystemExit(130)` | 管道 / CI / `curl … \| bash` 场景下控制台被**静默杀掉**，看不到任何提示 | 抛 `Cancelled`：交互菜单回菜单，非交互打印「已取消」并退出 130 |
| 2 | `conf check` 里引用未定义的 `a` | 客户一旦改过 `type/api/间隔/log_level`，`conf check` 立刻 `NameError` 崩掉 | 改为 `k, cur, want` 解包，只提示「固定项被改动（建议改回）」 |
| 3 | `logs` 只有一个参数时全当 unit 名 | `so-console logs 20` → `journalctl -u 20`，输出恒为空 | 纯数字参数按「最后 N 行」，`main` 当主服务 |
| 4 | `rollback` 非 tty 且无 `--file` | 停在「选择 #」，**一直等 stdin**（实测挂到 300 s 超时） | 直接 rc=2：`非交互回滚要指定文件：--file <备份文件>` |
| 5 | 多机场实例「面板不可达」也报成功 | `inst new` 拉不到面板 config，实例仍 active，但**没有端口**（僵尸进程，白占 ~62 MB），主实例端口被误当实例端口判 PASS | `[5/7]` 硬校验 `server_port`，拉不到就 **FAIL + rc=3**，并自动删掉刚写的半截 conf |
| 6 | `inst remove` 非交互 | 停在 `确认删除？[y/N]`（EOF 后杀进程） | 非 tty 必须 `--yes`，否则 rc=2 提示；`--yes` 才真删（含 `disable --now`） |
| 7 | `service <乱写>` / 菜单 `?` / 大写 `Q` | 乱写会把 `systemctl <乱写>` 当命令跑；`?`、`Q` 当未知命令 | 动作白名单校验；新增 `?`/`h` 帮助、`q/Q/quit/exit` 都认 |

顺带新增：`conf get <键名>`（本地运维取完整密钥；`conf show` 仍脱敏）、
`probe all` 在 TTY 下先确认（297 用户逐个握手很慢，防误触）、`install` 非 tty 无参数直接给用法。

回归证据：`amd64/src/smoke1_20261128.out.txt`（30+ 非交互命令，0 崩溃）、
`amd64/src/smoke3_20261128.out.txt` / `v3_test_20261128.out.txt`（上表逐项复测）。

## 5. 第二轮（同一轮检查里又挖出来的 6 个）

| # | 问题 | 以前 | 现在 |
|---|---|---|---|
| 8 | **`install.sh` 见 `/root/so/console` 存在就跳过下载** | 老机器永远停在第一次装的版本，修好的补丁**一条都到不了客户手里** | 默认「拉最新 + 覆盖程序文件」（`SO_SKIP_PULL=1` 才沿用本地）；`/etc` 下配置不受影响。实测：把 console 降级成旧版 → 重跑一键命令 **1 s** 后 sha 与 GitHub main 一致 |
| 9 | 两个 `install` 并发 | 抢同一批 unit / sink / hosts，互相踩 | `flock /tmp/.so-console.deploy.lock`，第二个直接 rc=2 提示「另一个正在部署」 |
| 10 | `backup` 默认不清理 | 一份 ~70 MB，客户跑几个月把 `/root` 撑满，最后连 install 都写不进 | 默认 `--keep 3`（`--keep 0` = 不清理），并打印保留策略 |
| 11 | `rollback --file` | 先查默认目录 `/root` 有没有备份 → 没有就直接「没有备份」，给了 `--file` 也没用；且解包前不校验内容 | `--file` 优先；解包前做**路径白名单**（只允许 `bin_dir` / `inst_dir`）；非 tty 需 `--yes` |
| 12 | `/etc/hosts` 不可写（容器/immutable） | `OSError` traceback | 该步判 FAIL 并说明「600 s 闸门不会被压制」 |
| 13 | `inst remove` | 只删 `<name>.conf`，`instances/<name>/` 私有日志目录残留 | 一并删除 |

回归（`amd64/src/v6_test_20261128.out.txt`、`oneclick_update_20261128.out.txt`）：
锁拒绝 rc=2、备份裁到 3 份、恶意 tar（含 `etc/passwd`）**rc=4 被拒且服务不动**（pid 未变）、
实例目录随删除清空、`probe 1/1`、菜单 3/6/9/15/`?`/`Q` 全 rc=0。

## 7. ARM 节点同步升级（node <ARM_NODE_ID> / VLESS+REALITY）

ARM（`ARM_IP`）原来停在很旧的 console（`0d312ad9…`，72,429 B），本轮一并处理：

| 动作 | 结果 |
|---|---|
| 一键命令更新 | `覆盖更新程序文件` → console `0d312ad9` → **`5ded1556`**（0 s，二进制 549ef746 未动） |
| watchdog | `9144 B`（VLESS 专用旧版）→ **`f544137a`** 统一版；重启后 `{"event":"probe_ok","type":"vless","server_port":49999}` |
| `doctor` | **16/16 ✔**（含 nft dnat / hosts / 面板可达） |
| `conf check` | 41 / 41 ✔ |
| `probe 3` | **3/3**（VLESS/REALITY 真实握手，走同一份 `probe_many.py`） |
| `gate` | 5 项全 ✔，`soco` PID 2543124 全程未变、`NRestarts=0` |
| 之后再更新一次 | console → `cfe40087`（下面第 8 节），`users` 不再误报 |

## 8. 又一个假告警：把历史日志里的「498」当成当前人数

ARM 上 `users` 一直报「本地 498 ≠ 面板 297」，看着像同步坏了。实际是：

- `so**` 的日志文件**按天切分**（`so**-vless-2026-11-26.log`），重启不会重写；
- `_user_num_from_logfiles()` 先扫 `/var/log`，命中 `daemon.log`（syslog **副本**）——
  这个文件**一直在被写**，所以「文件 mtime 检查」通过，但里面那条 `current user num: 498`
  是 `Nov 26 03:03:37` 的（本次启动是 `11-27 03:35:24`）。

修复（`30c242b`）：

1. 只扫 `/etc/so**` 与 `/usr/local/soco`，**不再扫 `/var/log`**（daemon.log / syslog 都是副本）；
2. 新增 `_line_epoch()`：解析 `YYYY/MM/DD HH:MM:SS` 与 syslog 的 `Mon DD HH:MM:SS`；
   **行时间戳必须 ≥ 本次启动 − 60 s**，解析不出来就不采信；
3. `users` / `status` / `doctor`：非实时来源一律标注「历史快照，仅供参考」，**不参与一致性判断**。

夹具实测（`amd64/src/v8_test_20261128.out.txt`）：

| 夹具 | 期望 | 实际 |
|---|---|---|
| 旧文件（mtime 11-26）+ 行时间 11-26 | 不采信 | `-`  不可读 ✔ |
| 新文件（mtime 现在）+ 行时间 11-26（daemon.log 情形） | 不采信 | `-`  不可读 ✔ |
| 新文件 + 行时间是现在（111） | 采信 | `111…历史快照，仅供参考` ✔ |
| 删除夹具后 | 回到不可读 | `-` ✔ |

ARM 复测：`users` 显示「本地 -（不可读）/ 面板 297」，不再出现假的「不一致 → logs 80」。

## 10. 第三、四轮：边界与异常路径（22 项，**已推送 `4022e1a`**）

> 这一轮全是「输入不合法 / 环境不完整」时暴露的问题。改动落在 `_ops/public/console/so-console`
> 与 `_ops/probe_many.py`，已推送（`4022e1a`）；AMD 装的是 `87cb2051…`（v15），
> `raw.githubusercontent.com/hk66443/soco/main/console/so-console` 与之一致（92,931 B）。

| # | 问题 | 以前 | 现在（实测） |
|---|---|---|---|
| 14 | `routes validate` 坏 toml | 把 python 的整段 traceback 原样贴给客户 | 只留最后一行错误 + 「改回去或删掉这个文件」；不再有 traceback |
| 15 | `logs <不存在的 unit>` | 显示「(空)」rc=0，看不出问题 | `✘ 没有这个单元：xxx（不加参数就是主服务 soco）` rc=1 |
| 16 | `probe 2 abc` | 探针抛 ValueError，控制台只留「退出码 1」 | `✘ 用户索引只能是逗号分隔的数字：abc` rc=2 |
| 17 | `probe 3 1,999` | 实际只测 1 个，却不说明 | 加提示「只测了 1 个：索引越界会被跳过」 |
| 18 | 探针崩溃 | 只有「退出码 1」 | 打印探针尾部输出（最多 4 行），能看出是拉不到用户还是索引非法 |
| 19 | `conf keys` 配置不存在 | rc=0、键数 0，像正常 | rc=1 + `配置不存在：<path>` |
| 20 | `install --type vmess/trojan` 未给 `--cert-mode` | 静默写成无证书配置，装完服务起不来 | rc=2 + 列出 `--cert-mode panel\|self\|file\|http\|dns` 与例子（`vless` 走面板 REALITY，仍允许不带） |
| 21 | `inst new <名> --type vmess` 同上 | 同上 | rc=2 同一句提示 |
| 22 | `verify` 有失败项 | 恒返回 0，脚本里没法判断 | 失败项计数 → rc=1；并区分「unit 缺失」「主服务没在跑」 |
| 23 | `gate` 主服务没在跑 | 仍报「闸门已被压制」 | 第一项就是「主服务 active」，没在跑直接结论 `✘` |
| 24 | `service restart` | 固定 `sleep 2` 就打状态 → 端口还没起，显示 DOWN，看着像重启失败 | 轮询到端口 LISTEN（实测 17 s）再打状态，并 `✔ :49989 已就绪` |
| 25 | 菜单 12（backup） | 追问参数缺失，菜单里无法指定 `--keep` | 加进 `NEEDS_ARG`，可输入 `--keep 2` |
| 26 | `probe_many.py` 并发 | 固定 `/tmp/probe-multi` + 端口 12100+i：两个 probe 同时跑会抢端口 → 随机 FAIL；目录越攒越多 | 每次运行用 `/tmp/probe-multi-<pid>` + 端口段 `13000+(pid%1000)`；跑完自动清理；输出带 `conf=` |
| 27 | 实例部署的 `[7/7]` 真实握手 | `probe_many.py` 默认读**主配置** → 「主实例通」被当成「实例通」，实例假的 PASS | 支持 `SO_PROBE_CONF`；实例部署时传实例自己的 conf（`conf=` 一行可在输出里核对） |
| 28 | `human_size` | 调外部 `du`（最小化镜像可能没有） | 纯 Python 计算 |
| 29 | `status` 内存显示 | `102060`（KB 裸数字） | `07:36 / 67 MB / CPU 1.1%` |
| 30 | `probe` 输出 | 只有 TOTAL | 多一行「抓取 · users=N sample=M type=ss conf=…」 |
| 31 | `so**_key` | 每次 install/修复都**随机换掉**授权密钥（面板侧若比对就断一次） | 幂等：`--so**-key` > 已有配置 > 随机；实测重跑前后 sha 一致 |
| 32 | 实例端口与主实例相同 | 实例拿**主实例的 listener** 判 PASS（`ss` 只看端口有人听） | 必须「实例自己的 PID 在监听」才算过；否则 `[6/7] FAIL 实例没监听自己的端口 X；该端口已被别的进程占用` |
| 33 | `[6/7]` 失败 | 只打 FAIL，部署仍 `rc=0` | 计入失败步骤 → `1 个步骤未通过` + `rc=1`（实测） |
| 34 | 无版本号输出 | `--version` 是未知命令 | `version` / `-v` / `--version` → `so-console 2.1 (amd64, python 3.13.5)` |
| 35 | 实例重跑换面板密钥 | 实例 `webapi_key` 每次随机 | 已有实例配置则沿用（同主实例规则） |
| 36 | 一键更新只拉项目、不更新运行期脚本 | console 已是新版，`/usr/local/soco/probe_many.py` 还停在**第一次 install** 拷进去的旧版（AMD、ARM 都实测到） | `install.sh` 拉完项目后同步 `probe_many.py` / `soco-watchdog.py` / `routes-guard.py` / `licence/sink.py` 到 `bin_dir`（旧文件先 `.bak.<ts>`，相同则跳过），并提示 watchdog 要重启才生效 |
| 37 | `probe_script()` 只认 `bin_dir` | 「项目更新了但没重装」的机器一直跑旧探针 | 按 mtime 取最新一份（bin_dir 与 `pkg/_ops` 之间） |
| 38 | `install.sh` 里 `[ x = y ] && say` | `set -euo pipefail` 下条件为假 → 整个脚本退出 | 改成 `if` 语句；同步失败只提示不中断 |
| 39 | licence sink 证书缺失 / 端口被占 | `FileNotFoundError` / `OSError` traceback 刷满 systemd 日志 | 一句人话 + 退出码 2/3，并直接给出生成自签证书的命令；`accept` 对 EINTR 重试 |
| 40 | `backup` 把 `.bak.*` / `__pycache__` 打进新备份 | 备份自我膨胀（每备一次都大一截） | tar filter 排除；实测 `.bak` / `__pycache__` / `.pyc` 均 0 条，关键文件仍在 |
| 41 | `rollback` 后立刻打状态 | 端口还没起 → 显示 DOWN，看着像回滚失败 | 等服务 active + 端口 LISTEN 再打；服务没在跑时明确说「服务状态是 inactive（没在跑）」 |
| 42 | `probe_many.py`：面板 0 用户 / count 非数字 / 索引全越界 | `0/0` 假成功 rc=0；`ValueError` traceback | rc=3 / rc=2 / rc=3，各带一句原因 |
| 43 | **`install.sh` 临时目录在 `/tmp`** | 这台 `/tmp` 是 **tmpfs 482 MB**，解 37 MB tarball + 82 MB 二进制时 `No space left on device`，tar 只写了 1536 字节 | 改 `/var/tmp`；下载前检查父分区 ≥ 350 MB，不足直接 die |
| 44 | `tar xzf` 失败 | 报错后继续往下跑（看着像装好了） | `\|\| die` 明确失败并说明多为空间不足 |
| 45 | release 二进制没有完整性校验 | 下载损坏/被中间页替换也照装 | 下载 `SHA256SUMS` 校验 tarball（**该文件是 CRLF 行尾，必须先 `tr -d '\r'` 再 grep，否则永远匹配不到、静默跳过**） |
| 46 | **在 `/root/so` 里 `bash install.sh`** | 脚本拉项目时把自己覆盖掉，bash 按已打开的 fd 继续读新内容 → 后半段行为错乱（实测新版脚本跑出旧版行为：临时目录还是 `/tmp`、没有校验） | 拉取改用 `tar --exclude='./install.sh'`；实测执行前后 install.sh sha 不变 |
| 47 | `probe_many` 工作目录 | 在 `/tmp`（tmpfs 满时 `OSError [Errno 28]`） | 改 `/var/tmp`；目录不可写时 rc=4 并提示 |
| 48 | `backup` 目录剩余空间 | 满了才在 tar 中途失败 | 备份前 < 200 MB 就 `warn` 提示 |
| 49 | **`rollback` 白名单只做前缀匹配** | `usr/local/soco/../tmp/x` 能混过检查；ARM 是 **py3.9，`extractall` 没有 `filter` 参数** → 真的会写到目标目录之外 | 按 `normpath` 判是否落在 `bin_dir`/`inst_dir`；含 `..`、绝对路径、`~` 一律拒绝；逐成员解包（3.12 用 `filter='data'`，3.9 走已校验路径），跳过符号/硬链接。实测 `/etc/pwned` 未被创建 |
| 50 | **`rollback --file` 接受任意 tar** | 一个 **4 字节 soco** 的 tar 就把生产 `/usr/local/soco/soco` 覆盖了（进程跑旧 inode 没断，靠 `SO_FORCE_BIN=1` 重新下载才恢复 `c463791a…`） | 备份里必须含 `bin_dir/soco` 且 ≥1 MB，否则 rc=4「这不是一份完整的 so 备份」；解包后再校验大小，异常直接 rc=5 并提示重装 |
| 51 | `rollback` 不检查成员类型 | 符号/硬链接可跳到别处 | 只落 regular / dir，symlink / hardlink 跳过 |
| 52 | watchdog marker 端口被占 | traceback → systemd 无限重启 | `marker_bind_failed` 日志 + 人话 + **rc=1**；顺带修掉 `if __name__=='__main__': main()` 丢弃返回值 |
| 53 | watchdog socks 端口固定 11009 | 遗留 sing-box 占着它 → 重启后探针永久起不来（要么误重启健康服务、要么永远 skip） | 启动时挑空闲端口（11009–11028），日志带 `socks_port`；实测选到 **11010** 并 `probe_ok` |
| 54 | `probe_many` 配置缺键 | `KeyError: 'webapi_url'` traceback | `配置缺少 webapi_url, webapi_key（conf=…）` rc=1 |
| 55 | `install.sh` 的 git clone 回退 | 先 `rm -rf "$DEST"` 再 clone —— clone 失败时已装的目录已经没了 | 先克隆到 `/var/tmp/so-clone.*`，成功后再 tar 覆盖 |
| 56 | 现场事故（本轮自伤） | 验证 49/50 时拿**真实** `bin_dir` 做隔离测试，把 `/usr/local/soco/soco` 写成了 4 字节 | 生产进程未受影响（跑旧 inode），`SO_FORCE_BIN=1` 重新下载恢复；此后所有回滚测试固定用 `/tmp/fakebin` |

> 49/50/51 在 AMD（py3.13）与 ARM（**py3.9**）两台都实测过：正常备份 rc=0 且 `soco` 恢复到 2,000,000 字节；
> 穿越备份 rc=4 且 `/etc/pwned` 不存在；4 字节 soco 备份 rc=4「不是完整的 so 备份」。
| 57 | **watchdog 退出不清理 sing-box** | `systemctl restart` 只杀 watchdog 本体，sing-box 变孤儿继续占 11009 端口和 ~80 MB 内存（本轮实测踩到，只能换端口） | 装 SIGTERM/INT/HUP handler + `atexit`，退出时 terminate/kill client；实测两台重启后旧 pid 消失、11009 被回收 |
| 58 | `probe_many` 面板返回非 JSON（HTML 错误页） | `json.loads` 抛 ValueError → traceback | `面板返回的不是 JSON（前 160 字节：<!doctype html>…）—— 查 webapi_url 是否正确、面板是否在维护` rc=1 |
| 59 | `probe_many` vless 缺 `tls_settings.public_key` | 生成非法 sing-box 配置 → 全部 FAIL，看不出原因 | 直接点明「面板侧这个节点没配 REALITY？」 |
| 60 | `probe_many` ss 缺 `cipher`/`server_key`/用户 `uuid` | `KeyError` | 逐个点名缺哪个键 |
| 61 | `backup` 打包 `/etc/so**/instances/<name>/` 私有日志 | 备份里带实例日志（长期可能很大） | 排除 `/instances`、`/access_log`；实测 0 条，`soco`/`libsoco.so`/`sink.py` 仍在 |
| 62 | 61 的匹配瑕疵 | 目录条目叫 `…/instances`（结尾没斜杠），`'/instances/'` 匹配不到 → 仍留 1 条 | 改成 `'/instances'` |

> 新增本地单测 `tools/test_probe_units.py`（9 项）：ss/vless 缺字段各给 SystemExit，正常 ss/vless 配置的
> 端口、reality 参数、server_name 全部校验通过。
| 63 | **watchdog 源码被 PowerShell 写坏编码（本轮自伤）** | 用 `Set-Content -Encoding UTF8` 改含中文的 `.py`，中文变成双重编码，**857 处 mojibake**；两台生产跑的就是这版（逻辑正常但所有中文提示全是乱码） | 用 `write`/`edit` 重建（12,974 B、`mojibake=0`），两台重新部署并逐文件核对 `mojibake=0`；**以后改源码只用 edit/write，不再用 Set-Content 覆写** |
| 64 | `backup` 产物的文件权限 | umask 022 → `-rw-r--r--`，而备份里含 `webapi_key` / `so**_key` / licence 私钥 | `chmod 600`；实测 `-rw-------` |
| 65 | `probe_many` 临时目录/配置权限 | 配置 644（内含 `server_key` + `uuid`）、目录 755 | 目录 `700`（`drwx------`）、配置 `600`（`-rw-------`）；实测抓取确认 |
| 66 | `pick_socks_port` 只试 20 个端口 | 端口密集被占时直接 exit → systemd 反复重启 | 试 50 个（11009–11058） |

> 本轮验证（两台）：`mojibake=0` 三个文件；watchdog 前台启动打印中文「marker 端口 18089 被占用（[Errno 98]…）；
> 不启动，避免把健康服务判成故障」并 rc=1；`backup` 产物 `-rw-------`；`probe` 运行期间的
> `/var/tmp/probe-multi-<pid>/` 为 `drwx------`、配置 `-rw-------`。
| 67 | **实例名 / `--name` 等于主配置名** | `inst new so**`（或 `install --name so**`）会写 `/etc/so**/so**.conf`：主实例的配置被"实例配置"覆盖，且 `soco.service` 与 `soco@so**.service` 同时读同一份配置、抢同一端口 | 名字校验拦住（`实例名不能是主配置名（so**）；换一个，例如 jp1`，rc=2）；实测隔离环境里 `so**.conf` 未被创建/覆盖，正常名字 `jp1` 仍照常走到 `[5/7]` 面板失败 |
| 68 | **licence sink 监听 `0.0.0.0:38443`** | 一个只服务本机 dnat 的端点开在全部网卡上（公网可达的额外暴露面） | 模板与两台生产 unit 都改成 `127.0.0.1:38443`（nft 只把 `127.0.0.1:443` dnat 过来），重启后 `ss` 显示 `127.0.0.1:38443`，`probe` 正常、`gate` 仍"闸门已被压制" |
| 69 | watchdog 无限重启 | 探针一直失败时会按下限反复 `systemctl restart soco`，把服务来回掐断（每次重启所有用户掉线） | 连续重启到 `STORM_LIMIT`（默认 5）后停手，只记 `restart_storm`；任意一次探活成功自动解除并清零（实测日志字段已就位，故障注入未做） |
| 70 | **`install.sh` 的同步段会把 `bin_dir` 覆盖成"项目目录里的版本"** | 本地改了、但还没推送时，跑一次一键命令就把探针/watchdog/sink 退回 GitHub 旧版 —— 实测 AMD 上 `probe_many` 落回 `16f21b03`、watchdog 落回 `f544137a`、sink 落回 `3a29ffbd`（而 console 是新版，所以看着"半新半旧"） | 这是设计使然（同步源就是 `${DEST}`）；已把最新文件同时放进 `/root/so` 与 `bin_dir`，并在 HANDOFF 标注：**推送前别跑一键命令**；推送后跑一次两处就齐了 |

> 排查记录：先怀疑有定时任务（`systemctl list-timers` / cron 都干净），再比对 `/root/so/_ops/probe_many.py`
> 与 `/usr/local/soco/probe_many.py` 的 sha 完全一致 → 确认是"一键命令同步段"导致；
> 重新部署后 **间隔 5 秒二次核对** sha 未回退，两台 5 个文件现已一致。
| 71 | **推送后复验（`12b5b17`）** | 之前"一键命令会把运行期脚本退回 GitHub 旧版" | 远端 `main` = `12b5b17`；`raw.githubusercontent.com` 上 6 个文件 sha 全部 MATCH；两台重跑一键命令 **0–1 s**、打印「运行期脚本已是最新」，`/root/so` 与 `/usr/local/soco` 五个文件 sha 全一致（`0e35c9ed` / `5abd2cba` / `d2dc74e7` / `bdaf9f2c` / `e4471443`）；`doctor` 全通过、`gate` 全 ✔、`probe 3/3`、soco PID 未变 |
| 72 | **控制台没有卸载入口** | 客户想清干净只能手工 `systemctl stop` + `rm -rf`，容易漏（实测手工清完还剩 2 个 unit 残留 + 一个 `ip soco_sink` nft 表） | 新增 `uninstall [--purge] [--yes]`（菜单 16）：停+禁用所有单元（含 `soco@<实例>`）、按可执行路径杀残留、删单元/目录/日志/临时目录、清 hosts 4 条、删 `ip soco_sink` 与 `ip nat`；**默认保留 `/etc/so**` 配置**，`--purge` 连配置一起删；非 tty 必须 `--yes`。隔离环境实测：默认保留配置 rc=0、`--purge` 后配置消失 |
| 73 | **ARM 上 `nft priority dstnat` 语法不被接受** | ARM 的 nftables 是 **v0.9.8**，`priority dstnat` 报 `invalid priority expression value`，`soco-sink-redirect` 直接 failed → `doctor` 的 `nft dnat` ✘（AMD 是 v1.1.3，两种写法都行） | 模板与两台 unit 统一改成 `priority 100`（等价数值），ARM 上 `soco-sink-redirect` active、`nft list chain` 正确、`doctor` 16/16 |
| 74 | **清空重装后 `[7/7]` 会 SKIP** | 清空会连 `sing-box-probe`（探测客户端）一起删掉，重装后 `probe`/`[7/7]`/watchdog 都用不了 | `install.sh` 的 `[7/7]` 明确提示怎么装（不假装通过）；本次 ARM 已按提示补装 `sing-box 1.14.5 arm64`，`probe 3/3`、watchdog `probe_ok type=vless` |

| 75 | **推送后双机同步复验（`0334789`）** | 72/73 的改动当时只在测试目录与 ARM 上，`_push` 里是**未提交、未推送**的工作区改动 —— 谁重跑一次一键命令，console 就退回 `0e35c9ed`（旧版，没有 `uninstall`、模板还是 `priority dstnat`） | 已提交并推送 `main = 0334789`；`raw.githubusercontent.com/hk66443/soco/main/console/so-console` = `c5693a8b…`（103,951 B，与本地逐字节一致）。两台重跑一键命令 **1 s** 到 `c5693a8b…`：`version` = `so-console 2.1 (arm64, python 3.9.2)` / `(amd64, python 3.13.5)`，`doctor` 全部通过（仅 `log_level=error` 的「本地人数不可读」提示）、`probe 3/3`（AMD `type=ss` / ARM `type=vless`）、`gate` 闸门已被压制、4 个单元 active、**soco PID 未变 / NRestarts=0**。非交互 `uninstall`（不带 `--yes`）两台都 rc=2 且 **units 4→4、二进制仍在**；licence 域名打 443 是完整 TLS 握手落到本机 sink（ARM 的 `priority 100` 同样生效）；AMD 现网 sink-redirect unit 也对齐成 `priority 100`（内核里已有的链仍显示 `dstnat`，语义等价，下次重建即 100） |

| 76 | **sink 依赖一直没闭合（HANDOFF §7.2 第 4 条）** | `soco.service` 只有 `After/Wants=network-online.target`；sink 靠自身 `Restart=always,RestartSec=3` 兜着，但开机竞态或 sink 与 soco 同时重启时，soco 启动阶段可能撞 600 s 授权检查（历史上 641 s 停摆的形态） | console 模板给 `soco.service` / `soco@.service` 补 `After=` + `Wants=soco-licence-sink.service`（`8fefcc68…`，已推 `9fa1ccf`）；**不给 sink 加 `PartOf=soco.service`**（会让主实例停止时带走实例节点正在用的 sink）；单测由 21 → **26** 项全绿；两台现网单元按同一形状补齐 + `daemon-reload` + `systemd-analyze verify` rc=0，`systemctl show soco -p Wants` 已含 sink；**未重启任何服务**：PID 未变、`probe 2/2`、`doctor` 全通过 |

| 77 | **本地人数永远读不到（`log_level=error`）** | 两台 `users` 都显示 `-`；`doctor` 把它当「固定项」查、`conf check` 把 `info` 判成「固定项被改动」，下一次 install 又静默写回 `error` —— 等于官方不支持看本地人数 | 控制台加 `--log-level error\|info`（`9b8ade1`，console `a0465a52…`）：`write_conf` 保留客户已选级别、单元模板 `LogLevelMax={log_max}`（`info` 时放开，否则 journal 侧仍过滤）、`doctor`/`conf check` 接受 `info`；单测 26 → **33 项**。两台切 `info` 各重启一次：PID AMD `467626→506373` / ARM `2577047→2587316`、`NRestarts=0`、`probe 3/3`、`doctor` 全通过，`users` **本地 297 = 面板 297（实时）**。日志量 1–3 KB/min/台 |
| 78 | **AMD 内核里的 nat 链与单元不一致** | 单元已是 `priority 100`，内核里那条链是历史建的 `priority dstnat`（显示不一致，虽然功能等价） | `nft delete chain ip nat redir` + `systemctl restart soco-sink-redirect` 重建：现在 `priority 100`，licence 域名走 443 仍完整 TLS 握手到 sink，`probe 2/2`、soco PID 未变（`506373`） |
| 79 | **ARM 的 routes.toml 丢了（清空重装的副作用）** | 11-28 清空重装后 `/etc/so**/routes.toml` 不再存在，`soco-routes-guard.path/service` 也没了 → **一条分流都没有**，所有站点走默认出口（DE），Netflix / ChatGPT / Disney+ 全不解锁（不只是"漏了几家站点"） | 用户说**先不动**，本轮未改；恢复源已确认：`_ops/routes-remote-20261123.toml`（961 行 / 26 KB）+ `_ops/routes_tw_patch.toml`（NF/OpenAI → `node-tw:20558`）；恢复步骤=放 `/etc/so**/routes.toml` → `soco restart` → `routes status` 看 rules 数 |

| 80 | **脚本审计第 1 轮：8 个真缺陷（`4713412`）** | ① `uninstall` 删整张 `ip nat` 表（docker/iptables-nft 的 NAT 链也在这张表里）；② `uninstall` 原地写 `/etc/hosts`（被杀 = 空文件），且按子串匹配会删掉注释里的域名；③ 对不存在的单元也 `systemctl stop`（刷屏）；④ `doctor` 在 info 刚重启时误判 FAIL；⑤ `probe_many` 端口段按 `pid%1000+i` 会与并发 probe 重叠 → 随机 FAIL；⑥ 固定 `sleep 2.0`；⑦ 清理不在 `finally`（SystemExit/Ctrl-C 留孤儿 sing-box + 含密钥目录）；⑧ vless 缺 uuid 抛 KeyError；⑨ watchdog `restarts` 只在 storm 时清零 → 真故障时反而不重启 | console `4810dda2…` / probe `c237dccf…` / watchdog `b81b0ac5…`：只删 `ip nat redir` 链；hosts 临时文件 + `os.replace` 且只匹配行尾域名；只 stop 存在的单元；doctor 改等待提示；`pick_port`（逐个 bind）+ `wait_port`（轮询 ≤6 s）；`finally` 收进程与目录；vless 缺 uuid 给人话；watchdog 探活成功即清零 + `restart_failed`/`restart_error` 记录。单测 console 39（+8）/ probe 13（+4），pyflakes 干净；两台同步后 `probe 3/3`、`doctor` 全通过、watchdog `probe_ok`、soco PID 未变 |

| 81 | **脚本审计第 2 轮：7 个真缺陷（装机器 / 守卫 / 授权 sink 这一面）** | ① `routes-guard` 原来取「全文第一个 `password=`」：trojan/vmess 出站排在 ss 前面时补丁拿到别的出站的密码 → 注入的 ss 出站认证必败 → **分流静默失效**；② 授权 sink 单线程 accept + 逐个握手，一个连上不发数据的客户端（扫描器/半开连接）就把后面全堵住，so\*\* 每 600 s 的授权检查跟着「挂住」→ 正好落进 600 s 闸门的停摆形态；③ 一键 `install.sh` 的 `find … \| head -1` 在 `pipefail` 下遇 SIGPIPE（find 141）会**无提示退出**，解包/复制失败还会漏 `/var/tmp/so-src.*`，缺 `python3` 要到 `exec` 才报错；④ `soco-uninstall` 只停 `soco.service`/`soco@.service`，watchdog / sink / sink-redirect / routes-guard 全留着，hosts 4 条与 nft 链也不清 → 卸完 **DNS 仍指向 127.0.0.1**（客户别的软件跟着坏）、38443 还占着、watchdog 还在拉 soco；⑤ `soco update` 的 `mktemp -d` 从不删（每更新一次留一份含二进制目录），`soco uninstall` 同样残留，`set_kv` 算好转义却没用（值含 `&`/`\|` 写坏配置）；⑥ `install-soco.sh` 失败分支把 HTTP 下载的 80 MB 二进制留在 `/tmp`；⑦ `so-console install` 不装 routes 守卫而 `uninstall` 会删 → 干净装机后 nfu 一重生成 routes.toml，TW 分流被冲掉且不报错 | routes-guard `6a499fee…` / sink `0c0d0b17…` / `install.sh` `526b36e9…` / `uninstall.sh` `4501b97d…` / `soco-multi.sh` `714783f7…` / `install-soco.sh` `cb6bbab8…` / console `17fc0f22…`：按 `[[routes.Outs]]` 分块只取 ss 块的 password（`has_ss_outbound` 仍全文匹配，只决定跳过/重试）；sink 每连接一线程 + 64 路信号量 + 独立超时（槽位满即 close，仍是快速失败）；`find -print -quit` + 全部临时目录 `trap` 收 + 开工前拦 `python3`；卸载按序停（watchdog 先）、只删本项目单元与 `.wants` 链接、hosts 临时文件 + `mv` 原子写回只删本项目域名、nft 只删自己的链/表；`soco update`/`install-soco.sh` 临时目录同样 `trap` 收；console 装 `soco-routes-guard.service`+`.path` 并 `enable+start`，`doctor` 加「routes 守卫 active」（**16 → 17 项**）。单测新增 `tools/test_routes_guard_units.py` 31 项 + `tools/test_sink_units.py` 14 项，console 39 → **45** 项，四套共 103 项全绿、pyflakes 干净 |

| 82 | **部署复验又照出 2 个（`cd5d6e4` + `82410df`）** | ① 两台机器上 `soco-routes-guard.path/.service` **实际都不存在**（`LoadState=not-found`），§3 里"已在"是重装前状态 —— 也就是说干净装机和重装后，nfu 一覆盖 routes.toml 就没有守卫了（正是 81-⑦ 的现场版）；② `install.sh` 一律 `--exclude=./install.sh`，用 `bash <(curl …)` 装机时 `/root/so/install.sh` **永远是第一次那份**（实测 pull 完仍是上一轮 `bdaf9f2c…`），用户下次直接跑本机那份就会踩回 `find \| head` 的 SIGPIPE 坑 | ① 按 `packaging/` 的单元补装 + `daemon-reload` + `enable --now soco-routes-guard.path`（等价于 console install 的动作），两台 `active`，手工跑一次守卫 → `routes file missing, skip`（routes.toml 仍是待办 17/79，用户说先不动；守卫已武装）；`doctor` 新行立刻从 ✘ 变 ✔；② `install.sh` 改成「只有正在执行的就是 `$DEST/install.sh` 时才排除」，否则照常覆盖（`82410df`，`70c91ae7…`）→ 实测 pull 完本机 `install.sh` 与远端逐字节一致 |

**第 2 轮部署复验（两台，2026-11-28）**：`bash -n` 7 个 shell 全 OK、`py_compile` OK；文件 hash 与
`_push` 逐字节一致（console `17fc0f22` / `install.sh` `70c91ae7` / routes-guard `6a499fee` / sink
`0c0d0b17` / uninstall `4501b97d` / multi `714783f7` / install-soco `cb6bbab8`，`bin_dir` 里的
`routes-guard.py`、`licence/sink.py` 同步刷新）；只重启 `soco-licence-sink`（38443 LISTEN ok，
打 443 证书校验 **0.01–0.02 s** 失败 = 设计上的快速失败），**soco PID 未变**
（AMD `506373` / ARM `2587316`，`NRestarts=0`）；`doctor` **17/17 ✔**、`probe 3/3`（AMD `type=ss`
:49989 / ARM `type=vless` :49999）、五单元全 active、`users` 本地 297 = 面板 297。

**现场事故记录**：验证 43/45 时把 `/tmp` 塞爆了（历史残留 `tmp.A6ehG0A5ks` 111 M、
`sing-box*` 三份 256 M、`bk4` 67 M、`x86pkg.tgz` 38 M …… 合计 482 M 占满 tmpfs），
`probe` 直接 `OSError: [Errno 28]`。清理后恢复 2/2。这也正是 43/44/47 的由来 ——
探针与安装器都不能把临时文件压在 `/tmp` 上。

回归：`pyflakes` 零告警、`tools/test_console_units.py` 21 项全 OK（含 `write_conf` 合并保留客户
自定义键、`conf_check` 缺键/多键判定、`_line_epoch` 两种格式、`human_size`）。
远端证据：`amd64/src/edge1_20261128.out.txt`、`edge2`、`edge3`、`v11`、`v12`、`v13`（`TOTAL_CRASHES=0`）。

## 11. 留档

- 清空前后配置备份：`amd64/src/so**-conf-backup-20261128.tar.gz`（5.3 MB，含原 `so**.conf` / `routes.toml`）
- 远端备份：`/root/so/console/so-console.bak.20261127*`（v1/v2/v3 各一份）
- 本文件配套脚本：`clear_all_20261128.sh`、`oneclick_run_20261128.sh`、`deploy_after_oneclick_20261128.sh`、
  `smoke4_20261128.sh`、`v3_test_20261128.sh`、`gate_after_clean_20261128.sh`（都在 `amd64/src/`）
- 第十轮（`0334789`）配套脚本：`_ops/sync_console_after_push_20261128.sh`（一键命令 + sha/doctor/probe/gate）、
  `_ops/uninstall_guard_20261128.sh`（非交互 `uninstall` 必须不动手）、
  `_ops/amd_unit_align_20261128.sh`（AMD 现网 unit 对齐 `priority 100`）、
  `_ops/dnat_detail_20261128.sh`（443 → 38443 sink 的 TLS 握手证据）
- sink 依赖补齐：`_ops/unit_sink_dep_20261128.sh`（改两台单元 + daemon-reload + verify）、
  `_ops/unit_sink_dep_close_20261128.sh`（单元内容 / 一键命令 / 新模板 / 现网未动 的收口核对）
- 日志级别与链对齐：`_ops/lvl_info_20261128.sh`（切 info + 重启 + 75 s 后核对本地/面板人数）、
  `_ops/nft_priority_align_20261128.sh`（AMD 删链重建 + dnat 握手验证）、
  `_ops/arm_routes_readonly_20261128.sh` / `_ops/arm_routes_sources_20261128.sh`（ARM 分流只读盘点，未改动）
- 审计第 1 轮：`_ops/apply_r13_20261128.sh`（一键命令 + 同步三个文件 + 只重启 watchdog + probe/doctor 复验）
- 审计第 2 轮：`_ops/apply_r14b_20261128.sh`（一键命令 + 9 个文件 hash + `bash -n` 7 个 shell +
  `py_compile` + 只重启授权 sink + 443 证书校验计时 + 补装 routes 守卫单元并手工跑一次 +
  `doctor`/`probe`/服务总览）。**注意**：第一版 `_ops/apply_r14_20261128.sh` 里的 443 探测用了
  `CERT_NONE`（不校验证书），会"握手成功"——那不是 sink 的问题，so\*\* 是校验证书的；已换成默认上下文，
  两台实测 0.01–0.02 s 失败。
- 单测：`tools/test_routes_guard_units.py`（31 项）、`tools/test_sink_units.py`（14 项）、
  `tools/test_console_units.py`（45 项）、`tools/test_probe_units.py`（13 项）