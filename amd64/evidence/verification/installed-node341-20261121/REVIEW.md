# 生产部署验证回执 — soco amd64（node341 / 141.148.139.236）

**状态：DEPLOYED_VERIFIED。** 生产 `soco.service` 已由「旧 binary+旧适配器（上限 88）」切换为
`c463791a…` + `2f60b5f8…`，面板 97 个用户全部加载，端口 49989 首/末账号真实握手通过，配置与原始 soga 未改动。

> 本文件取代 README 中「此证据不是生产 49989 已升级部署」的历史表述；README / release-manifest 本身保持冻结（其 hash 仍与已签发检查器一致）。

## 1. 这次切换了什么

| 项目 | 切换前 | 切换后 |
|---|---|---|
| 主程序 | `1ddc7619…`（上限被钉 88） | `c463791ac4bf9ba82f28b8e87b148976f13397e1407ddab04d366579e4c80fed`（85,851,856 B，53 regions / 84 changed bytes） |
| 适配器 | `4b8818cc…`（formal，含 SOCO_LIMIT 逻辑） | `2f60b5f881c9ae462a9de843eaea4471bd4a386a467c4e4c82042355c7998ab7`（clean，26,216 B） |
| systemd unit | `c4363bd7…`（`Environment=SOCO_LIMIT=88`） | `b86d3044…`（无 SOCO_LIMIT 注入） |
| 配置 | `d7879d5b…` | `d7879d5b…`（**未改动**） |
| 原始 soga | `c0e0f396…` | `c0e0f396…`（**未改动**） |
| 进程 | PID 98900，加载 88 | PID 100320，加载 **97** |

`systemctl is-enabled` 保持切换前的 `disabled`（未擅自改为开机自启）；备份 `/root/soco-backup-final-20261121-v2`（0700）含一键回滚 `rollback.py`。

## 2. 运行期证据（全部来自真机 49989，非 mock）

| 检查 | 结果 |
|---|---|
| 监听就绪 | PID 100320 自有 TCP `:49989` LISTEN + UDP（就绪耗时 10.19 s） |
| 用户加载 | `current user num: 97` × 3 个周期（面板返回 97，用户 id 覆盖到 1634） |
| Go 刷新 | `go_counts=[97,97,97]`，初始后额外 2 个真实刷新周期 |
| 首/末身份 | ordinal 1 与 97，初始与两轮刷新后各 HTTP 200 + HTTPS 200 / TLSv1.3 / curl 0，出口 IP 141.148.139.236 |
| 错误口令负控 | 拒绝（HTTP 0 / curl 52，未到目标） |
| 自检脚本 | `soco-verify` exit 0 |
| 进程身份 | 验证前后同一 PID，无重启、无客户端残留（cleanup_errors 空） |
| key 错误日志 | 1 条；**与本次改动无关**——切换前长期正常运行的旧组合每次启动也都有该条 |

## 3. 上一轮部署失败的真正原因（已定位并修好）

v1 部署在 0.932 s 处失败并自动回滚，原因不是候选程序不可用，而是**验证器竞态**：
`postdeploy_validate_v2` 之前的版本在进程还没绑定 49989 时即时断言 `owned_production_listeners` 非空。
真机实测就绪需要约 10.2 s（先拉面板用户、再监听）。

修复：新增 `postdeploy_validate_v2.py` —— 先轮询「本进程持有 49989 LISTEN」+「首个 `current user num` 周期」，
再做出口身份与两轮刷新断言；`deploy_final_v2.py` 同时把「旧 PID 硬编码 80093」改为动态取当前 MainPID，并使用新的 v2 备份/工作根。

## 4. 复现与取证

- 远端：`/root/soco-verified-tests/installed-node341-final-20261121-v2/result.json`（验证器原始结果）
- 远端：`/root/soco-verified-tests/final-deploy-20261121-v2/deploy_receipt.json`（部署/回滚回执）
- 远端：`/root/soco-verified-tests/deploy-v2-exec.log`（后台执行日志）
- 本目录：[review.json](review.json)（脱敏、无 UUID/口令/节点密钥，只含 hash 与结果）

## 5. 边界

只测了首/末两个身份与两轮刷新，**不代表** 6000 并发、全部账号逐一验证或 48 小时长稳；未涉及 VLESS Reality / UDP / WS / gRPC 等本节点未启用的协议；ARM 产物本轮回未改动。