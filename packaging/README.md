# packaging — release 包装 + 多实例安装

> 这里的**旧包装**（`install.sh` / `verify.sh` / `release-manifest.json` 等）是上一轮交付（`verified53-20261121-minimal-v1`）的流水线，
> 600 s 授权闸门结论**没有**纳入。新机器部署仍优先用 [../amd64/deploy/RUNBOOK.md](../amd64/deploy/RUNBOOK.md)。

## 多实例 / soga 目录兼容（2026-11-25，现行）

| 文件 | 作用 |
|---|---|
| `install-soco.sh` | 安装/更新 soco（保留 `/etc/soga` 与所有实例；`--no-restart` 只改单元） |
| `soco-multi.sh` | 多实例管理脚本 → 安装为 `/usr/bin/soco`（`list/new/remove/rename/start/stop/restart/log/config/update/uninstall`） |
| `soco.service` | 主实例单元：**不带 `-c`**，用 soco 默认的 `/etc/soga/soga.conf` |
| `soco@.service` | 多实例模板：`-c /etc/soga/%i.conf` |
| `MULTI_INSTANCE.md` | 使用手册（配置位置、实例隔离、screen/nohup、流媒体、回滚） |

要点：
1. soco 的 `-c` 默认值本来就是 `/etc/soga/soga.conf`，与 soga 完全一致；流媒体 `routes.toml` 等继续放 `/etc/soga/`，`nfu soga` 可直接用。
2. 多实例 = 一实例一配置（`/etc/soga/<name>.conf`）+ 独立 `log_file_dir` / `ip_user_cache_save_dir` / `access_log_dir`（在 `/etc/soga/instances/<name>/`）。
3. 同机多实例已验证隔离（见 [../arm64/evidence/MULTI_INSTANCE_20261125.md](../arm64/evidence/MULTI_INSTANCE_20261125.md)）。
4. licence sink 已从 443 换到 `38443` + nft 本地 dnat，**443 可留给网站/证书**。

## 旧 release 内容（仅供复现）

| 文件 | 作用 |
|---|---|
| `install.sh` | 旧安装器（校验四产物 hash + GLIBC ≥ 2.38；支持 `--dry-run`） |
| `verify.sh` | 旧主机侧校验（uname 双架构四 hash、MainPID/exe/maps、journal 绑定；始终输出 `traffic_status=NOT_TESTED`） |
| `uninstall.sh` | 卸载 |
| `release-manifest.json` | 旧 release 清单（四产物 hash、source/build/receipt 链接、doc/sourcehash） |
| `README_legacy-release-20261121.md` | 旧 README 原文（含当时的验证范围、ABI 说明、53 区域解释） |
| `candidate_manifest.authority.json` | 旧"补丁权威清单"（53 区域逐条），与 `../amd64/manifest/patch-manifest-amd64.json` 同源 |
| `artifact_metadata.py` / `build-amd64.py` / `build-amd64-reviewed.py` | 旧构建脚本（从 pristine 源重建出 c463 并断言 hash） |
| `check-soco.py` / `package_checker.py` | 旧静态校验器（ELF class/machine、slice 覆盖、整文件重建、hash 链） |
| `VERSION` | 旧版本号（0.1.0） |

## 已知差异（别被误导）

1. 旧 install/verify **不包含** `/etc/hosts` + `:443` sink 这一步——按旧流程装完，会在进程启动约 600 s 后出现"新连接全 52"。必须补 [RUNBOOK 第 1.3 步](../amd64/deploy/RUNBOOK.md)。
2. 旧 `verify.sh` 的 `traffic_status=NOT_TESTED` 是诚实标注：它只做静态/进程校验，不代表协议可用。健康判据始终是真实 SS2022 握手（`../amd64/src/probe_v2.py`）。
3. 旧 manifest 里的 ARM 产物标 `unverified-retained`（源码与已编译产物的对应未回收），不要据此宣称 ARM 已被本轮验证。