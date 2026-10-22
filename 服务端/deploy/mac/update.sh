#!/bin/bash
# 把这个更新包装到 Mac 上已经部署好的服务端目录里。玩家数据（data/chars.sqlite）不会被覆盖。
#
#   bash ~/Downloads/jyserver-mac-update-XXXX/update.sh [安装目录]     # 安装目录默认 ~/jyserver-mac
#
# 步骤：在更新包里跑测试 → 停服（先存档）→ 备份角色库和旧代码到 backups/<时间>/ → 换新代码 → 按原来的方式重启。
# 环境变量：SKIP_TESTS=1 跳过测试；PYTHON=python3.14 指定 Python。
set -eu

SRC="$(cd "$(dirname "$0")" && pwd)"
DST="${1:-$HOME/jyserver-mac}"
PY="${PYTHON:-python3}"
PLIST="$HOME/Library/LaunchAgents/com.jyserver.plist"
PATTERN='-m jyserver\.server'
CODE_DIRS="jyserver tests tools docs 原版数据"
TOP_FILES="start.sh update.sh README.md 部署说明.md VERSION.txt"

fail() { echo "✗ $*" >&2; exit 1; }
running() { pgrep -f -- "$PATTERN" >/dev/null; }

[ -d "$DST" ] || fail "安装目录 $DST 不存在。用法：bash $0 <安装目录>"
DST="$(cd "$DST" && pwd)"
[ "$SRC" != "$DST" ] || fail "这是安装目录本身。请把更新包解压到别处（比如「下载」文件夹），再运行它里面的 update.sh"
[ -f "$DST/data/chars.sqlite" ] || fail "$DST 里没有 data/chars.sqlite，看起来不是服务端的安装目录"
[ ! -e "$SRC/data/chars.sqlite" ] || fail "这个包里带了角色库，是完整包不是更新包；为了不覆盖玩家数据，已停止"
[ -d "$SRC/jyserver" ] || fail "$SRC 里没有 jyserver/，更新包不完整"
command -v "$PY" >/dev/null 2>&1 || fail "找不到 $PY，可以用 PYTHON=python3.14 指定"
"$PY" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 14) else 1)' || fail "需要 Python 3.14 或更高，当前是 $("$PY" --version 2>&1)"

echo "安装目录：$DST"
echo "当前版本：$(cat "$DST/VERSION.txt" 2>/dev/null || echo 未知)  →  新版本：$(cat "$SRC/VERSION.txt" 2>/dev/null || echo 未知)"

# 1. 先在更新包里跑测试，不通过就什么都不动
if [ "${SKIP_TESTS:-0}" != 1 ]; then
    echo "→ 运行测试（1~2 分钟）"
    (cd "$SRC" && "$PY" -m unittest discover -s tests -t . -q) || fail "测试没通过，服务端没有动"
fi

# 2. 停服：服务端收到 SIGTERM 会先给在线玩家存档再退出
MODE=stopped
if [ -f "$PLIST" ] && launchctl list com.jyserver >/dev/null 2>&1; then
    MODE=launchd
    echo "→ 停止服务端（launchd）"
    launchctl unload "$PLIST"
elif running; then
    MODE=background
    echo "→ 停止服务端"
    pkill -TERM -f -- "$PATTERN"
fi
for _ in $(seq 1 20); do
    running || break
    sleep 1
done
if running; then fail "服务端 20 秒内没停下来，没有更新。手动停掉后再运行一次"; fi

# 3. 备份角色库和旧代码，出问题可以回滚
TS="$(date +%Y%m%d-%H%M%S)"
BK="$DST/backups/$TS"
mkdir -p "$BK"
cp -R "$DST/data" "$BK/data"
for d in $CODE_DIRS; do
    if [ -e "$DST/$d" ]; then mv "$DST/$d" "$BK/$d"; fi
done
for f in $TOP_FILES; do
    if [ -f "$DST/$f" ]; then cp "$DST/$f" "$BK/$f"; fi
done
echo "→ 已备份到 backups/$TS"

# 4. 换上新版本。data/ 只覆盖包里有的文件，包里没有 chars.sqlite，所以玩家数据不动
for d in $CODE_DIRS; do
    if [ -d "$SRC/$d" ]; then cp -R "$SRC/$d" "$DST/$d"; fi
done
cp -R "$SRC/data/." "$DST/data/"
for f in $TOP_FILES; do
    if [ -f "$SRC/$f" ]; then cp "$SRC/$f" "$DST/$f"; fi
done
chmod +x "$DST/start.sh" "$DST/update.sh"
echo "→ 已更新到 $(cat "$DST/VERSION.txt" 2>/dev/null || echo 新版本)"

# 5. 按原来的方式重启
case "$MODE" in
    launchd)
        launchctl load "$PLIST" ;;
    background)
        (cd "$DST" && PYTHON="$PY" nohup ./start.sh >> server.log 2>&1 &) ;;
    stopped)
        echo "服务端原来没在运行，没有自动启动。启动：cd \"$DST\" && ./start.sh"
        exit 0 ;;
esac
sleep 3
if running; then
    echo "✓ 服务端已重新启动"
else
    echo "✗ 服务端没起来，看日志：$( [ "$MODE" = launchd ] && echo /tmp/jyserver.log || echo "$DST/server.log" )" >&2
    echo "  回滚：cd \"$DST\" && rm -rf $CODE_DIRS && cp -R backups/$TS/. . && ./start.sh" >&2
    exit 1
fi
