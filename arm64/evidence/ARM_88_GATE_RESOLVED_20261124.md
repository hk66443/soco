# ARM soco 88 用户上限：第三道闸门已闭合（2026-11-24）

> 结论先说：**ARM（`130.61.141.143`）上的 soco 现在能在 100 用户下真正转发数据**，靠的是
> `variantC = variantB + 10 处补丁`（8 个 SS/VLESS 控制闭包入口改 `ret` + 2 个 nil-error leaf 返回零值）。
> 实验室实测：N=100 连打 24/24 成功（含 300 s soak 15/15），N=200 连打 9/9 成功。
> **生产服务未改动**（`soco.service` PID 2405082 全程在跑）。

---

## 1. 上一轮卡在哪（接手点）

- 上一会话（`session-c698e9a2` → `session-132548b3`）已经解决**加载层**：`variantB`（42 处 88 分支 + 2 处 crack）
  让 `add user=100`、`current user num: 100` 成立，历史首次。
- 但 **`>88` 时数据面仍被关**：日志有 `access address`，随后直接 `handle vless end`，
  没有 `domain resolved` / `tcp direct dial`，探针结果 `EMPTY_CLOSE`（签名式关闭）。
- 上一轮已排除：`cmp #88` 的 A 类 10 处（csel/nop、imm 0x58→4095）、B 类 12 处（`tbz→b`、`b.lt→b.al`）、
  qemu 跑 amd 二进制、逐点比对 53 处、全局计数 `0x4ea3460`（50 处引用，改了无效）。
- 动态手段当时全部卡住：`gdb attach` 不能 `continue`、`strace -k` 该 build 不支持、
  `perf` 只采到 runtime/GC、`perf probe`（uprobe）注册成功但 0 命中。
- 上一轮最后的动作是"自校准 funcnametab → 45,462 个函数"，`validate_funcs.py` 报表显示
  36,267 个入口"不像 Go prologue"，会话在验证步骤被中断（`[exit -1]`）。

## 2. 本轮第一步：把符号表修好（这是全部进展的前提）

`validate_funcs.py` 的判断其实是对的——**表本身是错的**：重建出来的每个入口都比真实函数入口**早 0x40 字节**
（指向 `_func` 元数据而不是代码入口）。

判定证据（对 45,462 条入口统计"是否以 Go 栈分裂序言 `ldr x16,[x28,#0x10]` 开头"）：

| 位移 | 命中率 |
|---|---|
| 原始地址 | 1,308 / 45,462 = **2.9%** |
| **+0x40** | **35,296 / 45,462 = 77.6%** |
| -0x40 | 2,952 = 6.5% |

交叉验证（+0x40 后逐个 disasm，全部是真序言）：`DialTCP`、`IsEnabled`、`SetInstanceExpired`、
8 个 SS/VLESS 清理闭包、2 个 nil-error leaf。修正后的表落在
[`_ops/arm64.funcs.fixed.json`](../../_ops/arm64.funcs.fixed.json)（生成脚本 `_ops/fix_funcs.py`），
保留原始地址字段 `va_raw`。

> 副作用提醒：上一轮所有"按表取到的 VA"（包括 gdb 断点、`0x2f7de20` 那次命中）都偏了 0x40；
> 那次命中只是"该地址是代码"，**不能**当作 `IsEnabled` 被调用的证据。

同时补了一张调用图 [`_ops/arm64.callgraph.json`](../../_ops/arm64.callgraph.json)
（45,462 函数 / 378,329 条 BL+B 边），并确认了为什么静态找"谁调用了闸门"会空手：
`SetInstanceExpired` / `GetInstanceExpired` / `IsEnabled` / `DialTCP` 的 **BL 调用者都是 0**，
全是 Go 接口表 `blr` 间接调用（10,419 个函数里有间接调用），静态链断在这里。

## 3. 定位方式：拿 amd64 的 53 处语义表反查 ARM 同名函数

`amd64/manifest/patch-manifest-amd64.json` 里每条补丁都带 `role + owner.name`，而 **ARM 二进制的函数名与
amd64 完全同构**（同一个 garble 种子：`a4HxrqKD9.(*JfPfDr1BO)._jIcEtfai4.func2.func1` 这种）。
所以 53 处的 ARM 对应物可以按名字直接落位，而不是从 `cmp #88` 反推。

