# SECURITY · 仓库里哪些值被脱敏了，怎么填自己的

这个仓库是**公开**的，但它的内容原本来自两台真实生产节点。
推送前做了一遍机械脱敏：**凭据类一律替换成占位符，拓扑类（IP / 端口 / 节点 id / 协议）保留**，
这样文档仍然是"能照做的操作手册"，而别人拿到仓库也拿不到任何可登录的东西。

## 1. 已替换（这些值在仓库里是占位符）

| 类别 | 仓库里的样子 | 说明 |
|---|---|---|
| 服务器 root 密码 | `<REDACTED-PASSWORD>` | 原值只在你自己机器的 `HANDOFF.md`（未脱敏副本）里 |
| 面板域名 | `panel.example.com` | 你的 xboard 面板地址 |
| `soga_key` / `webapi_key` / `api_key` / `token` | `<REDACTED>` | 面板「服务器 → 节点」里各自一对 |
| NF 节点密码 / 面板 uuid | `<REDACTED-NF-PASSWORD>` / `<REDACTED-PANEL-UUID>` | 流媒体出站用 |
| REALITY `public_key` / `short_id` | `<REDACTED-REALITY-PBK>` / `<REDACTED-REALITY-SID>` | 面板下发，随节点变 |
| 订阅里的用户 uuid | `<UUID>` | `routes.toml` 模板、示例配置 |
| 住宅代理池账号 / 会话 | `<REDACTED-PROXY-USER>` / `<REDACTED-PROXY-SESSION>` | 压测用，与业务无关 |

## 2. 保留的（有意的）

- 节点公网 IP、私网 IP、业务端口（`49989` / `49999`）、`node_id`（341 / 644）、协议与加密套件；
- 二进制 sha256、补丁偏移与字节、实验数据、故障时间线。

理由：这些是"怎么做的"证据，且 IP/端口在你的订阅里本来就发给客户了。
**如果你希望连 IP 也不出现**，全仓库替换即可（`sed -i 's/141\.148\.139\.236/<AMD_IP>/g'` 之类），章节结构不用动。

## 3. 你自己的机器要填这些值

```bash
# 面板连接（两台一样）
/etc/soga/soga.conf:
  webapi_url=https://<你的面板域名>
  webapi_key=<面板 → 服务器 → webapi 里那一串>
  soga_key=<同上那一对里的另一个>
  node_id=<面板里的节点 id>

# 流媒体出站（ARM 专用）
/etc/soga/routes.toml:
  server="<出站域名>"  port=<端口>  password="<出站密码>"
  # 规则里的 {UUID} 占位符用你自己节点用户的 uuid
```

## 4. 别做的事

1. **别把带真实口令的 `HANDOFF.md` / `soga.conf` / `routes.toml` 直接提交**（本仓库那份已经过 §1 的替换）。
2. **别在 issue / PR 里贴 `journalctl` 全文**——里面有面板 URL、uuid、出站地址。
3. 本仓库含对闭源商业程序 `soga v2.18.1` 的**逆向与补丁产物/方法**，仅供你自己已授权的环境使用；
   分发二进制或用于对外售卖，法律与商业风险自负。
4. 生产机上 `LD_PRELOAD` 的 `.so` 权限保持 `0600 root:root`；`/etc/soga/soga.conf` 同样 `600`。

## 5. 泄露了怎么办

1. 立刻换 root 密码 → `passwd`；换面板 `webapi_key` / `soga_key`（面板里点刷新，节点侧同步改 `soga.conf` 后 `systemctl restart soco`）；
2. 检查 `/etc/hosts` 4 条 licence 记录与 `soco-licence-sink` 是否还在（被删 → 600 s 后新连接全断）；
3. `sha256sum /usr/local/soco/{soco,libsoco.so}` 对照本文档记录值，不符就按 USAGE 手册回滚。