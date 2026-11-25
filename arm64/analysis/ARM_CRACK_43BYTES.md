# ARM 破解版逐处分析（43 字节 / 11 条指令 / 10 段）

对文件：

| 文件 | 字节 | SHA256 |
|---|---:|---|
| `../bin/so**-arm64.original` | 91,634,064 | `3c42ba62984c72edc263fb0cba5b0640aca867f9b675977a33c874a67501d641` |
| `../bin/so**-arm64.crack-so**10` | 91,634,064 | `3733296060ddb4047495ea0eb67e0449eee07e8ce375a7e969b28d36773f1d3a` |

全量 diff：**实际不同字节 43 个**，解码为 **11 条指令 / 10 段**（个别字节恰好相同，所以按指令统计比按字节多）。

---

## 1. 段 1：整函数桩掉（1 条指令对）

| 项 | 值 |
|---|---|
| 函数 | `Po39saOz.W2IY7p`（args=0，752 B，源码 `Po39saOz/oVgBb_NkPcdl.go:6`） |
| VA / file | `0x2b6fbd0` / `0x1b5fbdc` |
| 原 | `str x30,[sp,#-0x50]! ; stur x29,[sp,#-8]`（函数序言） |
| 改 | `mov w0,wzr ; ret` |

语义：**整个函数恒返回 0**。它是"共享闸门"——被大量调用点用来决定是否放行。

---

## 2. 段 2–9：8 个核心接收者方法恒返回 0

同一条指令在 8 个不同类型的同名方法里各改一次：

| # | 函数（`a4HxrqKD9.(*T).xVhdeAZ_or`） | VA |
|---|---|---:|
| 1 | `(*FzQJMmRUMcw)` | `0x3062720` |
| 2 | `(*TJRO2pE)` | `0x3080a60` |
| 3 | `(*JrVj9M0FiT)` | `0x3086f10` |
| 4 | `(*Ke3Pasll)` | `0x3094c80` |
| 5 | `(*DJz1VUtC)` | `0x30a2de0` |
| 6 | `(*LoP8RKDPIfR)` | `0x30b3090` |
| 7 | `(*JfPfDr1BO)` | `0x30ba360` |
| 8 | `(*N7YBpgAe4)` | `0x30c3b20` |

| 原指令 | 字节（ARM64 LE） | 改后 | 字节 |
|---|---|---|---|
| `eor x0, x3, #1` | `60 00 40 d2` | `mov x0, xzr` | `e0 03 1f aa` |

语义：原本是"返回 `x3 ^ 1`"，改成**恒返回 0**（8 × 4 = 32 字节）。

---

## 3. 段 10：授权校验里的分支被强行跳过

| 项 | 值 |
|---|---|
| 函数 | `qzQvcAaX_.(*EahsQPY).tjJW_G`（args=8，19,760 B，VA `0x32281f0..0x322cf20`） |
| VA / file | `0x322c544` / `0x221c544` |
| 原 | `cbnz x1, #0x322c5bc`（`c1 03 00 b5`）→ 结果非零就去错误分支 |
| 改 | `b #0x322c548`（`01 00 00 14`）→ **无条件落到下一条** |

上下文（ARM 反汇编）：

```
322c540  bl #0x2b6f660        ; 调用 Po39saOz.JoskFx9Y1Mvz（授权校验）
322c544  cbnz x1, #0x322c5bc  ; ← 被改成 b .+4
322c548  mov x7, #0x74db      ; 正常路径继续
...
322c5bc  ...                  ; 错误路径（同形状状态块，只是状态常量不同）
```

语义：不看校验结果，直接走"正常"那一支。

---

## 4. 这个函数是控制流平坦化的（还原方法）

`tjJW_G` 每个状态块长这样：

```
mov  x7, #<lo>
movk x7, #<hi>, lsl #16
ldr  x8, [sp, #0x60]      ; KEY（只在序言写一次，取自 global 0x4ea36e0）
eor  x5, x7, x8           ; 状态常量 = 立即数 ^ KEY
<恢复 22 个活跃寄存器>
b    0x32282fc            ; dispatcher
```

静态解出：

| KEY | 值 | 命中率 |
|---|---|---|
| key1（`[sp,#0x60]`，global `0x4ea36e0`） | `0x16376b45` | 223 / 223 setter 全部吻合 |
| key2（`[sp,#0xe8]`，global `0x4ea36d8`） | `0x4c8debb3` | 79 / 79 setter 全部吻合 |

有了 KEY 就能把状态图完全还原，从而确认"被跳过的错误分支"只是另一条状态边，**不写日志、不返回 error、不释放资源**——它决定的是把 `-1` 写进哪个活跃变量（`[sp,#0xf8]` vs `x1`）。

---

## 5. 与 amd64 的对应关系（供交叉参考）

| ARM | amd64 对应 | 能否照搬 |
|---|---|---|
| `Po39saOz.W2IY7p`（桩） | `jBaQHzSm5z.PljQYvo5Ck`（file `0x1cf42aa` → `31 c0 c3 90 90 90 90`） | 部分（已在 c463 里打过类似桩） |
| `Po39saOz.JoskFx9Y1Mvz`（被调） | `jBaQHzSm5z.JXpj8yqsa4`（唯一 callee=`morestack`，in_degree 86/87，调用者集合同构） | 是（孪生匹配唯一解） |
| 8 × `xVhdeAZ_or` | `Z9lU6H.(*T).q8Qx_4` 8 处 `83 f2 01`（`xor edx,1`） | **不能**：amd64 里它们后面紧跟 `test dl,dl ; jmp`（消费者已无条件跳转 = 死值） |
| `tjJW_G` 的 `cbnz` | `QIL5jNyrmc.(*ZNzLWDeTnfS6).azvAthfr02` 内 `0x348ca0d`（file `0x248ba0d`，`75 79` → `eb 00`） | **不能**：单独打仍 613.9 s 停摆（另有机制） |

amd64 上这 9 段全部实测无效（8 个二分 run + v1–v8 变体，见 [../../BYPASS.md](../../BYPASS.md) §4）。

---

## 6. 复现命令（本机，需 pyelftools + capstone）

```python
# 逐字节 diff，打印所有差异区间
from pathlib import Path
a = Path('so**-arm64.original').read_bytes()
b = Path('so**-arm64.crack-so**10').read_bytes()
assert len(a) == len(b)
runs, i, n = [], 0, len(a)
while i < n:
    if a[i] != b[i]:
        j = i
        while j < n and a[j] != b[j]:
            j += 1
        runs.append((i, a[i:j].hex(), b[i:j].hex()))
        i = j
    else:
        i += 1
for off, before, after in runs:
    print(hex(off), before, '->', after)
```

预期得到 11 段（上面表格里 file offset = VA − 段偏移，ARM 该段 delta 可通过 `readelf -l` 求出）。