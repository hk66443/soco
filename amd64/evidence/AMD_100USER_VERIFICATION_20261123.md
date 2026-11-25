# amd64 侧 100 用户验证（2026-11-23）

> 结论：**amd64 上「面板 100 个用户 + SS2022」实测 5/5 全部 200，完全可用。**
> 同一套方法在 arm64 上「100 用户 + vless」是 0/5。所以「单节点 100 人」是可行的，
> 限制只出在 **vless 路径**（或 arm64 缺对应补丁），不是「soga 一律 90 封顶」。

## 1. 被测对象

| | amd64 | arm64 |
|---|---|---|
| 主机 | `141.148.139.236` | `130.61.141.143` |
| 二进制 | `soco` = `c463791a…`（53 区域补丁）+ `libsoco.so` `2f60b5f8…` | `soco` = `37332960…`（43 字节）+ `libsoco.so` `f5fc39df…` |
| 协议 | **SS2022**（`2022-blake3-aes-256-gcm`，`server_type=ss`） | **VLESS + REALITY**（`server_type=vless`） |
| 面板节点 | node 341（经 `127.0.0.1:50402` mesh 代理） | node 644 |

## 2. 实验设计（生产全程未动）

- **mock 面板**（`amd64/deploy/lab/mock_panel_ss.py`，`127.0.0.1:18080`）冒充 xboard：
  - `/config` → `server_port=19589` + 固定 `server_key` + `cipher=2022-blake3-aes-256-gcm`
  - `/user` → N 个用户（N 由 `/root/labss/n_users` 控制），`uuid` 用异或种子生成，**保证前 32 字符互不相同**
- **隔离实例**：`LD_PRELOAD=/usr/local/soco/libsoco.so /usr/local/soco/soco -c /root/labss/lab_ss.conf`（node_id 1100 → 19589）
- **客户端**：本机 sing-box 1.14.4，shadowsocks outbound，`password = server_key + ":" + base64(uuid[:32])`，经 SSH 本地转发 `11957 → 19589`
- **判据**：`curl https://www.cloudflare.com/cdn-cgi/trace` 是否 200 + 出口 IP

> SS2022 的坑：`password` 是 `base64(uuid 前 32 字符)`。如果 uuid 只是末位递增（前 32 字相同），
> 100 个用户的 password 会全部相同 → 实际只有 1 个唯一用户（第一版实验就踩了这个，`unique_pw=1`）。
> 必须让 uuid 的高位也不同，才有 100 个独立用户。修正后 `unique_pw=100`。

## 3. 结果

| 用户数 | `add user` | `unique password` | `current user num` | 客户端结果 |
|---|---|---|---|---|
| 1 | 1 | 1 | 1 | **200 x 3/3**（出口 `141.148.139.236`, loc=US） |
| **100** | **100** | **100** | **100** | **200 x 5/5**（同上） |

对照（arm64 vless，同一套 mock 方法）：

| 用户数 | `add user` | 客户端 |
|---|---|---|
| 88 | 88 | 200 x 6/6 |
| 89 ~ 100 | 89 ~ 100 | **000（认证通过、无 dial）** |

## 4. 结论

1. **「单节点 100 人」不是做不到** —— amd64 的 SS2022 实例在 100 个唯一用户下转发完全正常。
2. 差异在**协议路径**（或 arm64 的补丁不完整）：vless 的 100 用户路径在 arm64 上 `access address` 后
   直接 `handle vless end`，`tcp direct dial` 从不出现；SS2022 没有这个问题。
3. 因此 arm64 上要 100 人，**首选换 `server_type=ss`（SS2022）**；
   如果必须在 vless 上做，才需要继续找 arm64 缺的那处补丁。

## 5. 复现命令

```bash
# amd 机器
mkdir -p /root/labss
# 拷入 amd64/deploy/lab/{mock_panel_ss.py,lab_ss.sh}
cat > /root/labss/lab_ss.conf <<'EOF'
type=xboard
server_type=ss
node_id=1100
soga_key=<REDACTED>
api=webapi
webapi_url=http://127.0.0.1:18080
webapi_key=<REDACTED>
log_level=debug
check_interval=60
submit_interval=60
EOF
# 关键：按端口清场，避免 bind: address already in use 让新实例根本没起来
ss -lntp | grep ':19589 ' | grep -oE 'pid=[0-9]+' | cut -d= -f2 | xargs -r kill -9
bash /root/labss/lab_ss.sh 100
# 本机（SSH 转发 11957 -> 19589 之后）
curl -x socks5h://127.0.0.1:21200 https://www.cloudflare.com/cdn-cgi/trace
```

## 6. 踩坑记录

| 坑 | 现象 | 解决 |
|---|---|---|
| uuid 只递增末位 | 100 个用户的 `password` 全相同，`unique_pw=1` | uuid 用异或种子，保证前 32 字符不同 |
| 旧实例没杀干净 | `new server err: listen tcp :19589: bind: address already in use`，新实例根本没监听，测试全落在旧实例上 | 按端口 `ss -lntp | grep :19589 | kill -9` 清场，再起 |
| SS 用户是启动 10 秒后才灌 | 采样太早会看到 `add user=0` | 起实例后 sleep 8~10 秒再判定 |
| `pkill -f 'soco -c /root/labss/lab_ss.conf'` 未生效 | 旧进程残留 | 改用按端口杀 |