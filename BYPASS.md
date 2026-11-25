# 绕过过程全记录（amd64 + arm64）

> 这份文档记录"怎么试、试出什么、什么被排除"，供接手的 AI 直接续上，不必重复踩坑。
> 所有时间戳为 UTC，主机为 Debian 13 (trixie) x86_64，进程 = so\*\* v2.18.1 amd64。

---

## 0. 最终结果

| 目标 | 状态 | 实现方式 |
|---|---|---|
| 解除 88 用户上限 | ✅ | 二进制 53 区域补丁 + LD_PRELOAD 适配器（hook panel_core_pull_users） |
| 任意 key 可用 | ✅ | 同上（key 校验失败不再影响数据面） |
| 跑起来一直不停（跨 600 s 检查点） | ✅ | /etc/hosts 4 行 + 本地 443 sink（让授权检查**快速失败**） |
| 无重启 / 无迁移 / 无会话中断 | ✅ | 单进程长跑；watchdog 只在连续 3 次真实握手失败时重启 |

产物 hash：

| 文件 | 字节 | SHA256 |
|---|---:|---|
| amd64/bin/soco-amd64（线上在用） | 85,851,856 | c463791ac4bf9ba82f28b8e87b148976f13397e1407ddab04d366579e4c80fed |
| amd64/bin/soco-amd64.original（原始） | 85,851,856 | c0e0f3965cf871b2aea60f8d01959aeb1848fba86f0cc0a5b928681eb861ffbc |
| amd64/bin/libsoco-amd64.so（适配器） | 26,216 | 2f60b5f881c9ae462a9de843eaea4471bd4a386a467c4e4c82042355c7998ab7 |
| arm64/bin/so**-arm64.original | 91,634,064 | 3c42ba62984c72edc263fb0cba5b0640aca867f9b675977a33c874a67501d641 |
| arm64/bin/so**-arm64.crack-so**10 | 91,634,064 | 3733296060ddb4047495ea0eb67e0449eee07e8ce375a7e969b28d36773f1d3a |

---

## 1. 起点：88 用户上限

- 原生 panel_core_pull_users（amd64 VA 0x35e8870，共享体 0x35a8b50）在 C 模块里把用户列表截断到 **88**；
- 适配器（amd64/src/adapter-amd64-clean.c）在构造器里 mprotect + memcpy 改写 pull_users 入口，跳到自己的 hook：
  - **先调用原生体**（原生会写 Shadowsocks 凭证表这一副作用，不能跳过，跳过后每条握手都会被丢）；
  - 再自己用 libcurl 拉面板全量用户，序列化成完整 JSON 返回；
- 二进制侧 53 区域补丁解除 Go 层的列表长度/identity/cleanup 限制（详见 amd64/manifest/patch-manifest-amd64.json）；
- 结果：97 / 89 / 6000 用户档均通过（旧验收见 amd64/evidence/verification/）。

---

## 2. 现象：进程启动 ~600 s 后数据面被关

**特征（全部实测，不是推测）**：

| 项目 | 实测 |
|---|---|
| 触发时间 | 进程启动后 **601–604 s**（多次独立 run 一致，窗口 (601, 604] s） |
| 表现 | socket 仍可 connect（LISTEN 一直在），但 **accept4 成功后 0.5 ms 内 close**，客户端 curl 退出码 **52**，服务端**没有任何连接级日志**（连 start handle client 都没有） |
| TCP 层 | 服务端侧 TIME-WAIT（服务端先发 FIN） |
| 已建立连接 | **不受影响**（5 条长连接跨过 600 s 仍活到实例关闭）；UDP 也不受影响 |
| 进程状态 | 进程活着、current user num: 97 照刷、面板 /status /config /user /push /alive 全 200 |
| 与探测的关系 | 无关：**零探测**（650 s 内 0 条连接）照样 t=663 s 第一次连就 52；3 s 一次连 137 次全通；31 个不同用户轮换也照样停 |
| 与刷新周期 | 无关：pull/push = 30 / 60 / 120 三档，停摆都在 ~614 s |
| 与 device_limit / speed_limit | 无关：分别设为 1000 / 0 照样停 |
| 与 so** key 错误 日志 | **同刻**：该日志出现在启动 +1 s 与 **+600.1 s** 各一次，第二次之后数据面关闭 |

