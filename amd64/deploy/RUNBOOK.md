# amd64 运维手册（RUNBOOK）

> 适用：Debian 12/13 x86_64，systemd，单节点 soga v2.18.1 + 适配器 + 环境旁路。
> 所有命令以 root 执行；`PROBE` = 真实 SS2022 握手探测，唯一可信健康判据。

---

## 0. 文件清单（本目录）

```
deploy/
├── soco.service                  主服务单元（LD_PRELOAD=libsoco.so）
├── soco-watchdog.service         watchdog 单元（PREEMPT_SECONDS=0 / FAILS_TO_RESTART=3 / PROBE_EVERY=30）
├── soco-watchdog.py              watchdog 实现（读 unit 注入的环境变量）
├── soco-licence-sink.service     本地 :443 sink 单元
├── licence-sink.py               sink 实现（自签证书，握手即拒）
├── soco-mesh.service             备选架构（中继+轮换）单元
├── soco-mesh.py                  备选架构实现
├── final_switch_single2.sh       一键：装 sink → 停 mesh → 起单进程 → 探测 → 起 soak
├── deploy_mesh_prod.sh           一键：停单进程 → 起 mesh → 探测
├── restore_c463.sh               把主程序恢复成已验证的 c463791a…
├── check_prod_mesh.sh            只读：看 mesh 轮换/状态/监听
├── status_final.sh               只读：单进程态的全量状态快照
├── launch_fakelic_long.sh        实验室：30 min 单进程验证（licence 快速失败）
├── lab_hosts_hang.sh             实验室：黑洞对照（应延迟到 ~641 s）
└── lab_fake_licence.sh           实验室：从零搭 sink 并观察
```

---

## 1. 全新部署（从零到可用）

```bash
# ── 1.1 目录与二进制 ─────────────────────────────────────────────
install -d -m 0755 /usr/local/soco /usr/local/soco/licence
install -m 0755 soco-amd64        /usr/local/soco/soco
install -m 0600 libsoco-amd64.so  /usr/local/soco/libsoco.so
install -m 0755 licence-sink.py   /usr/local/soco/licence/sink.py
# 自签证书（sink 只需要"被 soco 拒绝"，不需要可信）
openssl req -x509 -newkey rsa:2048 -nodes -days 3 \
  -keyout /usr/local/soco/licence/key.pem -out /usr/local/soco/licence/cert.pem \
  -subj "/CN=sksjd.vaxilu.com" -addext "subjectAltName=DNS:sksjd.vaxilu.com"
chmod 600 /usr/local/soco/licence/key.pem

# ── 1.2 面板配置 ────────────────────────────────────────────────
install -d -m 0755 /etc/soco
cat > /etc/soco/soco.conf <<'EOF'
type=xboard
server_type=ss
node_id=341
soga_key=<面板给的 soga_key>
api=webapi
webapi_url=https://<面板域名>
webapi_key=<面板给的 webapi_key>
check_interval=60
submit_interval=60
log_level=info
EOF
chmod 600 /etc/soco/soco.conf

# ── 1.3 授权域名指向本机（关键步骤） ────────────────────────────
cat >> /etc/hosts <<'EOF'
127.0.0.1 sksjd.vaxilu.com
127.0.0.1 agdfgkdfg.singledance.xyz
127.0.0.1 boiudihsdfk.singledance.xyz
127.0.0.1 sxp7hu5t.cilema.xyz
EOF

# ── 1.4 单元与服务 ──────────────────────────────────────────────
install -m 0644 soco.service soco-watchdog.service soco-licence-sink.service /etc/systemd/system/
install -m 0755 soco-watchdog.py /usr/local/soco/soco-watchdog.py
systemctl daemon-reload
systemctl enable --now soco-licence-sink.service soco.service soco-watchdog.service
```

`/etc/systemd/system/soco.service` 的关键三行：

```ini
Environment=LD_PRELOAD=/usr/local/soco/libsoco.so
ExecStart=/usr/local/soco/soco -c /etc/soco/soco.conf
Restart=always
```

---

## 2. 验证（必须做这一条）

```bash
cd /root/soco-verified-tests && python3 probe_v2.py --run-id "check-$(date +%H%M%S)"
# 期望: {"PASS": true, "curl_exit": 0, "body": "PROBE-..."}
```

判定表：

| 现象 | 含义 |
|---|---|
| `PASS=true, curl 0, body=PROBE-*` | 健康 |
| `curl 52/56` + 服务端日志**无** `start handle client` | **已进入停摆态**（闸门关了）→ 查 hosts / sink / 是否被改回 |
| `curl 7` | 端口没在听 / 进程没了 |
| PASS 但服务端日志有 `soga key 错误` 且进程 uptime > 600 s | 说明 sink 没生效，检查 `soco-licence-sink` 与 hosts |

**不要**用 `ss -lnt` 或 `nc -z` 判健康——停摆态下端口照听、TCP 照连。

---

## 3. 常驻观察