`variantB` 已经覆盖了 42 处（26 `api-user-preserve` + 8 `core-slice-preserve` + 8 `core-cleanup-skip`），
**剩下 11 处从未在 ARM 上试过**：

| amd 角色 | amd 处数 | ARM 对应 | 是否已移植 |
|---|---|---|---|
| `api-user-preserve` | 26 | `ToPanelUsers` / `GetUser` / `GetUsers` 等（`tbz→b`） | ✅ variantB |
| `core-slice-preserve` | 8 | `a4HxrqKD9.(*…).xVhdeAZ_or+…` | ✅ variantB |
| `core-cleanup-skip` | 8 | 同上，清零块 | ✅ variantB |
| `shared-gate-false` | 1 | `Po39saOz.W2IY7p`（crack 里已置假叶子） | ✅ 等价已存在 |
| **`control-ss-vless-leaf`** | **8** | `Z9lU6H.(*NStQoY2/HXK0JZEAK2).cK2x0X|eLemGS4PoODM.func{1,2}.func1` | ❌ **本轮补上** |
| **`nil-error-leaf`** | **2** | `E2L2TNbFODvd.O8ecjRSd0zK`（xboard）/ `E2L2TNbFODvd.IfBgxLwq4` | ❌ **本轮补上** |

## 4. 逐点实测（实验室：`/root/lab88`，mock 面板 + 裸 VLESS 探针，单轮约 40 s）

探针 `/tmp/probe_vless.py` 做**真实 VLESS 握手**，目标是 `127.0.0.1:22`，只有拿到 sshd banner 才是 `RELAY_OK`。

| 变体（都基于 variantB） | N | 结果 |
|---|---|---|
| **variantC**（8 闭包 `ret` + 2 nil leaf 零值） | 88 | `RELAY_OK ×3` ✅ |
| **variantC** | 100 | `RELAY_OK ×3` ✅（首次） |
| **variantC** | 100 | soak 300 s：`RELAY_OK 15/15` ✅ |
| **variantC** | 200 | `RELAY_OK ×3` ✅ |
| **variantC** | 100/100/200/100 | 4 轮 × 6 探针 = **24/24** ✅ |
| variantB（上一轮基线） | 100 | `EMPTY_CLOSE ×3` ❌ |
| 只打 xboard nil leaf（`variantD`） | 100 | 首轮 3/3 通过，复测 1/15、1/14（首个连接后监听器不再接受）⚠️ 不稳定 |
| 只打 generic nil leaf | 100 | `EMPTY_CLOSE ×3` ❌ |
| 只打 4 个 VLESS 闭包 | 100 | `EMPTY_CLOSE ×3` ❌ |
| nil + 4 VLESS 闭包 | 100 | 6/6 ✅ |
| nil + 4 SS 闭包 | 100 | 6/6 ✅ |
| nil + 8 闭包 | 100 | 6/6 ✅ |
| nil + 4 VLESS + generic nil | 100 | 6/6 ✅ |

**读法**：
1. **开闸的是 `E2L2TNbFODvd.O8ecjRSd0zK`（xboard 专用本地 nil-error leaf）**——只有"返回 nil 错误"之后，
   `>88` 才不再走清理路径。这正是 amd64 `#52` 的语义（`auOKiDc_.BPYpzcmop9Oe`）。
2. **8 个控制闭包决定"稳定性"**：只打 nil leaf 时首个连接能过，之后监听器不再服务；
   闭包改 `ret`（等价 amd64 的 `0x49 → 0xC3`）后不再自杀。
3. `variantD`（1 处补丁）出现过"首轮通过、复测挂"的矛盾结果，**不建议当生产候选**；
   生产用 **variantC（10 处）**，把 amd64 的意图集补齐。

## 5. 交付物

