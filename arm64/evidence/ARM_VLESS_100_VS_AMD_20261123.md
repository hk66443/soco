# amd64 vless 100 用户验证 + 补丁语义对照（2026-11-23）

> 结论：**amd64 的 vless 在 100 个用户下 5/5 全部 200**，arm64 同样条件 0/5。
> 所以「100 人不可用」**与协议无关、与 so\*\* 版本无关**，纯粹是 **arm64 缺补丁**。

## 1. 验证（amd，vless）

在 amd（AMD_IP，soco = c463791a… + libsoco-amd64.so）上用 mock 面板造了一个
**VLESS + REALITY** 节点（端口 19590，固定 X25519 私钥 = bytes(1..32)，短 ID a1b2c3d4e5f6，
SNI www.apple.com），客户端 sing-box 经 SSH 隧道做真实握手：

| 用户数 | add user | current user num | 客户端 |
|---|---|---|---|
| **100** | **100** | **100** | **200 × 5/5**（出口 AMD_IP, US） |

对照 arm64（vless，同方法）：

| 用户数 | add user | 客户端 |
|---|---|---|
| 88 | 88 | 200 × 6/6 |
| 100 | 100 | **000 × 5/5**，access address 后直接 handle vless end，**连 domain resolved 都没有** |

**生产未受影响**：amd soco PID 186535 / NRestarts=0 / 49989 正常；
arm soco 磁盘 37332960…、PID 2405082 / NRestarts=0 / 49999 正常。

## 2. amd 的 26 处 api-user-preserve 语义（关键）

manifest 里这组的 hypothesis 分两类：

- **14 处**：gate-result branch skips count/88 minimum selection and rejoins unmodified normal
  list conversion/return path
- **12 处**：gate-result branch goes to restore/RET with RAX user object preserved;
  **skipped count>=88 block zeroes object fields**

x86 形态统一是 74 xx → eb xx（je → jmp），上下文示例：

```
0x32ebf00  test al, al
0x32ebf02  je   0x32ebf83     ← patch 成 jmp（无条件跳过）
0x32ebf04  mov  r9, [rsp+0x70]
0x32ebf09  cmp  r9, 0x58      ← count vs 88（在“被跳过”的块内）
```

即：**count >= 88 时会执行一段「清零用户对象字段」的代码，amd 把它整块跳过**。

arm64 上对应的块（已定位）：

```
0x2e1fdac  tbz  w1, #0, 0x2e1fddc   ; gate
0x2e1fdb4  cmp  x1, #0x58            ; count vs 88
0x2e1fdb8  b.lt 0x2e1fddc
0x2e1fdbc  str  xzr, [x0, #0x38]     ; ← 清零字段 1
0x2e1fdd8  str  xzr, [x0, #0x40]     ; ← 清零字段 2
```

**但把这块整块跳过（12 处 tbz → b）、或让 b.lt → b.al，实测 100 用户仍然 0/5。**

## 3. 还差什么

- arm64 的这 12 处 cmp #88 + 清零 patch 后无效 → **说明 amd 的 gate-result 在 arm64 上
  对应的不是这 12 处**（amd 的 gate 是「授权/过期」布尔，arm64 这 12 处用的是 mapaccess 的 ok 位）。
- 下一步应当在 arm64 上按 **「清零多个对象字段的块」** 反查（而不是从 cmp #88 反查）：
  找形如 str xzr,[x0,#A] ... str xzr,[x0,#B] 且同一块内带 cmp #0x58 的代码，
  它的入口 gate 才是 amd 那 26 处的对应物。

## 4. 已移植且无效的组合（不要再重复）

| 补丁 | 处数 | 结果 @100 用户 |
|---|---|---|
| csel→nop（min 截断失效） | 10 | 0/5（且 add 停在 88） |
| cmp/mov imm 88→4095 | 10 | 0/5 |
| b.lt→b.al（跳过清零） | 12 | 0/5 |
| tbz→b（整块跳过，cleanup-skip） | 12 | 0/5 |

## 5. 复现

```bash
# amd
bash /root/labss/lab_vless.sh 100        # mock 18081 -> 实例 19590
# 本机（隧道 11956 -> 19590）
curl -x socks5h://127.0.0.1:21210 https://www.cloudflare.com/cdn-cgi/trace   # => 200
```