#!/bin/bash
# 启动网金新服务端。用法：./start.sh [其他 jyserver.server 参数，如 -v]
# 端口默认 6731（原版客户端写死的端口），可用环境变量改：PORT=6732 ./start.sh
cd "$(dirname "$0")" || exit 1

PY="${PYTHON:-python3}"
if ! command -v "$PY" >/dev/null 2>&1; then
    echo "找不到 $PY，请先安装 Python 3.14（见 部署说明.md）" >&2
    exit 1
fi
if ! "$PY" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 14) else 1)'; then
    echo "需要 Python 3.14 或更高，当前是：$("$PY" --version 2>&1)" >&2
    echo "装好后可以这样指定：PYTHON=/usr/local/bin/python3.14 ./start.sh" >&2
    exit 1
fi

exec "$PY" -m jyserver.server --host 0.0.0.0 --port "${PORT:-6731}" --autosave 60 "$@"
