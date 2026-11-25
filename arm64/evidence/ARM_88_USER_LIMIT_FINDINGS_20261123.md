# ARM 侧「88 用户上限」实测结论 — 2026-11-23

> 一句话：**只解除了一半。** 适配层确实让 soco 从面板加载到 100 个用户（官方版只加载 88 个），
> 但**用户总数一旦超过 88，数据面整体关闭**：认证仍然通过、handle vless end 立即发生、
> 完全没有 tcp direct dial / tcp relay，连第 1 个用户都不通。
>
> 当前生产只有 1 个用户，**不受影响**；但若面板把 node <ARM_NODE_ID> 的用户加到 89+，节点会变成
> 「能握手、不出流量」—— 比官方版（截断到 88，前 88 个正常）更糟。

## 1. 实验方法（不碰生产）

生产实例 soco.service（49999）全程未动。实验在 /root/lab88/ 独立进行：

- **mock 面板**（arm64/deploy/lab/mock_panel.py，监听 127.0.0.1:18080）冒充 xboard/UniProxy：
  - /api/v1/server/UniProxy/config → 返回端口 19599 + REALITY 参数（固定 X25519 私钥 bytes(1..32)，短 ID a1b2c3d4e5f6）
  - /api/v1/server/UniProxy/user → 返回 N 个用户（N 由 /root/lab88/n_users 动态控制，uuid 由 <REDACTED-PANEL-UUID>… 递增）
- **实例 A**：LD_PRELOAD=/usr/local/soco/libsoco.so /usr/local/soco/soco -c /root/lab88/lab_a.conf（= 现役 soco 的组合）
- **客户端**：本机 sing-box 1.14.4，VLESS + REALITY + xtls-rprx-vision，经 SSH 本地转发 127.0.0.1:11959 → ARM_IP:19599
- **判据**：客户端 curl https://www.cloudflare.com/cdn-cgi/trace 是否 200 + 服务端是否出现 tcp direct dial / tcp relay

## 2. 核心数据

### 2.1 加载层：适配层确实生效

| 组合 | 面板下发 | add user 次数 | 最大 id |
|---|---|---|---|
| 官方 so**（3c42ba62…） | 100 | **88** | 88 |
| 现役 soco（37332960… + libsoco.so） | 100 | **100** | 100 |

### 2.2 转发层：88 是精确的分水岭

同一实例、同一客户端 uuid（user1，<REDACTED-PANEL-UUID>…）、同一目标 URL：

| 面板用户数 N | add user | current user num | 19599 监听 | 客户端 http | 服务端 dial |
|---|---|---|---|---|---|
| 1 | 1 | 1 | ✅ | **200** | ✅ |
| **88** | 88 | 88 | ✅ | **200** | ✅ |
| **89** | 89 | 89 | ✅ | **000** | ❌ |
| 90 | 90 | 90 | ✅ | **000** | ❌ |
| 92 | 92 | 92 | ✅ | **000** | ❌ |
| 97 | 97 | 97 | ✅ | **000** | ❌ |
| 100 | 100 | 100 | ✅ | **000** | ❌ |

000 时服务端日志的形态（N=92 的 A.out）：

```
DEBUG  start handle client 149.118.32.107:61201 connection
DEBUG  user 90 access address: www.cloudflare.com:443     ← 认证通过
DEBUG  domain www.cloudflare.com resolved: [...]
DEBUG  handle vless end                                    ← 立即结束，无 dial
```

统计：add user 92 行 / access address 1 行 / **direct dial 0 行** / **tcp relay 0 行**。
客户端侧：connection ... forcibly closed by the remote host。

注意：**N=89 时连 user1 也不通**（不是"只服务前 88 个"，而是"整体关数据面"）。

## 3. 结论与影响

1. libsoco.so 解除的是 **pull_users 的截断**（能加载 100 个用户，add user / current user num 都是 100）。
2. **没有**解除 **"用户总数 > 88 → 关闭数据面"** 的第二道闸门。这道闸门在 vless 转发路径上，与授权校验是两套逻辑：
   - 授权校验被 43 字节补丁绕过后，so** key 错误 只写日志，不影响 88 以内用户的流量（上一轮 30/30 握手已证）；
   - 用户数闸门不写日志、不报警，只是让 accept 后的连接静默结束。
3. 官方版不会触发它（自己截断到 88），所以"官方版能用 88 个"和"crack 版能加载 100 个"都不等于"能跑 100 个"。
4. **对现有生产无影响**：node <ARM_NODE_ID> 当前只有 1 个用户（id 1635），且已实测 netflix/chatgpt 正常转发。

## 4. 第二轮：定位闸门代码（2026-11-23 下午）

### 4.1 找到的两组 88

用 soco-arm64-legacy-delivery（174 字节重补丁版，症状同为"认证通过但从不 dial"）反推：
它的 54 处改动全是 tbz wX,#0 + b 形态。顺藤摸到同一代码区（0x2e10000–0x2e70000）里的两类 88：

