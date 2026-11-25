# CONFIG · 配置文件在哪、每个字段谁写、证书怎么弄

> 结论先给：**机场/主控信息都写在 `/etc/so**/so**.conf`**（真实路径用 `so-console paths` 看），
> 多机场则是 `/etc/so**/<实例名>.conf`；证书在 `/usr/local/soco/cert/` 或你自己给的路径。

---

## 1. 文件清单

| 文件 | 作用 | 谁写 |
|---|---|---|
| **`/etc/so**/so**.conf`** | **主配置文件 = 机场/主控信息文件**：面板类型、协议、节点 ID、面板地址、`webapi_key`、`so**_key`、间隔、日志、证书 | 控制台写；客户只需提供 4 项 |
| `/etc/so**/<实例名>.conf` | 多机场实例，字段与主配置完全一致（`0600`） | `so-console inst new` |
| `/usr/local/soco/cert/cert.pem` · `key.pem` | 业务 TLS 证书（自签或 ACME 落盘） | 控制台 / 程序 |
| `/usr/local/soco/licence/` | 授权 sink 的自签证书（**与业务证书无关**，别混用） | 控制台 |
| `/etc/systemd/system/soco*.service` | 服务单元（含 `LD_PRELOAD`、重启策略） | 控制台 |
| `journalctl -u soco` | 运行日志（`log_level=error` → **只记错误**） | 系统 |

查真实路径（不同机器可能不同）：

```bash
so-console paths
#   pkg        · /root/so
#   bin_dir    · /usr/local/soco
#   conf       · /etc/so**/so**.conf     ← 机场/主控配置文件
#   inst_dir   · /etc/so**               ← 多实例配置目录
```

---

## 2. `so**.conf` 字段表

| 键 | 例子 | 谁写 | 说明 |
|---|---|---|---|
| `type` | `xboard` | **固定** | 面板类型 |
| `api` | `webapi` | **固定** | 对接方式 |
| `server_type` | `ss` / `vless` / `vmess` / `trojan` / `anytls` / `hysteria` | **客户选** | 决定端口与是否需要证书 |
| `node_id` | `12` | **客户填** | 面板里的节点 ID |
| `webapi_url` | `https://panel.example.com` | **客户填** | 面板地址 |
| `webapi_key` | `3f9c1a7d…`（面板给的那串） | **客户填** | **面板通信密钥，必须与面板完全一致；不能随机**，否则拉不到用户 |
| `so**_key` | 任意串 | **自动（随机）** | 授权密钥；本工程已解除授权检查，随便写 |
| `check_interval` / `submit_interval` | `60` | **固定** | 拉取/回传间隔 |
| `log_level` | `error` | **固定** | 只记错误日志 |
| `cert_mode` | `panel` / `file` / `http` / `dns`（`self` 由控制台落成 `file`） | TLS 协议才有 | 证书来源 |
| `cert_domain` | `node.example.com` | TLS 协议才有 | 证书域名 / SNI |
| `cert_file` / `key_file` | `/usr/local/soco/cert/cert.pem` | TLS 协议才有 | 证书与私钥路径 |
| `dns_provider` | `cloudflare` / `aliyun` / `dnspod` | 仅 `cert_mode=dns` | DNS-01 提供商（API 凭证走环境变量） |

> 想让控制台重写一遍（会先备份 `.bak.<时间戳>`）：`so-console install …`，幂等。

---

## 3. 证书：和原版一致的五种方式（`cert_mode`）

| 模式 | 谁来出证书 | 需要准备什么 | 控制台怎么写 |
|---|---|---|---|
| **`panel`** | 面板（节点里配置的证书：上传内容或面板侧申请） | 面板节点里把证书配好 | 只写 `cert_mode=panel` + `cert_domain`，节点侧不写路径 |
| **`self`** | 本机自签（控制台用 openssl 生成，10 年） | 域名（可留空用 localhost） | 生成 `/usr/local/soco/cert/{cert.pem,key.pem}`，落成 `cert_mode=file` + 路径。**客户端需允许跳过校验** |
| **`file`** | 你已有的证书 | `fullchain.pem` + `privkey.pem` 路径 | 写 `cert_mode=file`、`cert_file`、`key_file`、`cert_domain`（不存在会直接报错） |
| **`http`** | 程序自己做 ACME HTTP-01 | 域名解析到本机、**80 端口公网可达** | 写 `cert_mode=http`、`cert_domain`；证书落到 `cert_file/key_file` |
| **`dns`** | 程序自己做 ACME DNS-01 | 域名 + `dns_provider` + 该商的 API 凭证（环境变量） | 写 `cert_mode=dns`、`cert_domain`、`dns_provider` |

**按协议分**

| 协议 | 需要证书？ | 说明 |
|---|---|---|
| `ss`（Shadowsocks 2022） | 不需要 | 不给 `--cert-mode` 即可 |
| `vless` | 通常不需要文件 | REALITY 的 `public_key / short_id / server_name` 由**面板下发**；要用 TLS 证书则按上表选一种 |
| `vmess` / `trojan` / `anytls` / `hysteria` | **需要** | 必须选一种 `cert_mode`；没域名先 `self` 跑通，再换 `http`/`dns` |

> 本工程使用的 `v2.18.1` 二进制里存在 `anytls_fallback_addr` / `anytls_fallback_port` 键，即**支持 anytls**；
> 它与 trojan 走同一条证书链路。

命令行等价写法：

```bash
# 面板下发证书（REALITY / 面板里配好的证书）
so-console install --node-id 12 --type vless --url https://panel --webapi-key <面板key> --cert-mode panel

# 本机自签（最快能用，客户端要允许不安全）
so-console install --node-id 12 --type trojan --url https://panel --webapi-key <面板key> \
  --cert-mode self --cert-domain node.example.com

# 已有证书
so-console install --node-id 12 --type trojan --url https://panel --webapi-key <面板key> \
  --cert-mode file --cert-domain node.example.com \
  --cert-file /etc/ssl/fullchain.pem --cert-key /etc/ssl/privkey.pem

# ACME
so-console install --node-id 12 --type vmess --url https://panel --webapi-key <面板key> \
  --cert-mode http --cert-domain node.example.com
so-console install --node-id 12 --type anytls --url https://panel --webapi-key <面板key> \
  --cert-mode dns --cert-domain node.example.com --dns-provider cloudflare
```

交互式则是在向导里选：`1) panel  2) self  3) file  4) http  5) dns`。

---

## 4. 改完怎么生效 / 怎么确认

```bash
so-console install ...          # 推荐：幂等重写 + 备份 + 自动重启 + 握手验证
# 或手改之后：
systemctl restart soco          # 只重启主服务，sink / nft 不用动
so-console doctor               # 逐项自检
so-console users                # 本地人数 == 面板人数
so-console probe 3              # 真实握手 3/3
```

证书相关问题看这两处：

```bash
journalctl -u soco -n 200 -o cat | grep -iE 'cert|tls|acme|reality' | tail -20
openssl x509 -in /usr/local/soco/cert/cert.pem -noout -subject -dates
```