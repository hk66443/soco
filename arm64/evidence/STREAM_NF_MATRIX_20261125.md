# 流媒体分流定位与修复（NF 出站节点选择）2026-11-25

## 1. 现象

ARM 节点（`ARM_IP`）通过客户端实测：

| 站点 | 结果 |
|---|---|
| `www.cloudflare.com` / `ipinfo.io` | 200（走 `rules=["*"]` → direct） |
| `www.netflix.com` | **000 超时 25 s** |
| `chatgpt.com` / `api.openai.com` | **000，TLS 握手失败** |

soco 日志证明路由命中正确、出站连接已建立：

```
user 1635 access address: www.netflix.com:443
domain www.netflix.com resolved: [207.45.72.1 ...]
tcp proxy dial ARM_LAN_IP:59236 -> node-us.nfdns.xyz:38383 (www.netflix.com:443)
start tcp relay: ... remote(104.238.222.105:38383)
end tcp relay:   ...（无数据返回，24 s 后结束）
```

## 2. 定位：不是 soco 的问题

在 AMD 上用 `/tmp/sing-box` **直接连 NF 的 ss 出站（不经 soco）**：

```
node-us:38383 → ifconfig.co 200（出口 104.238.222.105，US）
node-us:38383 → netflix 000（25 s 超时）
node-us:38383 → chatgpt 000（TLS unexpected eof）
```

→ soco 的路由/转发正常，**是 NF 美国节点对这些站点不通**。

## 3. NF 节点能力矩阵（2026-11-25，AMD 直连各节点实测）

| 节点 | 出口 | netflix | chatgpt | disney+ | hbo | prime |
|---|---|---|---|---|---|---|
| us（38383） | 104.238.222.105 US | 000 | 000 | 000 | 000 | 200 |
| hk（38888） | 154.88.64.34 HK | 000 | 000 | 000 | 200 | 200 |
| **tw（20558）** | 114.42.192.32 TW | **302** | **200** | **200** | **200** | **200** |
| kr（23355） | 83.147.61.2 HK | 302 | 000 | 200 | 000 | 200 |
| sg（20955） | 104.192.92.193 SG | 302 | 000 | 200 | 200 | 200 |
| jp（38123） | 141.11.131.10 JP | 000 | 000 | - | - | - |
| uk（25253） | 连接失败 | 000 | 000 | - | - | - |

结论：
- **美国节点对流媒体整体不可用**（只有 prime 通）；这也是原来 Netflix/ChatGPT 全 000 的原因。
- **台湾节点全通**（Netflix/Disney/HBO/Prime/ChatGPT），新加坡节点除 ChatGPT 外全通。

## 4. 修复（已上线）

在 `/etc/so**/routes.toml` 的 `enable=true` 之后插入一条最高优先级路由，把 Netflix / OpenAI 相关域名指到台湾出口：

```toml
[[routes]]
rules=[ "geosite:netflix", "domain:netflix.com", "domain:nflxvideo.net", "domain:nflximg.net",
        "geosite:openai", "domain:chatgpt.com", "domain:openai.com", "domain:oaistatic.com",
        "domain:oaiusercontent.com", "domain:oaistatsig.com" ]

[[routes.Outs]]
type="ss"
server="node-tw.nfdns.xyz"
port=20558
password="<REDACTED-NF-PASSWORD>-200e-4b79-900e-bd125a77c611"
cipher="chacha20-ietf-poly1305"
```

（补丁文件：`_ops/routes_tw_patch.toml`）

验证：

```
load routes config file </etc/so**/routes.toml> success, routes num: 11, enable: true
tcp proxy dial ... -> node-tw.nfdns.xyz:20558 (www.netflix.com:443)

www.netflix.com   -> 302  (2.66 s)
chatgpt.com       -> 200  (3.59 s)
api.openai.com    -> 421  (正常：无鉴权直连)
cloudflare trace  -> 200  (ip=ARM_IP)
current user num  -> 497
```

回滚：`cp /etc/so**/routes.toml.bak2.20261125015116 /etc/so**/routes.toml && systemctl restart soco`

## 5. 仍需注意

1. **`nfu so**` 重新生成 routes.toml 会覆盖这条补丁**，重跑后要重新插入（`_ops/routes_tw_patch.toml` 可直接拼）。
2. 现在 Netflix 走**台湾区**内容；要美区需要 NF 提供可用的美国流媒体节点（当前 US 节点只有 prime 能通）。
3. Disney+/HBO 仍走原跨国路由（美国出口），经节点仍 000；如要它们可用，把该路由的 Out 换成 tw（或 sg）即可，代价是内容地区随之变化。
4. 路由里 `rules` 顺序即匹配顺序：新补丁必须放在文件最前面（`enable=true` 后）才生效。