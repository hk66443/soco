# soco 节点工程 · amd64 + arm64（含控制台）

一套可直接部署到**任意新机器**的节点工程包：so** v2.18.1 兼容节点程序的深度改造 +
一个单文件控制台（console/so-console）。解决的问题只有两个：

| 问题 | 现象 | 本工程的做法 |
|---|---|---|
| **88 用户上限** | 面板下发 >88 个用户时，只 add user 到 88 | 二进制补丁（amd64 53 区域 / arm64 10 处控制闭包）+ 适配层 libsoco.so |
| **600 秒授权闸门** | 跑满 600 s 后认证照过、但**不转发**（新连接全挂） | 让授权检查"快速失败"（hosts + 本地 sink + nft 分流转发），不动业务逻辑 |

两台真实机器的实测结果（细节在 docs/ 与各架构 evidence/）：**497 个用户逐个独立握手 + 真实转发，497/497 全过**，
服务端 497 authenticated / 497 relayed / 0 auth failed，NRestarts=0。

> **关于 so****：教程里把程序名统一写成 so**（不出现完整产品名）。凡是路径、变量、命令里出现 so**，
> 都指代同一个名字；真实路径不用记，用 so-console paths 打出来即可。所有 IP / node id 也都是占位符，
> 换成你自己的；占位符清单见 [SECURITY.md](SECURITY.md)。

---

## 1. 三分钟上手（新机器）

```bash
# ① 把整个项目上传到服务器（只传项目，不要传任何本地备份/私钥）
scp -r ./soco root@<你的服务器>:/root/so

# ② 一条命令安装（自动：目录/证书/hosts/nft/systemd + 闸门自检）
/root/so/console/so-console install /root/so

# ③ 验证（3 个用户真实握手 → 全量自检）
/root/so/console/so-console probe 3
/root/so/console/so-console doctor
```

不带参数运行 so-console 就是**交互控制台**：

```
 so-console · amd64 · 2026-01-01 12:00:00
==========================================================
  1) status    状态总览（服务/端口/人数/闸门/routes）
  2) install   安装或修复（目录/证书/hosts/nft/systemd）
  3) service   启动 / 停止 / 重启
  4) users     本地与面板用户数对照
  5) probe     真实握手测试（3 / 497 / all）
  6) gate      600 秒闸门自检
  7) routes    流媒体分流：list / switch <地区> / validate
  8) inst      多实例：list / new / start / stop / log / remove
  9) logs      看日志（unit [行数]）
 10) backup    备份 /usr/local/soco + 配置
 11) rollback  从备份回滚
 12) verify    指纹与适配层检查
 13) doctor    全量自检（逐项 PASS/FAIL）
 14) paths     显示真实路径（配置/二进制/实例）
  0) 退出
so> 
```

也可以直接敲命令，脚本/自动化同样适用：so-console status、so-console probe 497、so-console routes switch tw。

---

## 2. 两个架构的差别（装之前先确认自己是哪种）

| | **amd64**（x86_64） | **arm64**（aarch64） |
|---|---|---|
| 典型协议 | Shadowsocks 2022（2022-blake3-aes-256-gcm） | VLESS + REALITY（xtls-rprx-vision） |
| 二进制 | 53 区域补丁版 | **variantE**（variantC + 8 处 mov #3→xzr） |
| 适配层 | 必需：LD_PRELOAD=libsoco.so 抓全量用户表 | 同样加载 libsoco.so（aarch64 版） |
| 88 上限解法 | 补丁 + 适配层 | 10 处控制闭包补丁 |
| 600 s 闸门 | 环境旁路（hosts + sink + nft） | 环境旁路 **+** 补回 8 处补丁 |
| 分流 routes.toml | 通常不用 | 常用（NF/ChatGPT 走指定地区出口） |
| 内存要求 | ≥1 GB（单实例 ≈80 MB，压测时别叠实例） | ≥2 GB（单实例 ≈95 MB） |
| 实测规模 | 497 用户 / 串行全量约 20 min | 497 用户 / 串行全量约 7 min |

