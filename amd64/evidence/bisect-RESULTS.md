# 补丁二分实验：8 核心点 + 0x248ba0d 分支能否跨过 ~600 s 闸门

执行时间：2026-11-22 04:22–05:52 UTC　　靶机：<AMD_IP>（Debian 13 / amd64）
基线二进制：`candidates/verified53-20261121-minimal-v1/soco` = `c463791ac4bf9ba8…`（= 线上二进制）
适配器：`adapter-clean-build-20261121-v1/libsoco-amd64.so`（`2f60b5f8…`）
Lab：`/root/soco-verified-tests/interval_lab_v4.py --duration 780 --probe-every 15 --fixtures lab-fixtures`
硬约束全部遵守：未触碰 `/usr/local/soco/*`、未动 soco.service / /etc/hosts / resolv.conf / systemd unit、未 apt；只在 `/root/soco-verified-tests` 下写入；隔离实例端口仅 198xx（mock 199xx / socks 200xx）；同时最多 2 个实例。

---

## 1. 结果表

| run-id | 补丁组合 | pull/push | 最后 PASS 的 t | 首个 FAIL 的 t | curl | t>620 是否可用 |
|---|---|---|---|---|---|---|
| `bisect-r1a-first4A-1` | p1–p4 → `31 d2 90` + 分支 `eb 00` | 60/60 | 600.8 | **615.8** | 52 | **否** |
| `bisect-r1b-last4A-1` | p5–p8 → `31 d2 90` + 分支 `eb 00` | 60/60 | 603.4 | **618.4** | 52 | **否** |
| `bisect-r2c-all8B-1` | 全 8 点 → `31 c0 90` + 分支 | 60/60 | 603.4 | **618.4** | 52 | **否** |
| `bisect-r2e-all8A-nobr-1` | 全 8 点 → `31 d2 90`，**不动**分支 | 60/60 | 598.4 | **613.4** | 52 | **否** |
| `bisect2-r3-bronly-1` | **只**改分支 `75 79`→`eb 00` | 60/60 | 598.9 | **613.9** | 56 | **否** |
| `bisect2-r3-const6000-1` | 600 s 常量 ×4 → 6000 s（8 点不动） | 60/60 | 598.9 | **613.9** | 52 | **否** |
| `bisect2-r4-base-ivl30-1` | 原始 c463，面板 push/pull=30 | 30/30 | 599.3 | **614.3** | 52 | **否** |
| `bisect2-r4-base-ivl120-1` | 原始 c463，面板 push/pull=120 | 120/120 | 599.2 | **614.3** | 52 | **否** |

补做说明：`bisect-r2d-bronly-1` / `bisect-r3-const6000-1` 两个实例在 05:08Z 被主控的全机清理误杀（数据停在 t≈269，curl 97 = SOCKS 客户端已消失），已作废，按主控要求用 `bisect2-*` 前缀重跑（上表两行 `bisect2-r3-*`）。

**闸门窗口**：8 个 run 的 (最后 PASS, 首次 FAIL) 全部落在 `(598.4 – 603.4, 613.4 – 618.4]`，即墙钟 ≈600–614 s，**与补丁组合、与面板 pull/push 间隔、与 600 s 常量改写均无关**。

---

## 2. 结论

1. **8 个 `83 f2 01` 点没有一个"必须改"**，因为它们在 c463 里已经是**死值**：
   每个点后面紧跟的消费者分支在 c463 中已是**无条件跳转**，`test dl,dl` 的结果被丢弃，改 `xor edx,1` 的任何字节都不可能改变行为。逐点字节（file offset = VA − 0x1001000）：

   | 点 | VA | c463 字节（site…） | 消费者 |
   |---|---|---|---|
   | p1 | 0x32c7e3c | `83 f2 01 90 84 d2 eb 15` | `test dl,dl` → **jmp** |
   | p2 | 0x32daf7d | `83 f2 01 84 d2 eb 15` | **jmp** |
   | p3 | 0x32eb701 | `83 f2 01 84 d2 eb 12` | **jmp** |
   | p4 | 0x32fd2bd | `83 f2 01 84 d2 eb 15` | **jmp** |
   | p5 | 0x329bd5d | `83 f2 01 84 d2 eb 15` | **jmp** |
   | p6 | 0x32bfcfd | `83 f2 01 84 d2 eb 15` | **jmp** |
   | p7 | 0x330519d | `83 f2 01 84 d2 eb 15` | **jmp** |
   | p8 | 0x330fd3a | `83 f2 01 0f 1f 00 84 d2 eb 18` | **jmp** |

   全二进制 `setl dl; xor edx,1`（`0f 9c c2 83 f2 01`）**恰好只有这 8 处**，没有第 9 处漏网。
   因此"正确字节"这个问题对结果无意义：`31 d2 90`（xor edx,edx;nop）与 `31 c0 90`（xor eax,eax;nop）**都实测无效**——前者让 dl=0、后者让 dl 保持 `(now<deadline)`，两者都在下一条 `test dl,dl; jmp` 处被丢弃。

2. **0x248ba0d 的分支补丁也不是闸门**：该处是真实指令 `jne 0x348ca88`（VA 0x348ca0d，`75 79`），目标块与落空分支代码形状相同、只差一个混淆常量（`xor rax,0x1296ec5d` vs `xor rax,0x23bd9f3`）；把它改成 `eb 00`（落空）**单独跑**仍然在 t=613.9 停摆。

