@echo off
rem 在 资源解析 目录起一个静态服务器, 然后访问 http://localhost:8765/viewer/ (?dir=boy05 可直接打开某目录)
cd /d "%~dp0.."
python -m http.server 8765 --bind 127.0.0.1