**accept → close 的 strace 原文（停摆后第一次连接）**：

```
accept4(16, {...htons(46962)...}) = 18
epoll_ctl(5, EPOLL_CTL_ADD, 18, {events=EPOLLIN|EPOLLOUT|EPOLLRDHUP|EPOLLET,...}) = 0
epoll_ctl(5, EPOLL_CTL_DEL, 18, ...) = 0
close(18) = 0            <-- 0.5 ms 内，中间没有 read()
```
停摆前同一条路径是：accept4 → epoll_ctl ADD → read() → 日志 start handle client → SS 握手/中继。

**停摆瞬间的旁证**：/etc/ssl/certs/ca-certificates.crt + 151 个 /etc/ssl/certs/*.pem 被打开、/etc/pki/tls/certs 被 stat、DNS 解析 sksjd.vaxilu.com、connect(104.21.64.7:443)，随后写 so** key 错误。

---

## 3. ARM 破解版逆向（43 字节 / 11 条指令 / 10 段）

ARM 原版 vs crack-so**10 逐字节 diff **只有 43 字节**，解出来是三类补丁：

| # | 位置（ARM） | 原指令 | 改成 | 语义 |
|---|---|---|---|---|
| 1 | Po39saOz.W2IY7p @ 0x2b6fbdc（file 0x1b5fbdc） | str x30,[sp,#-0x50]! ; stur x29,... | mov w0,wzr ; ret | **整函数桩掉，恒返回 0** |
| 2–9 | a4HxrqKD9.(*T).xVhdeAZ_or × 8 个接收者类型 | eor x0,x3,#1 | mov x0,xzr | 恒返回 0 |
| 10 | qzQvcAaX_.(*EahsQPY).tjJW_G @ 0x322c544 | cbnz x1, <错误分支> | b .+4 | 恒走"x1 := -1"那一支 |

补充事实（对理解闸门很重要）：
- tjJW_G 是**控制流平坦化**的：每个状态块 mov/movk x7,#C ; ldr x8,[sp,#0x60] ; eor x5,x7,x8 ; 恢复22个寄存器 ; b dispatcher；
- 静态解出 KEY：key1 = 0x16376b45（223/223 setter 命中）、key2 = 0x4c8debb3（79/79 命中），因此状态图完全可还原；
- 被破解的那条 cbnz 语义是"按第 2 个结果字决定把 -1 写进哪个活跃变量"，**不是**打日志/返回 error；
- Po39saOz.JoskFx9Y1Mvz（调用点前一跳）↔ amd64 jBaQHzSm5z.JXpj8yqsa4 的孪生匹配是唯一解（唯一 callee = runtime.morestack_noctxt，in_degree 87/86，调用者集合 32 个双调用点结构同构）。

---

## 4. amd64 对齐尝试：全部失败（这是本轮最重要的"负结果"）

前提：候选基线 c463791a…（53 区域），适配器 2f60b5f8…，实验室方法 = mock 面板 97 用户 + 每 15–20 s 一次真实 SS2022 握手（sing-box → 本机 marker，断言 body），--duration 780。

| 变体 | 补丁内容 | 结果 |
|---|---|---|
| v1 | 跳过 JXpj8yqsa4 后的错误分支（file 0x248ba0d：75 79→eb 00） | 仍 **611.6 s** 停摆 |
| v2 | v1 + IJ2KM3 后错误分支（0x248ca56：75 7d→eb 00） | 仍停摆 |
| v3 | v2 + ZhfND6 的 bool 分支（0x248c1a8：74 7f→eb 00） | **启动即崩**（回滚） |
| v4 | 按 ARM"整函数桩"思路把 8 个核心方法入口改成 31 c0 c3 | 启动后 user not exist，**凭证表没建起来** → 该配对错误 |
| v5 | 把 10 分钟 getter jBaQHzSm5z.KFmapIeR8（VA 0x2cf0940，movabs rax,600e9; ret）改成 1 h | 仍 **611.6 s** 停摆（该 getter 调用者为 0，被内联） |
| v6 | c463 + 8 个核心点 83 f2 01→31 d2 90 + 分支 eb 00 | 仍 **612.4 s** 停摆 |
| v7 | **原版 c0e0** + 只打 ARM 那 10 段（含 gate 桩 0x1cf42aa→31 c0 c3 90…） | 97 用户能加载，但**一条流量都不通**（t=3.6 s 即 52） |
| v8 | 把 CifZGV.BuDnj0MC 里 movabs rdi,600e9（VA 0x2f17e85）改成 24 h | 仍 **613.2 s** 停摆 |

**8 点二分（另一条独立实验线）**：

| run | 补丁 | 最后 PASS | 首个 FAIL |
|---|---|---|---|
| first4 + 分支 | p1–p4 31 d2 90，分支 eb 00 | 600.8 | **615.8** |
| last4 + 分支 | p5–p8 31 d2 90，分支 eb 00 | 603.4 | **618.4** |
| all8-B + 分支 | 全 8 点 31 c0 90，分支 | 603.4 | **618.4** |
| all8-A 不动分支 | 全 8 点 31 d2 90 | 598.4 | **613.4** |
| 只改分支 | 75 79→eb 00 | 598.9 | **613.9** |
| 4×600e9→6000 s | 常量全改 | 598.9 | **613.9** |
| 基线 pull/push=30 / 120 | 不改 | 599.3 / 599.2 | **614.3** |

**为什么这 9 段注定无效（静态证据）**：在 c463 里这 8 处 xor edx,1 后面紧跟的消费者分支**已经是无条件 jmp**（test dl,dl ; eb <rel8>），dl 被丢弃 → 改它是改死值；全二进制 0f 9c c2 83 f2 01 恰好只有这 8 处，没有第 9 处漏网。分支点 jne 0x348ca88 的目标块与落空分支代码形状相同、只差混淆常量。

**其他被排除的假设**：/etc/hosts 黑洞只删日志不改行为（早期）；unshare -n（无外网）631 s 正常 → 说明该闸门需要"外部可达性"参与；conntrack/内存/句柄/GOMAXPROCS/信号/缓存目录/租约文件均无变化。

---

## 5. 定因：闸门由"授权检查的结局"驱动

三个对照实验（同一二进制、同一适配器、同一 fixtures）：

| 600 s 时授权检查的结局 | 首个失败时刻 | 结论 |
|---|---|---|
| 正常联网，拿到失败响应 | **~603 s**（多个 run：611.6 / 612.4 / 613.2 / 613.4 / 615.8 / 618.4） | 关闸 |
| 授权域名 → 198.51.100.1（TEST-NET 黑洞，连接挂住后超时） | **641.7 s** | 闸门推迟 = 600 + 约 40 s 超时 → **由检查结果触发** |
| 授权域名 → 127.0.0.1:443（本地 sink，TLS 握手被拒，快速失败） | **>1792 s 全程无失败** | **闸门不关** |

第三组数据（lab-fakelic-long）：54 → 90 次探测全通、30 个刷新周期、so** key 错误 **0 条**、跑到 t=1792.2 s 才正常结束。

sink 侧日志同时给出证据链：soco 确实来握手（SSL: SSLV3_ALERT_BAD_CERTIFICATE / UNEXPECTED_EOF_WHILE_READING 交替），也就是它走的是"快速失败"分支，而不是"关闸"分支。

**结论**：不需要改二进制就能拿到"一直跑"的效果；旁路点放在环境（/etc/hosts + 本地 443 sink）。

---

## 6. 最终部署形态

```
soco.service（单进程，LD_PRELOAD=libsoco.so）
   └ :49989 TCP+UDP   97 用户，SS2022，任意 key
soco-licence-sink.service（python，:443，自签证书，握手即拒）
/etc/hosts：sksjd.vaxilu.com / agdfgkdfg.singledance.xyz / boiudihsdfk.singledance.xyz / sxp7hu5t.cilema.xyz → 127.0.0.1
soco-watchdog.service：PROBE_EVERY=30, FAILS_TO_RESTART=3, PREEMPT_SECONDS=0（不再掐点重启）
```

- 部署/回滚脚本：amd64/deploy/final_switch_single2.sh（切单进程）、amd64/deploy/deploy_mesh_prod.sh（切 mesh）、amd64/deploy/restore_c463.sh（恢复二进制）
- 运维手册：amd64/deploy/RUNBOOK.md

---

## 7. 备选方案：mesh（中继 + 轮换），已实测可用

设计（amd64/src/soco_mesh_v3.py）：中继常驻 49989，每 480 s 起一个全新后端（内部端口 51000+，各自一个面板代理 52000+ 负责改写 server_port、非活跃后端吞掉 /push /alive），新连接切到最新后端，旧后端**空闲即回收**（不杀活跃会话）。

实测：生产上跑了 2 小时，**36 次轮换、46/46 探测全通、relay_no_backend = 0**（没有任何连接被拒）。当 sink/hosts 被破坏时，一条命令即可切回：

```bash
systemctl stop soco.service soco-watchdog.service && systemctl start soco-mesh.service
```

---

## 8. 还没解决的（下一步线索，按价值排序）

1. **纯二进制旁路**（做到 ARM 那种"单文件自带"）：
   - 已知闸门动作在 accept 分发路径上（CifZGV 包里 Accept 与 BuDnj0MC 附近）；
   - 二进制里有 GetInstanceExpired / SetInstanceExpired / (*Cwj006RO2nyz).Expire* 语义符号（无节头，但 Go 元数据可解析）；
   - 已被排除：8 个 xor edx,1、0x248ba0d 分支、4 处 600e9 常量、KFmapIeR8 getter、ARM 镜像 10 段；
   - 建议下一步：在 595–610 s 窗口用 gdb 断在 close 前的 Go 函数（需绕过无符号问题：用 Go pclntab 自己解析 PC→函数名），或对 Z9lU6H.*/CifZGV.* 做单点 A/B（每点 12 分钟）。
