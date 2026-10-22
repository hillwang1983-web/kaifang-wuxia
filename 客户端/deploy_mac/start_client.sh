#!/bin/bash
# 启动网金网页客户端的网关，然后在浏览器里打开 http://127.0.0.1:8088/
# 用法：./start_client.sh [gateway.py 的其它参数，如 --look-fallback]
# 环境变量：SERVER=host:port 游戏服务端地址（默认 127.0.0.1:6731，也就是同一台 Mac 上用 jyserver 的 start.sh 起的服务端）
#           LISTEN=host:port 网关监听地址（默认 127.0.0.1:8088；游戏协议没有密码，别随便监听到局域网）
#           PYTHON=/path/to/python3 指定解释器
cd "$(dirname "$0")" || exit 1

PY="${PYTHON:-python3}"
if ! command -v "$PY" >/dev/null 2>&1; then
    echo "找不到 $PY，请先安装 Python（见 部署说明.md）" >&2
    exit 1
fi
if ! "$PY" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)'; then
    echo "需要 Python 3.10 或更高，当前是：$("$PY" --version 2>&1)" >&2
    echo "装好后可以这样指定：PYTHON=/usr/local/bin/python3.14 ./start_client.sh" >&2
    exit 1
fi

export PYTHONUTF8=1
exec "$PY" gateway.py --listen "${LISTEN:-127.0.0.1:8088}" --server "${SERVER:-127.0.0.1:6731}" "$@"