```bash
# 45 分钟 soak（每 20 s 一次真实握手）
cd /root/soco-verified-tests
setsid nohup python3 probe_mesh_v2.py --run-id soak-$(date +%m%d%H%M) --port 49989 \
  --duration 2700 --every 20 > /tmp/soak.out 2>&1 &
# 结果: /root/soco-verified-tests/<run-id>/result.json  → probes / fails / first_failure
```

```bash
# 进程年龄与关键日志（判断闸门是否在 600 s 处发作）
systemctl show soco.service --property=ExecMainStartTimestamp,NRestarts,MainPID
journalctl -b _PID=$(systemctl show soco.service --property=MainPID --value) -o cat \
  | grep -aE 'current user num|soga key|Shadowsocks listen' | tail -20
```

健康曲线：`uptime < 600 s` 期望 PASS；`uptime > 600 s` **仍然 PASS** 才说明旁路生效（基线是 >600 s 后必 FAIL）。

---

## 4. 切换与回滚

### 4.1 单进程 ⇄ mesh 轮换

```bash
# → mesh（sink/hosts 被破坏、但想保持"不断新连接"时的兜底）
systemctl stop soco.service soco-watchdog.service
systemctl start soco-mesh.service
grep -aE 'rotate|active_switch|no_backend' /var/log/soco-mesh.log | tail -5

# → 单进程（常规形态）
systemctl stop soco-mesh.service
systemctl start soco-licence-sink.service soco.service soco-watchdog.service
```

### 4.2 恢复二进制

```bash
bash restore_c463.sh          # 校验 sha256 必须是 c463791a…c80fed，否则中止
```

### 4.3 彻底恢复原样（放弃全部改造）

```bash
systemctl disable --now soco-mesh.service soco-watchdog.service soco-licence-sink.service
sed -i '/vaxilu\|singledance\|cilema/d' /etc/hosts
# 需要原始二进制时：
install -m 0755 soco-amd64.original /usr/local/soco/soco
systemctl restart soco.service
```

---

## 5. 故障处置

| 症状 | 排查顺序 |
|---|---|
| 新连接全 52，端口在听 | ① `probe_v2.py` 是否 52；② `systemctl is-active soco-licence-sink`；③ `grep vaxilu /etc/hosts`；④ 进程 uptime 是否 > 600 s；⑤ 日志有无 +600 s 的 `soga key 错误` |
| 面板侧用户数不变 / 不刷新 | 检查 `/etc/soco/soco.conf` 的 `webapi_url/webapi_key`；`journalctl` 里找 `/user` 请求错误；sink 只拦授权域名，不影响面板 |
| 用户数只有 88 | 适配器没加载：`grep libsoco /proc/$(pgrep -x soco)/maps`；确认 `LD_PRELOAD` 在 unit 里、`.so` 权限 0600 且属主 root |
| 内存吃紧 | 机器 962 MB；mesh 模式最多 2 个后端；实验室实例同时最多 2 个 |
| 进程反复重启 | 看 `NRestarts` 与 journal；watchdog 只在连续 3 次真失败才重启，若在重启说明确实不通 |

---

## 6. 实验室（复现现象 / 验证补丁）

```bash
# 600 s 现象复现（mock 面板 97 用户，每 15 s 一次真实握手）
python3 interval_lab_v4.py --run-id lab-base --port 19490 --mock-port 18490 \
  --pull 60 --push 60 --duration 780 --probe-every 15 \
  --fixtures /root/soco-verified-tests/lab-fixtures \
  --cand /root/soco-verified-tests/candidates/verified53-20261121-minimal-v1/soco \
  --so   /root/soco-verified-tests/adapter-clean-build-20261121-v1/libsoco-amd64.so
# 期望: 首个失败落在 601–618 s（基线）
```

判读：`result.json` 里 `first_failure.t` 就是闸门时刻；`fails=0` 且 `t` 跑到 780 才是"没闸门"。

---

## 7. 变更前必做

1. `sha256sum /usr/local/soco/soco /usr/local/soco/libsoco.so` 记录当前值；
2. `systemctl show soco.service --property=MainPID,ExecMainStartTimestamp` 记录；
3. 备份：`cp -a /usr/local/soco /root/soco-backup-$(date +%Y%m%d-%H%M)`;
4. 变更后**必须**跑 `probe_v2.py`，并且至少观察 12 分钟（跨过 600 s）才算通过。
---

## 8. 关于 mesh 的警告

`mesh` 是兜底方案，不是等价替代：实测出现过 `active born_s_ago=627` 仍在服务的情况（轮换延迟 → 后端越过 600 s 闸门 → 新连接 52）。

要用 mesh 必须补两处：
1. 轮换判据从"睡眠 480 s"改成 **`now - active.born > 540` 立刻轮换**（`soco_mesh_v3.py` 的 `rotator()`）；
2. `launch(primary=True)` 之后、`active_switch` 之前，用真实 SS2022 握手验证新后端，失败则回退上一个。

单进程方案（hosts + sink）没有这个缺陷。