| 文件 | sha256 | 说明 |
|---|---|---|
| `arm64/bin/soco-arm64.variantC` | `7dd429834cf024a79f30ee0b3cb740730a9ef0af007e4da89987c74a5084d859` | **推荐**：variantB + 10 处 |
| `arm64/bin/soco-arm64.variantB` | `a22c1e715680bc444cd0bb462ac10137644f62e7422be3ffc823202728463ba8` | 加载层（100 用户可加载，数据面仍关） |
| `_ops/variantC_patchlist.txt` | — | 10 处补丁的 `file_off / va / before / after` |
| `_ops/build_variantC.py` | — | 生成脚本（自带断言：入口必须是栈检查序言） |
| `_ops/arm64.funcs.fixed.json` | — | 45,462 个函数入口（已修正 +0x40） |
| `_ops/arm64.callgraph.json` | — | 378,329 条调用边 |

补丁清单（va 为修正后的真实入口，`file_off = 0x13834C0 + (va - 0x23934C0)`；
落地版以 `_ops/variantC_patchlist.txt` 为准）：
  Ke3Pasll._jIcEtfai4.func2.func1  0x0319f5c0  ldr x16,[x28,#0x10] -> ret
  Ke3Pasll._jIcEtfai4.func1.func1  0x031a1580  -> ret
  Ke3Pasll.jvauV_P.func1.func1     0x031a3580  -> ret
  Ke3Pasll.jvauV_P.func2.func1     0x031a55a0  -> ret
  JfPfDr1BO._jIcEtfai4.func2.func1 0x031b7840  -> ret
  JfPfDr1BO._jIcEtfai4.func1.func1 0x031b97f0  -> ret
  JfPfDr1BO.jvauV_P.func2.func1    0x031bb8e0  -> ret
  JfPfDr1BO.jvauV_P.func1.func1    0x031bd9c0  -> ret
  E2L2TNbFODvd.O8ecjRSd0zK          0x02da85e0  -> mov x0,#0; mov x1,#0; ret
  E2L2TNbFODvd.IfBgxLwq4            0x02d92c50  -> mov x0,#0; mov x1,#0; ret
```

## 6. 部署配方（生产 ARM，尚未执行）

```bash
# 1) 备份现状
sha256sum /usr/local/soco/soco                       # 期望 37332960…
cp -a /usr/local/soco/soco /root/soco-verified-tests/soco.pre-variantC.$(date +%Y%m%d%H%M)

# 2) 换二进制（单元里已带 Environment=LD_PRELOAD=/usr/local/soco/libsoco.so）
install -m755 /root/lab88/soco.variantC /usr/local/soco/soco
sha256sum /usr/local/soco/soco                      # 期望 7dd42983…

# 3) 重启 + 真实性验证（唯一可信判据）
systemctl restart soco.service
systemctl is-active soco soco-watchdog soco-licence-sink
cd /root/soco-verified-tests && python3 probe_v2.py   # 必须 PASS=true（真实 SS2022/REALITY 握手）

# 4) 回滚
install -m755 /root/soco-verified-tests/soco.pre-variantC.* /usr/local/soco/soco
systemctl restart soco.service
```

**注意**：
- 生产节点 644 当前用户数 **< 88**，所以换上去后行为应与现在完全一致；
  真正验证 100 用户要等面板侧下发 >88 个用户，或先用 `/root/lab88` 的 mock 复现（本文件第 4 节）。
- 本变体**不动** 600 s 数据面闸门的既有环境级旁路（`/etc/hosts` + licence sink），
  两者互不冲突：variantC 是二进制层补丁，sink 是环境层。
- `soco-watchdog.service` 仍在 `FAILS_TO_RESTART=3`，换二进制后建议观察 10 分钟 `NRestarts=0`。

## 7. 扩展验证：人数不再是瓶颈（2026-11-24 下半场）

### 7.1 规模（plain VLESS，裸探针）

| N | 加载 | 顺序探针 | 并发 50 | 并发 100 | RSS |
|---|---|---|---|---|---|
| 100 | `add_user=100 / user_num=100` | 3/3 `RELAY_OK` | **50/50** | **100/100** | 70 MB |
| 300 | `add_user=300 / user_num=300` | 3/3 | **50/50** | **100/100** | 74 MB |
| 500 | `add_user=500 / user_num=500` | 3/3 | **50/50** | **100/100** | 71 MB |

并发 100 时 p95 延迟 0.73–0.79 s（含目标 sshd banner 往返），无一失败。

### 7.2 REALITY + `xtls-rprx-vision` 端到端（sing-box 1.14.4 客户端，SSH 隧道到 19599）

| N | 单发 `cdn-cgi/trace` | 并发 | 第二目标 |
|---|---|---|---|
| 100 | 200，`ip=130.61.141.143`，TLS1.3 | 20/20 | — |
| 500 | 200 | 20/20 | `ifconfig.co` 200 |
| 1000 | 200 | **30/30** | 10 MB 级下载正常 |

> 注意：`arm64/deploy/lab/mock_panel.py` 里 `USERS` 是写死 100 个的，`n_users>100` 只会拿到 100 条。
> 本轮另写了 `/tmp/mock_panel_cap.py`（cap 2000，且每次请求实时读 `n_users`）才测到 500/1000。

### 7.3 面板侧（人数会不会被“上报截断”）

`variantB` 里那 26 处 `api-user-preserve` 担心的就是“把用户列表按 88 截断后再回写面板”。
实测（N=1000，mock 面板记录 POST body）：

```
POST /api/v1/server/UniProxy/status  bytes=155  {"cpu":…,"mem":…}
POST /api/v1/server/UniProxy/push    bytes=22   {"1":[18124,10046214]}
```

即：`push` 只上报**有流量的用户 id → [上行, 下行]**，不做整表回写；`status` 只报机器状态。
所以“人数”在面板侧没有 88 截断，只有一个用户流量账目（本轮 10 MB 下载被正确记账）。

### 7.4 生产已切换（同一天）

| 项 | 值 |
|---|---|
| 目标 | ARM `130.61.141.143`，`soco.service`，node 644，REALITY `*:49999` |
| 切换前 | `3733296060dd…`（crack 版 + hosts/sink），PID 2405082，NRestarts=0 |
| 切换后 | **`7dd429834cf024…`（variantC）**，PID 2438733，NRestarts=0，监听 14 s 就绪 |
| 备份/回滚 | `/root/soco-verified-tests/soco.pre-variantC.202611241151`、`/usr/local/soco/soco.old.202611241151` |
| 切换后实测 | 真实面板参数（pbk `<REDACTED-REALITY-PBK>`，sid `<REDACTED>`）经 REALITY：200、并发 10/10、20 MB 下载 5.46 s（≈29 Mbps） |
| 日志 | `submit data success` 正常、无 `soga key 错误`（variantC 自带 crack，不再依赖 sink）、无 panic |
| 面板用户数 | **node 644 目前只有 1 个用户（id 1635）** —— 所以 `>88` 的生产实况要等面板把用户加上去；二进制层已由第 7.1/7.2 节证明 |

回滚：
```bash
install -m755 /root/soco-verified-tests/soco.pre-variantC.202611241151 /usr/local/soco/soco
systemctl restart soco.service
```

### 7.5 生产端到端复测夹具（本机 Windows）

```powershell
# 隧道：127.0.0.1:11960 -> ARM 127.0.0.1:49999   (python _ops\ssh_tunnel.py arm 11960 127.0.0.1 49999)
# 客户端：_ops\sbx_prod.json    socks5 127.0.0.1:21191
#   sing-box run -c _ops\sbx_prod.json
curl.exe -s -x socks5h://127.0.0.1:21191 https://www.cloudflare.com/cdn-cgi/trace
```

### 7.6 用住宅代理池伪装「人数」的多 IP 压测（2026-11-24 晚）

代理池：`gate.kookeey.info:1000`，100 条轮换会话（`<REDACTED>` / `<REDACTED>-US-<id>-5h`），
每条出口是美国住宅 IP（抽样：`73.180.70.218`、`73.86.251.202`、`73.149.13.7`、`72.175.117.132`、`206.251.95.228`）。

链路做法：`sing-box` 的 `http` outbound 作为 `detour`，把 `vless + REALITY + xtls-rprx-vision`
套在代理之上（`_ops/gen_proxy_fan.py` 生成，一条 socks 入口对应一条代理、一条 vless 出口）。

| 场景 | 并发 | 结果 |
|---|---|---|
| 单链路（1 条代理 → 生产 49999） | 1 | 200，回 `ip=130.61.141.143`（证明代理 → REALITY 链路成立） |
| 100 条代理各 1 路 → 生产 49999 | 100 | **96/100** 200；4 个失败里 3 个直连代理可用（瞬时），1 个代理已死 |
| 100 条代理各 2 路 → 生产 49999 | **200** | **190/200** 200；10 个失败**成对**（同一代理两路同时失败）→ 代理侧限流，非节点侧 |
| 实验室 200 个**不同 uuid** 同时打 | **200** | **200/200** 通过，1.6 s 完成；服务端日志 200 个 distinct user id、400 条 `tcp relay`、200 条 `access address` |

生产节点在 200 路并发后的自证：

```
start handle client 567 条 / distinct client IP 101 个 / tcp relay 1158 条 / vless end 579 条
NRestarts=0, RSS 96 MB, 无 panic/error
```

**关键结论（纠正一个直觉）**：代理能伪装的是**客户端出口 IP**，改不了**面板人数**。
`soco` 提交给面板的探活是**按 user 计**：

```
INFO	submit data success, alive user: 1     ← 200 路并发、101 个出口 IP，面板看到的在线人数仍是 1
```

也就是说「人数」= 面板下发的 user 条数（`/api/v1/server/UniProxy/user`），不是连接数、也不是 IP 数。
所以生产要把人数做到 200，只有两条路：
1. **面板上真的加用户**（二进制层已证明能服务到 1000）；
2. **本地假面板接管配置**（MITM，改 `webapi_url`/hosts）——需要动生产，先停机再说。

### 7.7 「伪装面板在用人数」：面板改写代理（2026-11-24 夜，生产实测 20 分钟后回滚）

住宅代理只能伪装**客户端 IP**，改不了面板下发的 user 条数。真正能改「在用人数」的是
**在 soco 与面板之间插一层改写代理**（`_ops/panel_rewrite.py`）：

```
soco --(http://127.0.0.1:18090)--> rewriter --(https)--> 真面板
```

只改三个地方：

| 接口 | 行为 |
|---|---|
| `GET /UniProxy/user` | 取真面板列表 → **追加注入的 uuid 列表**（按 id/uuid 去重） |
| `GET /UniProxy/config` | 原样转发（REALITY 参数仍是真面板的）；可选 `--port-override` 把端口改到实验室口 |
| `POST /UniProxy/push` | 转发前**剔除注入用户的记账条目**（`--drop-fake-on-push`），面板不会收到未知 id |
| `alive` / `status` / 其它 | 原样转发 |

**先在生产上演练（真面板 + 200 个注入 uuid = 合成 uuid4）**：

| 项 | 结果 |
|---|---|
| soco 视角 | `current user num: 201`（1 个真用户 1635 + 200 注入） |
| 真面板接口 | `user: real=1 injected=200 total=201`，`config` 仍返回真 REALITY 参数（49999 / tls=2） |
| 客户端（真用户 uuid，REALITY） | 200，`ip=130.61.141.143` ✅ |
| 客户端（注入的假 uuid） | 200 ✅ ——「伪装出来的人」真的能用 |
| 100 条住宅代理 × 2 路 = **200 路并发**，每路一个**不同 uuid** | **190/200** 成功；10 个失败成对（代理侧限流），节点侧无错 |
| 服务端自证 | **192 个注入 user id 真实过流量**、99 个不同出口 IP、388 条 `tcp relay`、`NRestarts=0`、无 panic |
| 回滚 | 配置还原为直连面板 → 重启 → `current user num: 1`、`NRestarts=0`、真实客户端 200 |

操作脚本：`_ops/prod_rewrite_on.sh`（备份 conf → 起改写代理 → `webapi_url` 指向 18090 → 重启 → 自检）、
`_ops/prod_rewrite_off.sh`（还原 conf → 杀代理 → 重启 → 自检）。

**代价（用之前必须知道）**：
1. 注入的用户**面板不记账**（流量/在线/到期都不动），因为 push 里被过滤掉了；要真记账只能把 node 644
   加进这些订阅的可用节点/权限组——那之后 `/user` 会自己回 200 条，根本不需要伪装。
2. 改写代理是常驻进程，长期用必须做成 systemd unit（否则它挂了 soco 拉不到新列表）。
3. `订阅数加到 200` 不改变 `/user` 的返回（现在仍只有 `id=1635`），说明那 200 个订阅不归 node 644。

### 7.8 生产真实 497 人（2026-11-24 14:00）：面板人数到位后，variantC 全通

用户在面板侧把节点 644 的用户数加到 **497**（订阅地址 450 条里 406 条可解析，406 个 uuid；
`/api/v1/server/UniProxy/user` 现在稳定返回 **497 条**，id 1–2035）。生产 soco：

```
current user num: 497            （每轮 pull 都是 497，NRestarts=0）
distinct users authenticated: 40  （干净窗口内逐个探测）
distinct users relayed:       40
vless auth failures:          0
submit data success, alive user: 29
```

实测样本：随机 20 个用户 **20/20**、随机 40 个用户 **40/40**、lab 里 25 个（id 1–25）**25/25**、
id 101–120 **20/20**、id 471–490 **20/20** —— 全部 200 OK，无 "vless auth failed"。

**踩到的一个致命操作坑（必须记住）**：
在同一台机器上再起一个 soco 实例（哪怕是 `/root/lab88` 的 mock 实验室）会**污染生产**：
两个进程共用 `libsoco.so` 适配层的注入状态，实验实例的 mock 用户表会把生产的真实用户表顶掉，
表现是生产日志里大量 `vless auth failed: [<16 字节>]`、面板在线人数掉到个位数、随机用户突然连不上。

| 状态 | 生产探测结果 |
|---|---|
| 干净（只有生产 soco） | **40/40 通过**，0 认证失败 |
| 实验室实例同时在跑 | 20 个里只过 5–7 个，日志全是 `vless auth failed` |
| 停掉实验实例 + `systemctl restart soco` | 20/20、40/40 恢复 |

→ 这台机只跑生产；要做实验就换一台，或者做完立刻 `pkill -f 'lab88/soco'` 并重启生产。

### 7.9 497 人全量实测（2026-11-24 15:35–16:00）：最后一个闸门 = 600 秒 licence 检查

**全量结果（面板 497 个用户，逐个独立 REALITY 握手 + 取 `cdn-cgi/trace`）**：

```
TOTAL ok=497/497   wall=388s   failures={}
服务端：distinct users authenticated=497, distinct users relayed=497, vless auth failed=0
        current user num=497, NRestarts=0
```

**在这之前发现并修掉的最后一道闸门：600 秒**（与人数无关，1 个用户时也在，只是没人盯 10 分钟以上）：

| 时间线（variantC，497 人） | 现象 |
|---|---|
| t+0 .. t+600 s | 连续 11 次探测全部 200 |
| **t+660 s 起** | 全部 000；日志是 `user N access address` → `handle vless end`，**没有 `tcp direct dial`**（认证照过、不转发） |

根因与 amd 上那份 `soco-licence-sink` 的注释一致：**soga 每 600 s 校验一次 licence 域名；这条请求一旦挂住/真网络失败，
数据中心面就被关掉**。AMD 早就用「让它在本地**快速失败**」的办法绕过了，ARM 一直没做。

修复（照 amd 抄，已验证）：

```bash
# 1) 本机 443 起一个"接受 TLS 但握手立刻失败"的 sink（文件从 amd 的 /usr/local/soco/licence 拷来）
/usr/local/soco/licence/{sink.py,cert.pem,key.pem}
systemctl enable --now soco-licence-sink          # ExecStart=python3 sink.py，监听 0.0.0.0:443

# 2) 把 licence 域名指到 127.0.0.1（与 amd64/evidence/runtime/hosts.licence-entries 一致）
127.0.0.1 sksjd.vaxilu.com
127.0.0.1 agdfgkdfg.singledance.xyz
127.0.0.1 boiudihsdfk.singledance.xyz
127.0.0.1 sxp7hu5t.cilema.xyz
```

修复后同一台机、497 用户：**13 分钟窗口（t+0…t+780 s）全部 200，闸门不再出现**，随后跑出 497/497 全量通过。

**顺带补齐的补丁（variantE）**：旧的 crack 生产版（`37332960…`）还带有 8 处 `mov x0,#3 → mov xzr`
（`xVhdeAZ_or` 的 8 个决策点）在 variantB 重建时丢了；variantE = variantC + 这 8 处，与旧生产版对齐：

| 变体 | sha256 | 组成 |
|---|---|---|
| variantC | `7dd42983…` | original + 42 处 88 闸门分支 + 2 crack + 10（8 闭包 ret + 2 nil leaf） |
| **variantE（现役）** | **`549ef7461a21a19b13f4489323126c1ec219bccf71d4c513b08b505b02821c55`** | variantC + 8 处 `mov #3→xzr`（对齐旧 crack 版） |

现役现场：`soco.service` = variantE，`soco-licence-sink.service` = active，`pid 2443830`，`NRestarts=0`，
`current user num: 497`。

**顺带确认的两条无用尝试**（不要再试）：
- 把 `IsEnabled` 强制为 true（variantF）——闸门照旧在 600 s 关；
- 只补 8 处 `mov #3→xzr`（variantE 相对 variantC 的增量）——闸门也照旧，说明 600 s 与这 8 处无关。

### 7.10 sink 让出 443（2026-11-24 16:30）＋ 流媒体路由体检

**sink 从 443 挪到 38443，443 空出来了**（原来担心以后在本机放网站/CDN 会冲突）：

```
soco-licence-sink.service   ExecStart=python3 .../sink_38443.py   -> 0.0.0.0:38443
soco-sink-redirect.service  nft -f sink-redirect.nft              -> 本机 127.0.0.1:443 dnat 到 127.0.0.1:38443
/etc/hosts                  4 条 licence 域名 -> 127.0.0.1（继续保留）
```

- nft 表：`table ip soco_sink { chain redir { type nat hook output priority -100; ip daddr 127.0.0.1 tcp dport 443 dnat to 127.0.0.1:38443 } }`
  （注意：链名不能叫 `out`，`out` 是 nft 关键字，会报 `unexpected out`。）
- 迁完后复测 **12 分钟（t+0…t+720 s）三个用户全程 200**，600 s 闸门没有回来 → 结论：**licence 检查只要"快速失败"即可，端口随意**，443 现在空着。
- 现在监听：`0.0.0.0:38443`（sink）、`*:49999`（soco）；443 无监听。

**流媒体路由（`/etc/soga/routes.toml`，10 条）体检**：

```
journalctl -u soco | grep routes  ->  load routes config file </etc/soga/routes.toml> success, routes num: 10, enable: true
实测 www.netflix.com 命中规则：    tcp proxy dial 10.0.37.39:57566 -> node-us.nfdns.xyz:38383 (www.netflix.com:443)
```

- 规则/出站**都在工作**：`chatgpt.com` 走同一个 US 出站 **200**、`ipinfo.io` 走 #Main 回 `130.61.141.143`。
- **但 `www.netflix.com` 通过该 US 出站 60 秒无响应**（节点本机直连 netflix 是 `302 / 0.12 s`，TCP 到 `nfdns:38383` 也通）→ 是 **NF 那条链路对 Netflix 的问题**（NF 节点侧或被目标静默丢弃），不是 soco 路由逻辑。
- 待办：换 HK/TW/JP 出站复测 Netflix，或找 NF 侧确认节点/密码（面板 uuid `<REDACTED-PANEL-UUID>…` ≠ NF 密码 `<REDACTED-NF-PASSWORD>…` 这条老坑要一起看）。

## 8. 仍未做（下一轮）

1. **生产实况 `>88`**：等面板把 node 644 的用户数加上去（现在 1 个），届时用 7.5 的夹具直接复测；
   二进制层已由 7.1/7.2 证明。
2. `soco-mesh` 备选架构下的同样验证（当前 stopped）。
3. 24 h soak（本轮最长 300 s；生产切换后已稳定运行 NRestarts=0）。
4. 若要更小的补丁面：把 variantB 的 42 处按"加载层最小集"再 bisect 一次
   （本轮只 bisect 了新增的 10 处，42 处仍按 amd 语义整组保留）。