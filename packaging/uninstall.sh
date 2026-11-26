#!/bin/bash
# soco 卸载脚本
set -e
[ "$(id -u)" -eq 0 ] || { echo "必须以 root 运行"; exit 1; }

echo "=============================================="
echo " soco 卸载"
echo "=============================================="

echo ""
echo "=== 1. 停止并禁用服务 ==="
for unit in soco.service soco@.service; do
    if systemctl list-unit-files 2>/dev/null | grep -q "^${unit%%@*}"; then
        systemctl stop "$unit" 2>/dev/null || true
        systemctl disable "$unit" 2>/dev/null || true
        echo "  $unit 已停用"
    fi
done

echo ""
echo "=== 2. 删除 unit 文件 ==="
rm -f /etc/systemd/system/soco.service /etc/systemd/system/soco@.service
rm -f /usr/lib/systemd/system/soco.service /usr/lib/systemd/system/soco@.service
systemctl daemon-reload
systemctl reset-failed 2>/dev/null || true
echo "  已删除"

echo ""
echo "=== 3. 删除程序文件 ==="
rm -rf /usr/local/soco
rm -f /usr/bin/soco-verify /usr/bin/soco-uninstall
echo "  已删除 /usr/local/soco 与辅助命令"

echo ""
echo "=== 4. 配置文件 ==="
if [ -d /etc/soco ]; then
    echo "  保留 /etc/soco/ （配置不删，防止误删面板密钥）"
    echo "  确认不需要后手动执行：rm -rf /etc/soco"
fi

echo ""
echo "=== 5. 备份目录 ==="
ls -d /root/soco-backup-* 2>/dev/null | tail -5 || echo "  无备份"

echo ""
echo "=============================================="
echo " 卸载完成"
echo "=============================================="
echo "如需回到原版 soga：systemctl start soga"
echo ""