> 两边的补丁**不可互换**：补丁偏移、函数入口、闭包数量都不同。按架构走对应文档，别交叉照搬。

---

## 3. 目录

```
soco/
├── README.md                 ← 本文件（总览 + 三分钟上手 + 架构差别）
├── DEPLOY.md                 ← 新机器部署全流程（amd64 / arm64 都适用）
├── CONSOLE.md                ← 控制台命令参考
├── SECURITY.md               ← 仓库里哪些值被屏蔽了、你自己的值要填在哪
├── HANDOFF.md                ← 接手包（环境、服务清单、踩过的坑、待办）
├── BYPASS.md                 ← 绕过过程全记录（实验数据与排除结论）
├── console/
│   └── so-console            ← 单文件控制台（Python3，无第三方依赖）
├── amd64/
│   ├── src/                  ← 适配器 C 源码、licence sink、mesh、探测与实验室脚本
│   ├── deploy/               ← 部署/切换/回滚脚本 + 运维手册
│   ├── manifest/             ← 53 处补丁清单、静态校验、构建溯源
│   └── evidence/             ← 二分实验、映射报告、运行时证据、全量跑批日志
├── arm64/
│   ├── analysis/             ← 43 字节 crack 逐处分析
│   ├── deploy/               ← 一键部署、分流切换、mock 面板、运维脚本
│   ├── manifest/             ← SHA256SUMS、溯源
│   └── evidence/             ← 88 上限解除全过程、全量、分流修复、多实例
├── packaging/                ← 通用交付：install-soco.sh、soco-multi.sh、watchdog、routes-guard
└── _ops/                     ← 实战脚本：probe_many.py、build_variant*.py、隧道、跑批
```

**二进制不在仓库里**（每个 80–90 MB）：要么用 _ops/build_variant*.py 从原版重建，
要么从旧机器的 /usr/local/soco/ 备份取回。见 [DEPLOY.md](DEPLOY.md) §2。

---

## 4. 判健康只有一条标准

**跑一次真实协议握手，并且确认服务端真的 dial + relay 了。**

```bash
/root/so/console/so-console probe 3        # 期望 3/3
/root/so/console/so-console doctor         # 期望 ALL PASS
```

ss -lnt、nc -z、ping 端口 全部**不可信**：闸门打开时端口照样 LISTEN，accept 后立即 close、不读字节，
已建立的旧连接也仍然活着。这就是为什么本工程所有验证都走真实握手（[_ops/probe_many.py](_ops/probe_many.py)）。

---

## 5. 文档索引

| 想干什么 | 看哪份 |
|---|---|
| 新机器从零装一套（amd64 或 arm64） | [DEPLOY.md](DEPLOY.md) |
| 记不住命令 / 想用控制台操作 | [CONSOLE.md](CONSOLE.md) |
| 上线后回滚、卸载、换机 | [DEPLOY.md](DEPLOY.md) §9 / §10 |
| 为什么这么改、怎么排错到字节级 | [BYPASS.md](BYPASS.md)、*/evidence/ |
| 交接给下一个人 / 下一个 AI | [HANDOFF.md](HANDOFF.md) |
| 仓库里的占位符怎么填自己的值 | [SECURITY.md](SECURITY.md) |

## 6. 使用边界

1. 600 s 闸门**没有**从二进制里彻底移除，靠 hosts + 本地 sink 维持；so-console doctor 会逐项检查，缺一项就退回"600 s 后新连接全断"。
2. 一台机**不要**同时跑两个实例压满人数：适配层状态会互相顶掉。要多机场就多开机器，或独立目录 + 独立端口 + 不同时打满。
3. routes.toml 是**模板**（含 {Out}/{OutPort} 等占位符），写坏会**静默**退回 0 条——so-console routes validate 后再 list 看 loaded 那一行。
4. 本工程针对闭源商业程序做了逆向与补丁，仅供你在**自己已授权**的环境使用。