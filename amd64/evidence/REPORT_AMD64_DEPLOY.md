# amd64 生产切换记录（承接 session-015c9db4 的 amd 收口）

时间：2026-11-21 09:29–09:37 UTC ｜ 目标机：141.148.139.236（Debian 13, x86_64, node_id=341）

## 1. 接手时的真实状态（从上一会话证据复核）

上一会话已经做完的：`c463791a…`（53 regions / 133 span / 84 changed bytes）+ clean 适配器 `2f60b5f8…` 在隔离环境
（mock 89/97/6000、真实 node341 97 用户）全部通过；**只有最终生产部署失败**，失败回执在
`_deploy/implementation_amd64_verified/failed-deploy-20261121-v1/`，形态是：安装 exit0、新 PID 98771 起来、
0.932 s 时验证器断言 `owned_production_listeners=[]` 失败、自动回滚回旧 binary/旧 so/原 config，生产回到旧 PID 98900。

上一会话留下的两个未决疑点：

1. 验证器 0.9 s 就断言 listener 非空——疑似启动竞态；
2. 失败新 PID 的日志里有 1 条 `soga key 错误`，怀疑 amd64 的 key 分支没打全。

## 2. 本轮做的定位（不是猜，是实测）

**key 错误：与本次改动无关。** 直接只读拉取"当前一直正常工作"的旧服务（PID 98900 / 1ddc + 4b88）的 journal：
其启动日志同样有 `soga key 错误`（本次 invocation 共 8 条），随后照常 `current user num: 88` 并在 49989 监听。
→ 这条日志是 soga 官方 key 提交通道对非官方 key 的正常输出，旧组合也有，不影响加载与转发。
另：`soga key 错误` 在 amd64/ARM 原版与 crack 版里**都不是明文串**（被混淆），静态字符串检索会落空，应改用运行期日志做判据。

**listener 为空：纯验证器竞态。** 旧服务从启动到 49989 监听约 2 s；候选版实测就绪 10.19 s（先拉 97 用户再监听）。
所以 0.932 s 的即时断言必然为空——不是候选程序不能监听。

## 3. 本轮改的东西

| 文件 | 变更 |
|---|---|
| `deploy_final_v2.py`（新） | ① 旧 PID 从硬编码 `80093` 改为动态取当前 MainPID（上一轮回滚后生产已是 98900，v1 脚本会在第一步就 assert 死）；② 工作/备份根改为 `final-deploy-20261121-v2`、`/root/soco-backup-final-20261121-v2`；③ 调新验证器；④ 启动后最多等 30 s 拿新 PID。 |
| `postdeploy_validate_v2.py`（新） | ① **先就绪再断言**：轮询"本进程持有 49989 LISTEN"（≤60 s）+ 等到首个 `current user num` 周期；② 断言每周期都是 97（88 会失败）；③ 删除"日志不得出现 key 错误"的旧断言（旧正常服务也有该条）；④ 就绪/首个周期耗时写进结果。 |
| 部署方式 | 远端 `setsid nohup` 后台执行 + 轮询日志，避免 SSH 450 s 截止线把一次真部署打断在两可状态。 |

候选程序、适配器、安装包**一字未改**（install.sh `bb830da4…` / verify.sh `1bcd019e…` / soco `c463791a…` / so `2f60b5f8…`）。

## 4. 结果

- `stage=installed_verified`、`passed=true`、`rollback=null`；旧 PID 98900 → 新 PID 100320，NRestarts=0。
- 生产 49989：TCP LISTEN + UDP，进程自有；`current user num: 97`（面板 97，用户 id 到 1634），99 分钟观察窗内 7 个周期全 97。
- 运行期真实转发：ordinal 1 与 97（初始 + 两轮刷新后共 4 组）HTTP 200 / HTTPS 200 TLSv1.3 / curl 0，出口 IP 141.148.139.236；
  错误口令负控被拒（HTTP 0 / curl 52）；`soco-verify` exit 0；验证前后同一 PID、无残留客户端进程。
- 配置 `d7879d5b…` 与原始 soga `c0e0f396…` 未动；enabled 保持 `disabled`；备份 + 一键回滚在 `/root/soco-backup-final-20261121-v2`。
- 交付侧回执：`C:\Users\adminuser\Downloads\soco\verification\installed-node341-20261121\`（`review.json` + `REVIEW.md`，脱敏无口令/UUID）。

## 5. 证据位置

| 内容 | 路径 |
|---|---|
| 验证器原始结果（55 KB，无口令/UUID） | `keypath-amd64-v1/installed-v2-result.json`（sha `b39d4f3c…`） |
| 部署回执（前后 hash、install/start/stop 退出码） | `keypath-amd64-v1/deploy_receipt_v2.json`（sha `f8e4c4da…`） |
| 验证器 stdout/exit0 | `keypath-amd64-v1/validation_execution_v2.json` |
| 只读健康检查快照 | `keypath-amd64-v1/health_v2.json`、`prod_readonly_state.json`、`preflight_v2.json` |
| 远端 | `/root/soco-verified-tests/{installed-node341-final-20261121-v2,final-deploy-20261121-v2}/`、`deploy-v2-exec.log` |

## 6. 现在回滚只要一条命令

```bash
python3 /root/soco-backup-final-20261121-v2/rollback.py
```

（备份根 0700，含旧 binary `1ddc…`、旧 so `4b88…`、原 config `d787…`、原 unit `c436…`）

## 7. 没做的边界

只测首/末身份 + 两轮刷新；没有 6000 并发、没有逐账号验证、没有 48 h 长稳；本节点是 SS2022，VLESS/Reality/UDP 未在本节点启用也未验证；ARM 产物本轮未改动。