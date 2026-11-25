#!/bin/bash
# soga 兼容入口：nfu / soga 生态脚本调用 `soga restart|stop|start|status|log|config` 时，
# 实际作用到 soco（同一份 /etc/soga 配置）。真实实现见 /usr/bin/soco。
exec /usr/bin/soco "$@"