2. **24 小时长稳观察**：目前只压了 30 分钟（隔离台）+ 45 分钟（线上 soak），建议挂到 24 h。
3. **ARM 交叉验证**：本轮没有 ARM 机器；arm64/ 里的产物是历史破解件，未在真机复测。
4. **sink 的健壮性**：若 sink 挂掉而恰好撞上 600 s 检查，会退回停摆；可考虑让 sink 与 soco 同 unit（PartOf=）或加 BindsTo=。
---

## 8. mesh 备选方案的已知缺陷（实测，2026-11-22 06:05 UTC）

mesh-prod-probe-2 的一个 run 在 **t=465.8 s 出现 1 次 curl 52**：当时状态是
active=7, born_s_ago=627 —— 也就是**轮换没按时发生，活跃后端自己已经越过 600 s 闸门**，中继把新连接导给了一个已经关闸的后端。

原因：rotator 是"上一轮结束后再睡 480 s"，一旦某次轮换被延迟（新后端就绪慢、回收耗时、进程抖动），下一次就可能滑过 600 s。

**结论：mesh 只作为兜底，不做主方案。** 若要用，至少补两处：
1. 轮换计时改成**按后端出生时间**判断：if now - active.born > 540: rotate_now()；
2. 切换前必须确认新后端**真实可用**（跑一次 SS2022 握手），不能只判端口在听。

当前主方案（单进程 + hosts + sink）没有这个风险：它根本不依赖轮换。