```
# A 类（10 处）：截断
cmp  x1, #0x58        ; len(users) vs 88
mov  x5, #0x58
csel x1, x5, x1, gt   ; len = min(len, 88)
str  x1, [sp, ...]

# B 类（12 处）：闸门候选
cmp  x1, #0x58
b.lt skip             ; len < 88 就跳过
str  xzr, [x0, #0x38] ; len >= 88 时把某字段清零
```

地址（crack-so\*\*10 基址）：A 类 0x2e1bcf0 / 0x2e1fe4c / 0x2e21900 / 0x2e23120 / 0x2e25ed0 /
0x2e2bb90 / 0x2e4c848 / 0x2e4e83c / 0x2e5b718 / 0x2e604e8；B 类 12 处与之交错。

### 4.2 三种 patch 的实测结果（都是 n=100）

| 补丁 | 加载用户数 | 客户端 http | 说明 |
|---|---|---|---|
| 原版 crack 37332960…（+浮层） | 100 | **000** | 认证通过、无 dial |
| A 类 csel→nop | 88 | 200 | 分配/循环不一致，只加载 88 |
| A 类 cmp/mov imm→4095 | 88 | 200 | b.lt 判定变成"永远跳"，走回 88 路径 |
| B 类 b.lt→b.al（其它不动） | 100 | **000** | **闸门不在这 12 处** |

结论：**B 类不是 dial 的闸门**。100 用户时"认证通过→立即 handle vless end、无 tcp dial"
由**另一处独立逻辑**决定，位置尚未定位。

### 4.3 一个必须记住的操作坑

**libsoco.so 只对 /usr/local/soco/soco 这个路径下的二进制生效。**
把二进制复制到 /root/lab88/soco-x 再跑，即使 LD_PRELOAD 在 maps 里、environ 也有，
**适配层构造器也不会注入全量用户**（无 [soco] 日志、add user 只有 88）。
→ 做 88 相关实验必须**换到生产路径**（mv 旧 inode 保住运行中进程，再放新二进制），
实验后再 mv 回来。本轮的 4.2 表就是这样测的，测试后已回滚（磁盘 SHA256 恢复为 37332960…）。

### 4.4 下一步（若继续）

1. dial 决策点：<88 时走 tcp direct dial，>=88 时不走。用 gdb 在 >=88 时断 connect
   不命中、在 <88 时命中，二分两侧的 PC 差异；或在 handle vless end 的日志调用点
   （0x2f7f120 附近是日志封装，真正的调用者需从 bl 反查）下断。
2. 也可从"清零的字段 [x0+0x38]"入手：找到写它的位置（B 类 12 处），再看谁**读**它，
   读点就是被禁用的能力入口。

## 5. 如果要真的超过 88 个用户

两条路，按成本排序：

### 5.1 工程分片（零二进制改动，推荐先用）

一个 soco 实例只服务 ≤88 个用户，把用户摊到多个节点/端口上：

```
面板 node ARM_NODE_ID  → soco 实例 A  :49999  （用户 1..88）
面板 node 645  → soco 实例 B  :50001  （用户 89..176）
...
```

每个实例独立 -c /etc/soco/soco-<node>.conf（不同 node_id）+ 独立 unit，LD_PRELOAD 相同。
对客户端而言是多节点，不影响使用；面板侧只是多建几个同 IP 不同端口的 vless 节点。
代价：内存每实例 ~100 MB（这台 11.9 GB 够放 50+ 个），端口与防火墙要逐一对齐。

### 5.2 定位第二道闸门（需逆向，成本高）

已知边界：
- 阈值精确为 **88**（0x58），在"用户集合大小"这一层判定；
- 触发后行为：REALITY 握手成功 → VLESS 认证成功 → 立即 handle vless end，**不进入 dial**；
- 与授权无关（授权报错有日志，这个闸门没有）。

建议切入点（按性价比）：
1. 在 pclntab 里定位 add user 日志所在函数（add user: id: 字符串的引用者），看其调用链末端是否对 len(users) 做 >88 比较；
2. 在 vless 的 Accept 分发路径里找 len(...) > 0x58 形式的立即数比较（ARM64: cmp wX, #0x58 → b.le），
   把条件跳转改成无条件落正常分支；
3. A/B 时用本实验设施（/root/lab88/ + n_users 文件 + SSH 转发 11959）即可，每次 30 秒，不用碰生产。

> 参考：amd64 侧曾做到 **97 用户正常转发**（amd64/README 的验收记录），说明 amd64 的补丁是同时动了加载与转发两处；
> arm64 的 43 字节只动了授权分支与 8 个同名方法，**漏了用户数闸门**。

## 5. 复现命令（全部在工程内）

```bash
# 机器上
mkdir -p /root/lab88
# 拷入 arm64/deploy/lab/{mock_panel.py,lab_case.sh,lab_ab_100users.sh}
echo 100 > /root/lab88/n_users
python3 /root/lab88/mock_panel.py &            # 127.0.0.1:18080
bash /root/lab88/lab_case.sh 88 1              # N=88 + 适配层
# 本机（SSH 转发 11959 -> 19599 之后）
curl -x socks5h://127.0.0.1:21100 https://www.cloudflare.com/cdn-cgi/trace
```