3. **能否跨过 600 s：不能。** 8 点（全部子集 / 两种字节）+ 分支，全部在 ~614 s 停摆。

4. **明确判定：8 点 + 分支（共 9 段）都不是闸门所在。**

---

## 3. 实验里观察到的旁证（指向真闸门）

1. **每个 run 的日志里，"so\*\* key 错误"恰好两次，且严格相差 600.0 s**：
   - `bisect-r1b`：`04:34:32` → `04:44:32`
   - `bisect2-r3-const6000`：`05:18:05` → `05:28:05`
   - 第一次出现在启动 +1 s（用户加载之前，无害）；第二次落在"最后 PASS / 首次 FAIL"窗口内，{紧跟其后}所有新连接被 accept 后立即关闭。
2. **第二次 key 错误之后没有任何 `add user`**（97 条 `add user` 全在启动阶段一次性输出，之后 0 条）→ 不是"用户表刷新"导致的，而是**服务端自己的 key 校验开始失败**（已建立连接不受影响，会话密钥已协商）。
3. **改写 600 s 常量无效**：`0x8bb2c97000`（= 600×10⁹ ns，全二进制仅 4 个 imm64 使用点：VA `0x29c9861` 写入 `mallocgc(0x30)+0x28`、`0x2cefb6d` 的 `cmovle` 默认值、`0x2cf0940` 的独立 getter、`0x2f17e85` 的 `runtime.sec` 定时形参）全部改成 6000 s 后，key 错误**仍然严格 +600.0 s** → 该常量不是这个 tick 的来源。
4. **与面板间隔无关**：push/pull = 30 / 60 / 120 三档，闸门都落在 599.3→614.3（check 循环本身确实随间隔变化：`next check` 等待 30 s / 60 s / 120 s 都有日志为证），所以 tick 不是"N 次 check/submit 累加"，而是**固定的墙钟 ~600 s 定时器**。
5. **不是适配器/shime 造成的**：`libsoco-amd64.so` 里没有任何 600 / 600e9 / 60e9 常量（`u32=0, u64=0`），字符串也只有 `[soco] v0.1.0 ready (… cap bypass)` → 闸门在 soco 二进制内部。
6. 三条前人结论与本次一致：c463 + 全 8 点(A) + 分支 → 612 s 停摆；ARM 侧 `eor x0,x3,#1 → mov x0,xzr` 的 8 段语义在这条路径上**已被 c463 的"消费者 eb 桩"覆盖**，所以再补 8 段是重复且无效的。
7. `bisect2-r3-bronly-1` 首次失败是 `curl 56`（received 数据中断）而不是 52，说明分支补丁让"accept 后立即关闭"的时序略变，但闸门时刻不变——进一步说明它只影响收尾路径，不决定闸门。

---

## 4. 证据文件

本地 `_deploy/implementation_amd64_verified/bisect/`：
- 构建器：`build.py`（c463 + 点/分支补丁）、`build_const.py`（600 s 常量改写）、`disasm_sites.py` / `enum_sites.py` / `elfmap.py` / `site_bytes.py` / `br_ctx.py`（静态核验）
- 二进制：`r1a-first4A-1.soco`、`r1b-last4A-1.soco`、`r2c-all8B-1.soco`、`r2d-bronly-1.soco`、`r2e-all8A-nobr-1.soco`、`r3-const6000-1.soco`、`r4-const60-1.soco`（最后的 60 s 常量版**已构建上传但未跑**）
- 每 run 的补丁清单：`<run>.patch.json`（逐点 VA/file offset/原字节/新字节/sha256）
- 远端结果回传：`remote/<run>.result.json`、`remote/<run>.out`（全部 8 个有效 run）
- 单点变体（更小的子集，共 24 个）：`s-p{1..8}-{A,B}-br.soco`、`s-p{1..8}-A-nobr.soco` —— 由于"全 8 点"这一超集已失败且 8 处静态上都是死值，**未再消耗实例去跑单点**。

远端（`/root/soco-verified-tests/`）：
- run 目录：`bisect-r1a-first4A-1/`、`bisect-r1b-last4A-1/`、`bisect-r2c-all8B-1/`、`bisect-r2d-bronly-1/`(作废)、`bisect-r2e-all8A-nobr-1/`、`bisect-r3-const6000-1/`(作废)、`bisect2-r3-bronly-1/`、`bisect2-r3-const6000-1/`、`bisect2-r4-base-ivl30-1/`、`bisect2-r4-base-ivl120-1/`（各含 `result.json` / `server.log` / `test.conf` / `client.json`）
- 候选二进制：`candidates/bisect-*/soco`

---

## 5. 清理

- 05:51:52Z 复核：`/proc/*/exe` 中以 `/root/soco-verified-tests/` 开头的进程 **0 个**；198xx / 199xx / 200xx 端口 **无任何监听**。
- 所有实例均由 lab 脚本 `finally` 或 `terminate` 自行退出（含被 05:08Z 误杀后重跑的两轮）。
- 未改动任何生产路径；生产 `soco-mesh` 相关端口（49989/51000/52000）全程未触碰。