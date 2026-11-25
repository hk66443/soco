# ARM 0x221c544 → amd64 等价补丁：静态证据链

工作目录：`C:\Users\adminuser\Downloads\so**`
证据目录：`_deploy\implementation_amd64_verified\armmap\`
二进制未做任何修改（所有补丁均在内存副本上用 capstone 复核）。

| 项 | 值 |
|---|---|
| ARM 原版 | `_deploy\so**-v2.18.1-arm64.original` (91,634,064 B) |
| ARM 破解版 | `_deploy\so**-v2.18.1-arm64.crack-so**10` |
| amd64 原版 | `_deploy\amd64\so**\so**` SHA256 `c0e0f3965cf871b2aea60f8d01959aeb1848fba86f0cc0a5b928681eb861ffbc` |

---

## 0. 先把混淆机制解开（后面全部结论都建立在这个 KEY 之上）

`qzQvcAaX_.(*EahsQPY).tjJW_G`（VA 0x32281f0..0x322cf20，19760 B，4940 条指令）是
**双状态字 + 编码状态常量**的控制流平坦化函数：

```
每个状态块:  mov x7,#lo ; movk x7,#hi,lsl16 ; ldr x8,[sp,#0x60] ; eor x5,x7,x8 ; …恢复 22 个活跃寄存器… ; b 0x32282fc
派发器:      mov x7,#lo ; movk x7,#hi,lsl16 ; cmp x5,x7 ; b.eq/b.ne …
```

* `[sp,#0x60]` 与 `[sp,#0xe8]` 只在序言里各写一次（`0x322821c` / `0x3228228`，取自
  globals `0x4ea36e0` / `0x4ea36d8`），函数体内 **122 次读、0 次写** → 是常量 KEY。
* 静态求 KEY：对全部 `eor x5,x7,x8` 型 setter 常量与派发器比较常量做异或，
  得到唯一众数 **key1 = 0x16376b45，223/223 全中**（`arm_cff3.py`）；
  对 `x2` 型（次级状态字）做同样运算得 **key2 = 0x4c8debb3，79/79 全中**（`derive_key2.py`）。
* 于是「块常量 ^ key」= 派发器里真实比较的状态常量，状态图可以完全静态还原。
  （amd64 侧同一套机制：`mov rax,r10 ; xor rax,imm32`，r10 = `[rsp+0x110]`，派发器在 `0x348648f`。）

---

## 1. ARM "错误分支"目标 0x322c5bc 到底做什么

完整反汇编 80 条：`out_arm_err_branch.txt`。块 0x322c5bc..0x322c628：

```
0322c5bc  mov  x7,#0x99f3 ; movk x7,#0xf65,lsl16     ; x7 = 0x0f6599f3
0322c5c4  ldr  x8,[sp,#0x60]                          ; key1
0322c5c8  eor  x5,x7,x8                               ; 下一状态 = 0x1952f2b6
0322c5cc…0x322c628  ldr x0,[sp,#0x268] / ldr x1,[sp,#0x150] / … / ldr x17,[sp,#0x1f0]
                                                      ; 恢复 22 个活跃寄存器（x0-x6,x9-x11,x13-x17,x19-x26,x30,w12）
0322c62c  b    #0x32282fc                             ; 回派发器
```

**结论：这一块里没有任何 `bl` / `blr` / `ret` / 内存写 / 日志调用。它不是"打日志"、不是"返回 error"，
它只是一条"状态边"：`state := 0x1952f2b6; goto dispatcher`。**

顺着状态图往下（派发器表见 `out_cff2.txt` / `out_cff_table.json`）：

| 步 | 状态常量（派发器比较值） | 到达代码 | 动作 |
|---|---|---|---|
| 1 | 0x1952f2b6 | `cmp@0x32284c4 b.ne`，取 0x32284cc | **次级状态 x2 := 0x02707a7e ^ key2 = 0x4efd91cd**；主状态 x5 := 0x39914f2a ^ key1 = 0x2fa6246f |
| 2 | 0x2fa6246f | 0x322b5c4 | 只改 x5 := 0x767af445 ^ key1 = 0x604d9f00（机器入口/出口态） |
| 3 | 0x604d9f00 | 0x32282fc 落入 0x322830c | 全函数唯一一处 `cmp x2,#0x7cb163e6`；本路径不等 → 状态 0x6f267d86^key1 = 0x791116c3 |
| 4 | 后续守卫态 0x4e04f9fb（`cmp@0x3229edc`） | 0x3229ee4 | `cmp x2,#0x4efd91cd` **相等** → 状态 0x394e27ac^key1 = 0x2f794ce9 |
| 5 | 0x2f794ce9 | 0x322b0fc | `mov x7,#-1 ; str x7,[sp,#0xf8]` ← **给活跃变量 [sp,#0xf8] 写 -1**，然后继续派发 |

对照**不跳转（x1==0）那条路**：

| 步 | 状态常量 | 动作 |
|---|---|---|
| 1 | 0x0b381f9e | 0x3228498：x2 := 0x77dd3818 ^ key2 = 0x3b50d3ab；x5 := 0x61cc8317 ^ key1 = 0x77fbe852 |
| 2 | 0x604d9f00 | 同上，落到 0x6f267d86^key1 = 0x791116c3 |
| 3 | 守卫态 0x6644e6c6（`cmp@0x32298c0`） | 0x32298c8 `cmp x2,#0x3b50d3ab` 相等 → 状态 0x09ffe823 |
| 4 | 0x09ffe823 | 0x3229ebc：**`mov x1,#-1`** ← 把 -1 写进另一个活跃变量 x1，然后继续派发 |

所以这条 `cbnz x1, 0x322c5bc` 的语义是：**按"被调函数返回的第 2 个结果字"选择给哪个活跃变量写 `-1`**
（错误/非零 → 写 `[sp,#0xf8]`；零 → 写 `x1`）。它既不写日志也不直接 `return`；
`tjJW_G` 全函数只有 **一个** `ret`（0x322c0d4，纯收尾 `ldp x29,x30 / add sp / ret`，见 `out_rets_tjJWG.txt`）。
破解版把它改成 `b .+4`，等于**恒定走"x1 := -1"这一支**。

---

## 2. `Po39saOz.JoskFx9Y1Mvz` 在 amd64 的真身（唯一性证据）

三类特征，全部 arch-invariant：

### 2.1 出边 / 内部 callee 多重集合 — 决定性

```
ARM Po39saOz.JoskFx9Y1Mvz 0x2b6f660  1392B 348insn args=0  out_degree=1  callees={runtime.morestack_noctxt:1}
AMD jBaQHzSm5z.JXpj8yqsa4 0x2cf4c20  1664B 358insn args=0  out_degree=1  callees={runtime.morestack_noctxt:1}
```

全库扫描（`uniq_scan.py`，两侧各扫全部 45k 函数）：

```
[arm] 唯一 callee=runtime.morestack_noctxt 的函数 1607 个，其中 in_degree∈[80,95] 只有 1 个：
      *** in_degree=87  size=1392  Po39saOz.JoskFx9Y1Mvz
[amd] 唯一 callee=runtime.morestack_noctxt 的函数 1621 个，其中 in_degree∈[80,95] 只有 1 个：
      *** in_degree=86  size=1664  jBaQHzSm5z.JXpj8yqsa4
```

### 2.2 调用者集合（数量 + 每个调用者内的调用点数 + 位置比例）

```
ARM 87 个调用点 / 55 个调用者，调用点数直方图 {1:23, 2:32}
AMD 86 个调用点 / 54 个调用者，调用点数直方图 {1:22, 2:32}
```

* 32 个"双调用点闭包"在两侧**结构完全同构**：ARM 是 8 个接收者类型 ×
  {`jvauV_P`,`_jIcEtfai4`} × {`func1.func1`,`func2.func1`}；
  AMD 是同样的 8 个类型 × {`cK2x0X`,`eLemGS4PoODM`} × {`func1.func1`,`func2.func1`}。
* 唯一差异是 AMD 少 1 个"单调用点"调用者（86 vs 87）—— 对应 1 处被内联的调用点。
* 完整两侧调用表：`out_caller_table.txt`。

### 2.3 同文件兄弟函数交叉验证（最硬的一刀）

`JoskFx9Y1Mvz` 在同一源文件 `Po39saOz/oVgBb_NkPcdl.go` 的兄弟 `W2IY7p` 与 amd64
`jBaQHzSm5z/XMiaQunNxtPH.go` 的兄弟 `PljQYvo5Ck` **callee 多重集合逐项相同、in-degree 完全相同**：

```
ARM Po39saOz.W2IY7p  752B  in_degree=59 unique=51 out=5
    {time.GHvczVng:1, internal/sync.(*Mutex).lockSlow:1, internal/sync.(*Mutex).unlockSlow:1,
     Po39saOz.JoskFx9Y1Mvz:1, runtime.morestack_noctxt:1}
AMD jBaQHzSm5z.PljQYvo5Ck 608B in_degree=59 unique=51 out=5
    {time.GawPQdW:1, internal/sync.(*Mutex).lockSlow:1, internal/sync.(*Mutex).unlockSlow:1,
     jBaQHzSm5z.JXpj8yqsa4:1, runtime.morestack_noctxt:1}
```

即：兄弟函数的"调用了谁"一模一样（含它所调的那个叶函数），两侧 in-degree 同为 59/51。
兄弟对上了，叶函数自然只能对上。

**结论：`Po39saOz.JoskFx9Y1Mvz` (0x2b6f660) ↔ `jBaQHzSm5z.JXpj8yqsa4` (0x2cf4c20)，唯一。**

---

## 3. 精确补丁

`tjJW_G` 里对 `JoskFx9Y1Mvz` 的调用**全函数只有一次**（0x322c540，ratio 0.8721）；
`azvAthfr02` 里对 `JXpj8yqsa4` 的调用**也全函数只有一次**（0x348ca05，ratio 0.8076）。

```
ARM 原版                                   amd64 原版
0322c540  bl  JoskFx9Y1Mvz                 0348ca05  call JXpj8yqsa4
0322c544  cbnz x1, 0x322c5bc  (错误态)      0348ca0a  test rbx, rbx
0322c548  <落到 0x1d0f74db 状态块>          0348ca0d  jne  0x348ca88   (错误态块)
                                           0348ca0f  <落到 rbx==0 的状态块>
```

* **VA 0x348ca0d / file offset 0x248ba0d**
* before：`75 79`（`jne 0x348ca88`）
* after ：`eb 00`（`jmp 0x348ca0f`，= 等长 2 字节、无条件落到下一条）
* 语义：和 ARM 破解版 `c1 03 00 b5` → `01 00 00 14`（`b .+4`）完全等价 ——
  恒不走"错误/非零结果"那条状态链，恒执行 `rbx==0` 那支。

**为什么是这条、不是另外三条**（四条调用点的 profile 对照，`out_four_sites.txt`）：

| ARM 站点 | ARM callee | 特征 | AMD 站点 | AMD callee | 特征 |
|---|---|---|---|---|---|
| 0x322c540 | JoskFx9Y1Mvz | **in87 / out1 {morestack}** | 0x348ca05 | JXpj8yqsa4 | **in86 / out1 {morestack}** |
| 0x322b5d4 | VhBf3YD5Mw | in1 / out2 {TGpEFtCy,morestack} | 0x348aba0 | DnVLpQb8d2I4 | in1 / out2 {Gtv1ywMtccF,morestack} |
| 0x322b8a4 | XtgnZa9 | in1 / out2 {TGpEFtCy,morestack} | 0x348d1a1 | ZhfND6 | in1 / out2 {Gtv1ywMtccF,morestack} |
| 0x322c160 | LGxBMDeFEi | in2 / out9（novel 多重集合） | 0x348da4e | IJ2KM3 | in1 / out9（同一多重集合） |

`tjJW_G` 内共 4 处对同包函数的调用，`azvAthfr02` 内也恰好 4 处，按 profile 一一对上：

1. `DnVLpQb8d2I4` 对应的是 ARM **0x322b5d4 的 `VhBf3YD5Mw`**（那处 ARM 是
   `bl VhBf3YD5Mw ; eor x12,x0,#1`，amd64 是 `call DnVLpQb8d2I4 ; xor eax,1`）——
   它和 0x322c544 是**同一函数里的另一处**，与 `cbnz x1` 无关；且 in1/out2 ≠ in87/out1。
2. `ZhfND6`：站点后是 `test al,al ; je`，测的是**第 1 个结果字的低字节**（bool），
   ARM 对应 `tbz/cbz w0`，不是 `cbnz x1`；profile in1/out2 也对不上。
3. `IJ2KM3`：out-degree 9（`concatstring2 / newobject / growslice / gcWriteBarrier*`），
   ARM 真身 out-degree 1 且无任何直接调用 —— 排除。它对应 ARM 0x322c160 的 `LGxBMDeFEi`。
4. `JXpj8yqsa4`：唯一满足 in86/out1{morestack} 的函数，且是**全二进制唯一**（2.1 的扫描）。

ABI 层面也自洽：Go 结果寄存器按字段顺序分配，`error`/接口占两个槽，
ARM `X1` = 第 2 个结果字 ↔ amd64 `RBX` = 第 2 个结果字；
`cbnz x1`（非零跳）↔ `test rbx,rbx ; jne`。三条候选中只有这一处两者同时成立。

---

## 4. capstone 独立复核（`verify_patch.py`，全内存操作）

```
# before : 75 79        # after : eb 00
0348ca00  e98a9affff           jmp  0x348648f
0348ca05  e8168286ff           call 0x2cf4c20
0348ca0a  4885db               test rbx, rbx
0348ca0d  7579                 jne  0x348ca88   <== BEFORE
0348ca0d  eb00                 jmp  0x348ca0f   <== AFTER
0348ca0f  4c8b942410010000     mov  r10, qword ptr [rsp + 0x110]

# boundary check: instruction start addresses identical? True
   [3] 0348ca0f  before=4c8b942410010000 mov r10,[rsp+0x110] | after=同上  (未破坏)
# jmp target = 0x348ca0f ; next instruction = 0x348ca0f  -> falls through unconditionally: True
# bytes changed in memory image: 2 at file offsets ['0x248ba0d', '0x248ba0e']
# every changed offset is inside the patch span: True
```

---

## 5. 附加发现（重要）：ARM 破解版到底改了哪 10 处

`arm_diff.py` 全量 diff：**43 字节**；按 4 字节指令对齐归并后是 **10 段**
（`W2IY7p` 那段一次改了两条指令，所以按"改动条数"数确实是 11 条）。逐段解码：

| # | VA | 函数 | 原文 | 破解 | 语义 |
|---|---|---|---|---|---|
| 1 | 0x2b6fbdc | `Po39saOz.W2IY7p` (+0xc) | `str x30,[sp,#-0x50]! ; stur x29,[sp,#-8]` | `mov w0,wzr ; ret` | **整函数桩掉，恒返回 0** |
| 2-9 | 0x30627b0 / 0x3080af0 / 0x3086fa0 / 0x3094d10 / 0x30a2f08 / 0x30b3120 / 0x30ba3f0 / 0x30c3bb0 | `a4HxrqKD9.(*T).xVhdeAZ_or` (8 个接收者类型) | `eor x0,x3,#1`（其中 1 处 `eor x3,x3,#1`） | `mov x0,xzr`（对应 `mov x3,xzr`） | **8 个方法恒返回 0/false** |
| 10 | 0x322c544 | `qzQvcAaX_.(*EahsQPY).tjJW_G` (+0x4354) | `cbnz x1,#0x322c5bc` | `b #0x322c548` | 本报告第 1/3 节 |

也就是说：**只打第 10 处不足以复现破解**——前 9 处（尤其第 1 处 `W2IY7p` 整体桩成 return 0）
才是主逻辑旁路的正面打击。这解释了上一轮"只改 0x348ca0d 仍然 10 分钟停摆"的现象。

amd64 对应目标（同样是 profile/名族匹配出来的，可直接据此续做）：

| ARM | amd64 对应 | 依据 |
|---|---|---|
| `Po39saOz.W2IY7p` (752B, in59/out5) | **`jBaQHzSm5z.PljQYvo5Ck`** 0x2cf52a0 (608B, in59/out5, callee 多重集合逐项相同) | 第 2.3 节 |
| `a4HxrqKD9.(*T).xVhdeAZ_or` ×8 | **`Z9lU6H.(*T).q8Qx_4` ×8**，每处含 `83 f2 01`（`xor edx,1`）：0x32c7e3c / 0x32daf7d / 0x32eb701 / 0x32fd2bd / 0x329bd5d / 0x32bfcfd / 0x330519d / 0x330fd3a；接收者类型恰好是同 8 个（BJAfPdiL/HXK0JZEAK2/OJTQI2Ac1r/KaOVrnMV7E3H/Du63sFoU/TrxgWsds/NStQoY2/R91N1E7Dcg），与 ARM 8 个类型一一对应 | `find_xor1.py` + 调用者闭包族结构 |
| `qzQvcAaX_.(*EahsQPY).tjJW_G` 0x322c544 | `QIL5jNyrmc.(*ZNzLWDeTnfS6).azvAthfr02` file 0x248ba0d `75 79` → `eb 00` | 本报告第 3 节 |

`W2IY7p` 桩掉的具体落点（两侧都保留 Go 的栈检查，只把建帧改成"返回 0"）：

```
ARM  0x2b6fbd0  ldr x16,[x28,#0x10] / cmp sp,x16 / b.ls morestack   ← 保留
     0x2b6fbdc  fe 0f 1b f8  fd 83 1f f8   (str x30,[sp,#-0x50]! ; stur x29,[sp,#-8])
              → e0 03 1f 2a  c0 03 5f d6   (mov w0,wzr ; ret)      ← 破解版

AMD  0x2cf52a0  49 3b 66 10              cmp rsp,[r14+0x10]        ← 保留
     0x2cf52a4  0f 86 35 02 00 00        jbe morestack             ← 保留
     0x2cf52aa  55 48 89 e5 48 83 ec 38  (push rbp ; mov rbp,rsp ; sub rsp,0x38)  ← 建议改成
              → 31 c0 c3 90 90 90 90   (xor eax,eax ; ret ; nop×4)   等长 7 字节
     对应 file offset 0x1cf42aa（VA 0x2cf52aa）
```

---

## 6. 证据文件清单（全部在 `_deploy\implementation_amd64_verified\armmap\`）

| 文件 | 内容 |
|---|---|
| `out_arm_err_branch.txt` | 0x322c5bc 起 80 条指令反汇编（§1） |
| `out_arm_patchsite.txt` | 补丁点前后 ARM 指令（含两条后继状态块） |
| `out_arm_dispatcher.txt` | 派发器入口 0x32281f0/0x32282fc 反汇编 + 序言写 KEY |
| `out_cff2.txt` / `out_cff_table.json` | 全函数 316 条派发比较与 304 个 setter 的对照表 |
| `out_state_resolve.txt` | 两个分支状态 → 处理器块（0x32284cc / 0x3228498） |
| `out_x2_discrim.txt` | x2 = 0x4efd91cd / 0x3b50d3ab 两处判别点 |
| `out_rets_tjJWG.txt` | `tjJW_G` 唯一 ret（0x322c0d4） |
| `out_arm_target_full.txt` | `JoskFx9Y1Mvz` 全 348 条指令 |
| `out_caller_table.txt` | 87 vs 86 调用点全表（两侧） |
| `out_twin_match.txt` / `out_uniq.txt` | 唯一性扫描与特征对照 |
| `out_four_sites.txt` | `tjJW_G` 与 `azvAthfr02` 四个同包调用点的一一对应 |
| `out_arm_diff_all.txt` | ARM 原版 vs 破解版 43 字节 /10 段全解码 |
| `out_verify_patch.txt` | capstone 补丁前后复核输出 |
| `*.py` | 全部可复跑脚本（`elfmap.py` / `arm_cff3.py` / `derive_key2.py` / `profile_fn.py` / `twin_match.py` / `uniq_scan.py` / `callgraph.py` / `verify_patch.py` / `arm_diff.py` …） |